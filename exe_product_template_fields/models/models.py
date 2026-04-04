# -*- coding: utf-8 -*-

from odoo import models, fields, api


class ProductTemplate(models.Model):
    _inherit = 'product.template'

    size = fields.Float(string='Tamaño')
    peso = fields.Float(string="Peso")
    espesor = fields.Float(string="Espesor")
    calidad = fields.Many2one('calidad',string='Calidad')



class Calidad(models.Model):
    _name = 'calidad'
    _description = 'Calidad'

    name = fields.Char(string='Calidad')
