from odoo import _, api, fields, models
from odoo.exceptions import ValidationError

from .common import validate_date_range


class TestHorasOvertimePeriod(models.Model):
    _name = "test.horas.overtime.period"
    _description = "Período de horas extra"
    _inherit = ["test.horas.staging.guard.mixin"]
    _order = "date_from desc, id desc"

    name = fields.Char(required=True)
    company_id = fields.Many2one("res.company", required=True, default=lambda self: self.env.company, index=True)
    date_from = fields.Date(required=True)
    date_to = fields.Date(required=True)
    state = fields.Selection(
        [("draft", "Borrador"), ("calculated", "Calculado"), ("submitted", "A autorizar"), ("approved", "Autorizado"), ("valued", "Valorizado"), ("closed", "Cerrado"), ("cancelled", "Anulado")],
        required=True,
        default="draft",
        index=True,
    )
    line_ids = fields.One2many("test.horas.overtime.line", "period_id")
    calculation_version = fields.Char(readonly=True)
    submitted_by_id = fields.Many2one("res.users", readonly=True)
    submitted_at = fields.Datetime(readonly=True)
    approved_by_id = fields.Many2one("res.users", readonly=True)
    approved_at = fields.Datetime(readonly=True)
    approval_reason = fields.Text()

    @api.constrains("date_from", "date_to")
    def _check_dates(self):
        for record in self:
            validate_date_range(record.date_from, record.date_to, "período de extras")

    @api.model_create_multi
    def create(self, vals_list):
        self._assert_staging()
        return super().create(vals_list)

    def action_submit(self):
        self._assert_staging()
        if not self.line_ids:
            raise ValidationError(_("El período no tiene líneas calculadas."))
        self.write({"state": "submitted", "submitted_by_id": self.env.user.id, "submitted_at": fields.Datetime.now()})

    def action_approve(self):
        self._assert_staging()
        if not self.env.user.has_group("ebinox_test_horas.group_test_horas_supervisor"):
            raise ValidationError(_("Sólo un supervisor puede autorizar horas extra."))
        if not self.approval_reason:
            raise ValidationError(_("La autorización requiere un motivo o referencia."))
        self.write({"state": "approved", "approved_by_id": self.env.user.id, "approved_at": fields.Datetime.now()})


class TestHorasOvertimeLine(models.Model):
    _name = "test.horas.overtime.line"
    _description = "Detalle diario de horas extra"
    _order = "date, employee_id"

    period_id = fields.Many2one("test.horas.overtime.period", required=True, index=True, ondelete="cascade")
    employee_id = fields.Many2one("hr.employee", required=True, index=True, ondelete="restrict")
    company_id = fields.Many2one(related="period_id.company_id", store=True, index=True)
    date = fields.Date(required=True, index=True)
    workday_id = fields.Many2one("test.horas.workday", required=True, ondelete="restrict")
    detected_excess_min = fields.Integer(readonly=True)
    excluded = fields.Boolean(help="Exclusión puntual del día, aun si el período está autorizado.")
    exclusion_reason = fields.Char()
    payable_50_diurnal_min = fields.Integer(readonly=True)
    payable_50_nocturnal_min = fields.Integer(readonly=True)
    payable_100_diurnal_min = fields.Integer(readonly=True)
    payable_100_nocturnal_min = fields.Integer(readonly=True)
    valuation_id = fields.Many2one("test.horas.overtime.valuation", readonly=True)

    _sql_constraints = [
        ("period_employee_date_unique", "unique(period_id, employee_id, date)", "La jornada ya está incluida en el período."),
    ]


class TestHorasOvertimeValuation(models.Model):
    _name = "test.horas.overtime.valuation"
    _description = "Valorización de horas extra"
    _inherit = ["test.horas.staging.guard.mixin"]
    _order = "valuation_date desc, id desc"

    employee_id = fields.Many2one("hr.employee", required=True, index=True, ondelete="restrict")
    period_id = fields.Many2one("test.horas.overtime.period", required=True, index=True, ondelete="restrict")
    company_id = fields.Many2one(related="period_id.company_id", store=True)
    valuation_date = fields.Date(required=True, default=fields.Date.context_today)
    currency_id = fields.Many2one("res.currency", related="company_id.currency_id", store=True)
    source_hour_value = fields.Monetary(required=True, currency_field="currency_id")
    base_factor = fields.Float(required=True, default=0.805, digits=(8, 6))
    overtime_50_factor = fields.Float(required=True, default=1.5, digits=(8, 6))
    overtime_100_factor = fields.Float(required=True, default=2.0, digits=(8, 6))
    nocturnal_factor = fields.Float(required=True, default=0.1333, digits=(8, 6))
    rule_version = fields.Char(required=True)
    raw_amount = fields.Monetary(currency_field="currency_id", readonly=True)
    rounded_amount = fields.Monetary(currency_field="currency_id", readonly=True)
    state = fields.Selection(
        [("prepared", "Preparado"), ("pending", "Pendiente"), ("paid", "Pago"), ("not_applicable", "No aplica")],
        required=True,
        default="prepared",
        index=True,
    )
    authorization_reference = fields.Char()
    payment_reference = fields.Char()

    @api.model_create_multi
    def create(self, vals_list):
        self._assert_staging()
        return super().create(vals_list)

