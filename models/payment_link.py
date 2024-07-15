# -*- coding: utf-8 -*-
# Part of Odoo. See LICENSE file for full copyright and licensing details.

from werkzeug import urls

from odoo import _, api, fields, models


class PaymentLinkWizard(models.TransientModel):
    _inherit = 'payment.link.wizard'

    def send_sms_to_customer(self):
        context = dict(self.env.context)
        context['default_body'] = f'Please Pay Using the below Link:{self.link} From:Admin'
        return {
            "type": "ir.actions.act_window",
            "res_model": "sms.composer",
            "view_mode": 'form',
            "context": context,
            "name": "Send SMS Text Message",
            "target": "new",
        }