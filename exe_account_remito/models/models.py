from odoo import models, fields, api


class AccountMove(models.Model):
    _inherit = 'account.move'

    stock_picking_ids = fields.One2many(
        'stock.picking',
        'invoice_id',
        string='Salidas',
    )


class StockPicking(models.Model):
    _inherit = 'stock.picking'

    num_remito = fields.Char(string="Número de Remito Pre-impreso")

    invoice_id = fields.Many2one('account.move',
        string='Factura',
    )