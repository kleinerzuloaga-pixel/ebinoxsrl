# -*- coding: utf-8 -*-
from odoo import models, fields

class CrmLeadInherit(models.Model):
    _inherit = 'crm.lead'

    partner_id = fields.Many2one(
        'res.partner',
        string='Partner',
        help='Partner associated with the lead'
    )

    partner_sales_purchases_user_id = fields.Many2one(
        'res.users',
        string='Comercial Ventas',
        related='partner_id.user_id',
        store=True,
        readonly=True,
        
    )