# -*- coding: utf-8 -*-
from odoo import models, fields
import logging

class CrmLeadInherit(models.Model):
    _inherit = 'crm.lead'

    licitacion = fields.Char(string='Licitacion')
