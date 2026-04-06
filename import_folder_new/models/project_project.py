# -*- coding: utf-8 -*-

from odoo import models, fields, api, exceptions, _

class ProjectInherit(models.Model):
    _inherit = 'project.project'

    importation = fields.Boolean(string='Importación' , default=False)
