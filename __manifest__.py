# -*- coding: utf-8 -*-
# Part of Odoo. See LICENSE file for full copyright and licensing details.
{
    'name': 'Stripe Terminal In Invoice',
    'version': '1.0',
    'summary': 'Stripe Terminal In Invoice',
    'sequence': 10,
    'description': """
    Customization in the business flow
    """,
    'author': "Vivek Kundaliya",
    'website': "https:trewac.com",
    'depends': ['web','base','account','base_setup','payment'],
    'assets': {
        'web.assets_backend': [
            'stripe_account_move/static/src/js/payment_stripe.js',
            'stripe_account_move/static/src/js/stripe.js',
            'stripe_account_move/static/src/xml/payment_stripe.xml',
            'stripe_account_move/static/src/css/payment_style.css'
        ],
    },
    'data': [
        # 'views/assets.xml',
        # 'security/ir.model.access.csv',
        'wizard/stripe_wizard_template.xml',
        'views/account_move.xml',
        'views/payment_provider.xml',
        'views/payment_link.xml',
        'views/sale_order.xml',
        'views/payment_method.xml'

    ],

    'installable': True,
    'application': True,
    'license': 'LGPL-3',
}
