# -*- coding: utf-8 -*-

from odoo import models, fields, api


class PurchaseRequisition(models.Model):
    _inherit = 'purchase.requisition'

    rubro = fields.Many2one('rubro', string="Rubro")
    area = fields.Many2one('area', string="Area")
    prioridad = fields.Many2one('prioridad', string="Prioridad")



class Rubro(models.Model):
    _name = 'rubro'
    _description = 'Rubro'

    name = fields.Char(string='Rubro')


class Area(models.Model):
    _name = 'area'
    _description = 'Area'

    name = fields.Char(string='Area')


class Prioridad(models.Model):
    _name = 'prioridad'
    _description = 'Prioridad'

    name = fields.Char(string='Prioridad')


