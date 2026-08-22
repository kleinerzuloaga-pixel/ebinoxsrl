from odoo import api, fields, models
from odoo.exceptions import ValidationError


class TestHorasEmployeeProfile(models.Model):
    _name = "test.horas.employee.profile"
    _description = "Perfil auxiliar de empleado para Test de Horas"
    _inherit = ["test.horas.staging.guard.mixin"]
    _order = "employee_id"

    employee_id = fields.Many2one("hr.employee", required=True, index=True, ondelete="restrict")
    company_id = fields.Many2one(related="employee_id.company_id", store=True, index=True)
    active = fields.Boolean(default=True)
    population_type = fields.Selection(
        [("direct", "Directo"), ("indirect", "Indirecto"), ("unclassified", "Sin clasificar")],
        required=True,
        default="unclassified",
        index=True,
    )
    hire_date = fields.Date(string="Fecha de ingreso (snapshot)")
    termination_date = fields.Date(string="Fecha de baja (snapshot)")
    agreement_code = fields.Char(string="Convenio (snapshot)")
    external_employee_key = fields.Char(string="Clave externa estable")
    notes = fields.Text()

    _sql_constraints = [
        ("employee_unique", "unique(employee_id)", "Ya existe un perfil auxiliar para esa persona."),
    ]

    @api.constrains("hire_date", "termination_date")
    def _check_employment_dates(self):
        for record in self:
            if (
                record.hire_date
                and record.termination_date
                and record.termination_date < record.hire_date
            ):
                raise ValidationError("La fecha de baja no puede ser anterior a la fecha de ingreso.")

    @api.model_create_multi
    def create(self, vals_list):
        self._assert_staging()
        return super().create(vals_list)


class TestHorasHoliday(models.Model):
    _name = "test.horas.holiday"
    _description = "Feriado aislado de Test de Horas"
    _inherit = ["test.horas.staging.guard.mixin"]
    _order = "date desc"

    name = fields.Char(required=True)
    date = fields.Date(required=True, index=True)
    company_id = fields.Many2one(
        "res.company", required=True, default=lambda self: self.env.company, index=True
    )
    active = fields.Boolean(default=True)
    pay_overtime = fields.Boolean(string="Liquida extras")
    count_ordinary = fields.Boolean(string="Computa ordinarias")
    notes = fields.Text()

    _sql_constraints = [
        ("company_date_unique", "unique(company_id, date)", "Ya existe un feriado para esa compañía y fecha."),
    ]

    @api.model_create_multi
    def create(self, vals_list):
        self._assert_staging()
        return super().create(vals_list)

