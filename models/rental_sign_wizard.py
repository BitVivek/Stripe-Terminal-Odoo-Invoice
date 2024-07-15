from odoo import api, fields, models


class RentalSign(models.TransientModel):
    _inherit = "rental.sign.wizard"
    _description = "Sign Documents from a SO"


    def next_step(self):
        action = super(RentalSign,self).next_step()
        if action.get("context").get("sign_directly_without_mail"):
            action["context"]["sign_directly_without_mail"] = False
        return action