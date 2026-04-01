from odoo import fields, models

class ProjectTag(models.Model):
    _inherit = 'project.tags'

    is_import = fields.Boolean(string="Importación", default=False)

