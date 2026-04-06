# -*- coding: utf-8 -*-

from odoo import models, fields, api


class exe_stock_picking_custom(models.Model):
    _inherit = 'stock.picking'


    transporte = fields.Many2one('res.partner','Transporte')  

