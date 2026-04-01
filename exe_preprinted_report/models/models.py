# -*- coding: utf-8 -*-
from odoo import models, fields, api

class StockPicking(models.Model):
    _inherit='stock.picking'

    # Los nombres los dejo en español para evitar que choquen con algun campo de Odoo.


    valor_declarado = fields.Float('Valor Declarado')

     
    tipo_moneda = fields.Selection(
        selection=[
            ('usd', 'USD'),
            ('ars', 'ARS')
        ],
        string='Currency',
        default='ars'  
    )