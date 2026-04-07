# -*- coding: utf-8 -*-

from odoo import models, fields

class FleetVehicle(models.Model):
    _inherit = 'fleet.vehicle'

    codigo_id = fields.Many2one('codigo.id', string='Código')



class CodigoId(models.Model):
    _name = 'codigo.id'
    _description = 'Codigo'

    name = fields.Char(string='Name')