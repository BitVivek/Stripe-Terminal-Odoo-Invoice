# -*- coding: utf-8 -*-
# Part of Odoo. See LICENSE file for full copyright and licensing details.

from werkzeug import urls

from odoo import _, api, fields, models


class SaleOrderExt(models.Model):
    _inherit = 'sale.order'

    def send_sms_to_so_url_customer(self):
        context = dict(self.env.context)
        context['default_body'] = f'Here is the link to you SO:{self.get_base_url()+self.get_portal_url()} From:Admin'
        context['default_recipient_single_number_itf'] = self.partner_id.mobile or ''
        return {
            "type": "ir.actions.act_window",
            "res_model": "sms.composer",
            "view_mode": 'form',
            "context": context,
            "name": "Send SMS Text Message",
            "target": "new",
        }
