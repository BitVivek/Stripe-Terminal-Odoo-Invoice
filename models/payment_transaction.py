import logging
import pprint

from werkzeug.urls import url_encode, url_join

from odoo import _, fields, models
from odoo.exceptions import UserError, ValidationError, AccessError

from odoo.addons.payment import utils as payment_utils
from odoo.addons.payment_stripe import const
from odoo.addons.payment_stripe.controllers.main import StripeController
from odoo.addons.payment.controllers.post_processing import PaymentPostProcessing

_logger = logging.getLogger(__name__)


class PaymentTransaction(models.Model):
    _inherit = 'payment.transaction'

    def terminal_create_transaction(
            self, flow,payment_provider,txn_amount,invoice_id,token_id=None, **kwargs
    ):
        """ Create a draft transaction based on the payment context and return it.

        :param int provider_id: The provider of the provider payment method or token, as a
                                `payment.provider` id.
        :param int|None payment_method_id: The payment method, if any, as a `payment.method` id.
        :param int|None token_id: The token, if any, as a `payment.token` id.
        :param float|None amount: The amount to pay, or `None` if in a validation operation.
        :param int|None currency_id: The currency of the amount, as a `res.currency` id, or `None`
                                     if in a validation operation.
        :param int partner_id: The partner making the payment, as a `res.partner` id.
        :param str flow: The online payment flow of the transaction: 'redirect', 'direct' or 'token'.
        :param bool tokenization_requested: Whether the user requested that a token is created.
        :param str landing_route: The route the user is redirected to after the transaction.
        :param str reference_prefix: The custom prefix to compute the full reference.
        :param bool is_validation: Whether the operation is a validation.
        :param dict custom_create_values: Additional create values overwriting the default ones.
        :param dict kwargs: Locally unused data passed to `_is_tokenization_required` and
                            `_compute_reference`.
        :return: The sudoed transaction that was created.
        :rtype: payment.transaction
        :raise UserError: If the flow is invalid.
        """
        # # Prepare create values
        # if flow in ['redirect', 'direct']:  # Direct payment or payment with redirection
        #     provider_sudo = self.env['payment.provider'].sudo().browse(provider_id)
        #     token_id = None
        #     tokenize = bool(
        #         # Don't tokenize if the user tried to force it through the browser's developer tools
        #         provider_sudo.allow_tokenization
        #         # Token is only created if required by the flow or requested by the user
        #         and (provider_sudo._is_tokenization_required(**kwargs) or tokenization_requested)
        #     )
        # elif flow == 'token':  # Payment by token
        #     token_sudo = self.env['payment.token'].sudo().browse(token_id)
        #
        #     # Prevent from paying with a token that doesn't belong to the current partner (either
        #     # the current user's partner if logged in, or the partner on behalf of whom the payment
        #     # is being made).
        #     partner_sudo = self.env['res.partner'].sudo().browse(partner_id)
        #     if partner_sudo.commercial_partner_id != token_sudo.partner_id.commercial_partner_id:
        #         raise AccessError(_("You do not have access to this payment token."))
        #
        #     provider_sudo = token_sudo.provider_id
        #     payment_method_id = token_sudo.payment_method_id.id
        #     tokenize = False
        # else:
        #     raise ValidationError(
        #         _("The payment should either be direct, with redirection, or made by a token.")
        #     )

        # reference = self.env['payment.transaction']._compute_reference(
        #     provider_sudo.code,
        #     prefix=reference_prefix,
        #     **(custom_create_values or {}),
        #     **kwargs
        # )
        # if is_validation:  # Providers determine the amount and currency in validation operations
        #     amount = provider_sudo._get_validation_amount()
        #     currency_id = provider_sudo._get_validation_currency().id
        invoice_id = self.env['account.move'].browse([invoice_id])
        invoice_found = self.search([("invoice_ids","in",[invoice_id.id])])
        invoice_name = ''
        if invoice_found:
            invoice_name = invoice_id.display_name + '-' + str(len(invoice_found))
        # Create the transaction
        tx_sudo = self.env['payment.transaction'].sudo().create({
            'provider_id': payment_provider.id,
            'payment_method_id': 40,
            'reference': invoice_name,
            'amount': txn_amount,
            'currency_id': invoice_id.currency_id.id,
            'partner_id': invoice_id.partner_id.id,
            'provider_reference':kwargs.get('id'),
            'invoice_ids':[(4,invoice_id.id)],
            'token_id': token_id.id if token_id else False,
            'operation': f'online_{flow}' if flow else 'online_direct',
            'state_message':'Creation of payment Intent',
            'state':'pending'
            # 'tokenize': tokenize,
            # 'landing_route': landing_route,
            # **(custom_create_values or {}),
        })  # In sudo mode to allow writing on callback fields

        return tx_sudo



    def _stripe_handle_notification_data(self,provider_code,notification_data):
        if notification_data:
            notification_data = notification_data.get('charges').get('data')[0]
            if self.provider_code != 'stripe':
                return
            # Update the payment method.
            payment_method = notification_data.get('payment_method_details')
            if isinstance(payment_method, dict):  # capture/void/refund requests receive a string.
                payment_method_type = payment_method.get('type')
                if self.payment_method_id.code == payment_method_type == 'card':
                    payment_method_type = notification_data['payment_method_details']['card']['brand']
                payment_method = self.env['payment.method']._get_from_code(payment_method_type)
                self.payment_method_id = payment_method or self.payment_method_id

            # Update the provider reference and the payment state.
            if self.operation == 'validation':
                self.provider_reference = notification_data['setup_intent']['id']
                status = notification_data['setup_intent']['status']
            elif self.operation == 'refund':
                self.provider_reference = notification_data['refund']['id']
                status = notification_data['refund']['status']
            else:  # 'online_direct', 'online_token', 'offline'
                self.provider_reference = notification_data['payment_intent']
                status = notification_data['status']
            if not status:
                raise ValidationError(
                    "Stripe: " + _("Received data with missing intent status.")
                )
            if status in const.STATUS_MAPPING['draft']:
                pass
            elif status in const.STATUS_MAPPING['pending']:
                self._set_pending()
            elif status in const.STATUS_MAPPING['authorized']:
                if self.tokenize:
                    self._stripe_tokenize_from_notification_data(notification_data)
                self._set_authorized()
            elif status in const.STATUS_MAPPING['done']:
                if self.tokenize:
                    self._stripe_tokenize_from_notification_data(notification_data)

                self._set_done()

                # Immediately post-process the transaction if it is a refund, as the post-processing
                # will not be triggered by a customer browsing the transaction from the portal.
                if self.operation == 'refund':
                    self.env.ref('payment.cron_post_process_payment_tx')._trigger()
            elif status in const.STATUS_MAPPING['cancel']:
                self._set_canceled()
            elif status in const.STATUS_MAPPING['error']:
                if self.operation != 'refund':
                    last_payment_error = notification_data.get('payment_intent', {}).get(
                        'last_payment_error'
                    )
                    if last_payment_error:
                        message = last_payment_error.get('message', {})
                    else:
                        message = _("The customer left the payment page.")
                    self._set_error(message)
                else:
                    self._set_error(_(
                        "The refund did not go through. Please log into your Stripe Dashboard to get "
                        "more information on that matter, and address any accounting discrepancies."
                    ), extra_allowed_states=('done',))
            else:  # Classify unknown intent statuses as `error` tx state
                _logger.warning(
                    "received invalid payment status (%s) for transaction with reference %s",
                    status, self.reference
                )
                self._set_error(_("Received data with invalid intent status: %s", status))



