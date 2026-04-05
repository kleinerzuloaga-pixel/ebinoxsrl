# -*- coding: utf-8 -*-

from odoo import api, fields, models
import qrcode
import logging
_logger = logging.getLogger(__name__)

class CustomInvoiceReport(models.AbstractModel):
    _name = 'report.exe_account_custom_report.custom_invoice_report_template'
    _description = 'Custom Invoice Report'


class AccountMove(models.Model):
    _inherit = 'account.move'

    def _get_report_values(self, docids, data=None):
        report_values = super(AccountMove, self)._get_report_values(docids, data)
        stock_pickings = self.env['stock.picking'].search([('id', 'in', self.stock_picking_ids.ids)])
        report_values['num_remito'] = stock_pickings.mapped('num_remito')
        return report_values
    
    #agregado para calcular por tasa
    
    exchange_rate = fields.Float( string='Exchange Rate', compute='_compute_exchange_rate', store=True, digits=(12, 6) )

    @api.depends('currency_id', 'invoice_date')
    def _compute_exchange_rate(self):
        for move in self:
            if move.currency_id and move.invoice_date:
                _logger.info('Obteniendo tasas para la moneda: %s en la fecha: %s', move.currency_id.name, move.invoice_date)
                rate_record = self.env['res.currency.rate'].search([
                    ('currency_id', '=', move.currency_id.id),
                    ('company_id', '=', move.company_id.id),
                    ('name', '<=', move.invoice_date)
                ], order='name desc', limit=1)
                
                if rate_record:
                    _logger.info('Tasa encontrada: %s', rate_record.rate)
                    move.exchange_rate = rate_record.rate
                else:
                    _logger.info('No se encontró tasa, usando tasa predeterminada: 1.0')
                    move.exchange_rate = 1.0
            else:
                move.exchange_rate = 1.0