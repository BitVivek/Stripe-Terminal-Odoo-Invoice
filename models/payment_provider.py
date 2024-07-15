import datetime

import requests
import werkzeug

from odoo import fields, models, api, _
from odoo.exceptions import ValidationError, UserError, AccessError
import logging
import requests
import stripe

TIMEOUT = 10
_logger = logging.getLogger(__name__)

class PaymentProviderExt(models.Model):
    _inherit = 'payment.provider'

    stripe_serial_number = fields.Char("Terminal Serial Number",copy=False,help='[Serial number of the stripe terminal], for example: WSC513105011295')
    is_terminal_enabled = fields.Boolean("Receive Payment with Terminal",help="Receive Payment Using terminal in Invoice/Quotation")

    def _process_transaction(self,invoice_id,token_id=False,**resp):
        provider_reference = resp.get('id')
        amount = resp.get('amount_received')/100
        payment_token = int(token_id)
        traxs = self.env['payment.transaction'].search([('provider_reference', '=', provider_reference)])
        if amount > 0:
            if traxs:
                payment_method_id = self.env['account.payment.method.line'].search([('code','=','stripe')],limit=1)
                register_payment = self.env['account.payment.register'].with_context(active_model='account.move',
                                                                  active_ids=invoice_id.ids).create({
                    'amount': amount,
                    'partner_id': invoice_id.partner_id.id,
                    'payment_type': 'inbound',
                    'partner_type': 'customer',
                })._create_payments()
                if register_payment:
                    self.env.cr.commit()
                    if payment_method_id:
                        register_payment.write({'payment_transaction_id':traxs.id,'payment_token_id':payment_token,'payment_method_line_id':payment_method_id.id})
                    else:
                        register_payment.write({'payment_transaction_id': traxs.id, 'payment_token_id': payment_token})
                    traxs.write({'payment_id': register_payment.id})
                    traxs.action_capture()
                    traxs._stripe_handle_notification_data('stripe', resp)
                    return register_payment
                else:
                    traxs._stripe_handle_notification_data('stripe', **resp)
                    ValidationError(f"Could not register Payment for transaction reference:{provider_reference}")
            else:
                raise ValidationError(f"No Transaction Found with reference:{provider_reference}")
        else:
            traxs._stripe_handle_notification_data('stripe', **resp)
            ValidationError("Did Not Received the Amount, Check Transaction")

    @api.constrains('stripe_serial_number')
    def _check_stripe_serial_number(self):
        for payment_method in self:
            if not payment_method.stripe_serial_number:
                continue
            existing_payment_method = self.search([('id', '!=', payment_method.id),
                                                   ('stripe_serial_number', '=', payment_method.stripe_serial_number)],
                                                  limit=1)
            if existing_payment_method:
                raise ValidationError(_('Terminal %s is already used on payment method %s.', \
                                        payment_method.stripe_serial_number, existing_payment_method.display_name))

    def _get_stripe_payment_provider(self):
        stripe_payment_provider = self.search([
            ('code', '=', 'stripe'),
            ('company_id', '=', self.env.company.id)
        ], limit=1)

        if not stripe_payment_provider:
            raise UserError(_("Stripe payment provider for company %s is missing", self.env.company.name))

        return stripe_payment_provider

    @api.model
    def get_stripe_serial_number(self):
        payment_provider = self._get_stripe_payment_provider()
        stripe_serial_key = payment_provider.stripe_serial_number
        is_test = payment_provider.state
        if is_test == 'test':
            is_test = True
            # stripe_serial_key = 'SIMULATOR'
        if not stripe_serial_key:
            raise ValidationError("Stripe Terminal Serial Key Missing or Invalid!")
        # stripe.api_key = self._get_stripe_payment_provider().stripe_secret_key
        # stripe.terminal.Reader.create(
        #     location='tml_FiI81AsuxQg9xA',
        #     registration_code="simulated-wpe",
        # )
        # print("Stripe Terminal Created!!!!")
        return {'stripe_serial_key':stripe_serial_key,'is_test':is_test}
    @api.model
    def _get_stripe_secret_key(self):
        stripe_secret_key = self._get_stripe_payment_provider().stripe_secret_key

        if not stripe_secret_key:
            raise ValidationError(_('Complete the Stripe onboarding for company %s.', self.env.company.name))

        return stripe_secret_key

    @api.model
    def stripe_connection_token(self):
        # if not self.env.user.has_group('point_of_sale.group_pos_user'):
        #     raise AccessError(_("Do not have access to fetch token from Stripe"))

        endpoint = 'https://api.stripe.com/v1/terminal/connection_tokens'

        try:
            resp = requests.post(endpoint, auth=(self.sudo()._get_stripe_secret_key(), ''), timeout=TIMEOUT)
        except requests.exceptions.RequestException:
            _logger.exception("Failed to call stripe_connection_token endpoint")
            raise UserError(_("There are some issues between us and Stripe, try again later."))

        return resp.json()

    def _stripe_calculate_amount(self, amount):
        currency = self.env.user.company_id.currency_id
        return round(float(amount) / currency.rounding)

    def stripe_payment_intent(self, amount,invoice,token=None):
        # if not self.env.user.has_group('point_of_sale.group_pos_user'):
        #     raise AccessError(_("Do not have access to fetch token from Stripe"))

        # For Terminal payments, the 'payment_method_types' parameter must include
        # at least 'card_present' and the 'capture_method' must be set to 'manual'.
        endpoint = 'https://api.stripe.com/v1/payment_intents'
        # currency = self.journal_id.currency_id or self.company_id.currency_id
        currency = self.env.user.company_id.currency_id
        # Get Customer ID
            # If customer object exists , do not create customer
            # If customer does not exists , create a customer.
        # If save payment is enabled , save the card
        # Or just charge the card
        # Create Transaction attached to the invoice
        # Create payment intent if to process the transaction
        # Or to save the card create setup intent.
        if invoice:
            print(invoice)
        token_id = None
        if not token:
            params = [
                ("currency", currency.name),
                ("amount", self._stripe_calculate_amount(amount)),
                ("payment_method_types[]", "card_present"),
                ("capture_method", "manual"),
            ]

            if currency.name == 'AUD' and self.company_id.country_code == 'AU':
                # See https://stripe.com/docs/terminal/payments/regional?integration-country=AU
                # This parameter overrides "capture_method": "manual" above.
                params.append(("payment_method_options[card_present][capture_method]", "manual_preferred"))
            elif currency.name == 'CAD' and self.env.user.company_id.country_code == 'CA':
                params.append(("payment_method_types[]", "interac_present"))
            flow = 'direct'
        else:
            token_id = self.env['payment.token'].browse([int(token)])
            params = [
                ("currency", currency.name),
                ("amount", self._stripe_calculate_amount(amount)),
                ("payment_method_types[]", "card"),
                ("customer",token_id.provider_ref),
                ("payment_method",token_id.stripe_payment_method),
                # ("confirm",True),
                # ("off_session",True)
            ]
            flow = 'token'
        try:
            data = werkzeug.urls.url_encode(params)
            resp = requests.post(endpoint, data=data, auth=(self.sudo()._get_stripe_secret_key(), ''), timeout=TIMEOUT)
        except requests.exceptions.RequestException:
            _logger.exception("Failed to call stripe_payment_intent endpoint")
            raise UserError(_("There are some issues between us and Stripe, try again later."))
        # Transaction for setup intend and one for payment intend
        # If setup Intend or first time by default
        # Create Draft Invoice
        payment_provider = self._get_stripe_payment_provider()
        transaction_id = self.env['payment.transaction'].terminal_create_transaction(flow=flow,payment_provider=payment_provider,txn_amount=amount,invoice_id=invoice[0].get('id'),token_id=token_id,**resp.json())
        print("Payment Intent........")
        print(resp.json())
        return resp.json()

    def stripe_ter_setup_intent(self, invoice):
        payment_provider = self._get_stripe_payment_provider()
        invoice = self.env['account.move'].browse([invoice[0].get('id')])
        cuts_existing_rec = self.env['payment.token'].search([('partner_id', '=', invoice.partner_id.id)], limit=1)
        currency = self.env.user.company_id.currency_id
        if cuts_existing_rec:
            customer = cuts_existing_rec.provider_ref
        else:
            customer = self._create_stripe_customer(payment_provider, invoice)
            customer = customer['id']
        payload = {}
        if customer:
            customer_id = customer

            params = [
                ("customer", customer_id),
                ("description", f"Setup Intend for Invoice: {invoice.name}"),
                ("payment_method_types[]", "card_present"),
                ("usage", "off_session"),
            ]
            payload = werkzeug.urls.url_encode(params)
        response = payment_provider._stripe_make_request(
            'setup_intents', payload=payload
        )
        return response

    def save_payment_token(self, paymentdetails, partner_id):
        customer_id = paymentdetails.get('customer')
        if customer_id:
            stripe.api_key = self._get_stripe_payment_provider().stripe_secret_key
            payment_methods = stripe.SetupIntent.retrieve(
                paymentdetails.get('id'),
                expand=["latest_attempt"],
            )
            payment_id = stripe.Customer.retrieve_payment_method(
                customer_id,
                payment_methods.latest_attempt.payment_method_details.card_present.generated_card,
            )
            if payment_id:
                token = self.env['payment.token'].create({
                    'provider_id': self._get_stripe_payment_provider().id,
                    'payment_method_id': 40,
                    'payment_details': payment_id.card.last4,
                    'partner_id': partner_id,
                    'provider_ref': customer_id,
                    'stripe_payment_method': payment_id.id,
                    'stripe_mandate': paymentdetails.get('mandate'),
                })
                if token:
                    return {'token': token.payment_details}
                else:
                    return {'error': 'Some error Occurred , Try Again!'}
        else:
            return {'error': 'Customer details is Missing, Try Again!'}

    def get_partner_payment_ids(self, partner_id):
        if partner_id:
            payment_token = self.env['payment.token'].search([('partner_id', '=', partner_id)])
            if payment_token:
                payment_ids = []
                for rec in payment_token:
                    payment_ids.append({'id': rec.id, 'name': rec.payment_details})
                return {'recs': payment_ids}
            else:
                return {'not_found': "No Record Found"}

    @api.model
    def stripe_process_setup_intent(self, reader, setup_intent):
        stripe.api_key = self._get_stripe_secret_key()
        response = stripe.terminal.Reader.process_setup_intent(
            reader,
            setup_intent=setup_intent,
            customer_consent_collected=True,
        )
        return response

    def _create_stripe_customer(self, payment_provider_id, invoice_id):
        customer = payment_provider_id._stripe_make_request(
            'customers', payload={
                'address[city]': invoice_id.partner_id.city or None,
                'address[country]': invoice_id.partner_id.country_id.code or None,
                'address[line1]': invoice_id.partner_id.street or None,
                'address[postal_code]': invoice_id.partner_id.zip or None,
                'address[state]': invoice_id.partner_id.name or None,
                'description': f'Odoo Partner: {invoice_id.partner_id.name} (id: {invoice_id.partner_id.id})',
                'email': invoice_id.partner_id.email or None,
                'name': invoice_id.partner_id.name,
                'phone': invoice_id.partner_id.phone or None,
            }
        )
        return customer

    @api.model
    def stripe_capture_payment(self, paymentIntentId, invoice,confirm=False,token=False ):
        """Captures the payment identified by paymentIntentId.

        :param paymentIntentId: the id of the payment to capture
        :param amount: without this parameter the entire authorized
                       amount is captured. Specifying a larger amount allows
                       overcapturing to support tips.
        """
        # if not self.env.user.has_group('point_of_sale.group_pos_user'):
        #     raise AccessError(_("Do not have access to fetch token from Stripe"))
        if not confirm:
            endpoint = ('payment_intents/%s/capture') % (werkzeug.urls.url_quote(paymentIntentId))
        else:
            endpoint = ('payment_intents/%s/confirm') % (werkzeug.urls.url_quote(paymentIntentId))

        data = None
        # if amount is not None:
        #     data = {
        #         "amount_to_capture": self._stripe_calculate_amount(amount),
        #     }
        resp = self.sudo()._get_stripe_payment_provider()._stripe_make_request(endpoint, data)
        # Set the payment transaction and payment token if required.
        # Register payment for the Invoice of the amount
        print("Capture Payment...!")
        print(resp)
        if resp:
            if invoice:
                invoice = self.env['account.move'].browse(invoice[0].get('id'))
                payment = self._process_transaction(invoice_id=invoice,token_id=token,**resp)
                self.env.cr.commit()
        return resp

    def action_stripe_key(self):
        res_id = self._get_stripe_payment_provider().id
        # Redirect
        return {
            'name': _('Stripe'),
            'res_model': 'payment.provider',
            'type': 'ir.actions.act_window',
            'view_mode': 'form',
            'res_id': res_id,
        }

    def confirm_payment_intrec(self,paymentIntentId,invoice,txn_failed=False):

        endpoint = ('/v1/payment_intents/%s') % (werkzeug.urls.url_quote(paymentIntentId))

        data = None

        resp = self.sudo()._get_stripe_payment_provider()._stripe_make_request(endpoint, data)

        if resp['status'] == 'succeeded':
            if invoice:
                invoice = self.env['account.move'].browse(invoice[0].get('id'))
                payment = self._process_transaction(invoice_id=invoice, token_id=False, **resp)
                self.env.cr.commit()
        if txn_failed:
            if invoice:
                invoice = self.env['account.move'].browse(invoice[0].get('id'))
                payment = self._process_transaction(invoice_id=invoice, token_id=False, **resp)
                self.env.cr.commit()

        return resp
