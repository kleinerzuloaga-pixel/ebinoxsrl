# -*- coding: utf-8 -*-

from odoo import models, fields, api
from odoo.exceptions import ValidationError


class AccountMove(models.Model):
    _inherit = 'account.move'


    stock_picking_ids = fields.One2many(
        'stock.picking', 
        'invoice_id',
        string='Salidas',
    )
    def _get_report_values(self, docids, data=None):
        report_values = super(AccountMove, self)._get_report_values(docids, data)

        stock_picking_out = self.stock_picking_ids.filtered(lambda p: p.picking_type_code == 'outgoing')
        
        report_values['num_remitos'] = stock_picking_out.mapped('num_remito')
        
        return report_values

class StockPicking(models.Model):
    _inherit = 'stock.picking'


    num_remito = fields.Char(string="Número de Remito Pre-impreso")

    invoice_id = fields.Many2one('account.move',
        string='Factura',  
    )