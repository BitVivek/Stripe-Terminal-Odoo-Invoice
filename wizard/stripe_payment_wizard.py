from odoo import fields, models, api, _
from odoo.exceptions import ValidationError, UserError, AccessError


class PaymentStripeWizard(models.TransientModel):
    _name = 'payment.stripe.wizard'
    _description = 'Stripe Payment Wizard'

    # Existing fields
    payment_status = fields.Char(string='Payment Status', readonly=True)
    payment_reference = fields.Char(string='Payment Reference', readonly=True)
    message = fields.Text(string='Message', readonly=True)

    # New field for Stripe PaymentIntent ID
    payment_intent_id = fields.Char(string='Payment Intent ID', readonly=True)

    # Other methods remain the same...
