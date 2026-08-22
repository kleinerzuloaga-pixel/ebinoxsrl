from odoo import fields, models


class TestHorasEmployeeProfileNov(models.Model):
    _inherit = "test.horas.employee.profile"

    nov_treatment = fields.Selection(
        [
            ("own", "Personal propio"),
            ("consultant", "Consultora"),
            ("unclassified", "Sin clasificar"),
        ],
        required=True,
        default="unclassified",
        index=True,
        help="Define el tratamiento de NOV/NOVCAL sin depender del nombre de la empresa.",
    )
    consultant_code = fields.Char(
        help="Código informativo de la consultora, por ejemplo CDE o ADECCO."
    )
