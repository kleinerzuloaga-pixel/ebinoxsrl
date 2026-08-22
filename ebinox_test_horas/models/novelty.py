from odoo import _, api, fields, models
from odoo.exceptions import ValidationError

from .common import validate_date_range


class TestHorasNoveltyType(models.Model):
    _name = "test.horas.novelty.type"
    _description = "Tipo de novedad"
    _order = "sequence, code"

    sequence = fields.Integer(default=10)
    code = fields.Char(required=True, index=True)
    name = fields.Char(required=True, translate=True)
    active = fields.Boolean(default=True)
    company_id = fields.Many2one("res.company", index=True)
    valid_from = fields.Date()
    valid_to = fields.Date()
    unit = fields.Selection([("hours", "Horas"), ("days", "Días")], required=True, default="hours")
    counts_as_presence = fields.Boolean()
    counts_for_agreed_hours = fields.Boolean()
    subtracts_from_agreed_hours = fields.Boolean()
    counts_for_absenteeism = fields.Boolean()
    requires_document = fields.Boolean()
    notes = fields.Text()

    _sql_constraints = [
        ("code_company_unique", "unique(code, company_id)", "El código ya existe para esa empresa."),
    ]

    @api.constrains("valid_from", "valid_to")
    def _check_dates(self):
        for record in self:
            validate_date_range(record.valid_from, record.valid_to, "tipo de novedad")


class TestHorasDailyNovelty(models.Model):
    _name = "test.horas.daily.novelty"
    _description = "Novedad diaria"
    _inherit = ["test.horas.staging.guard.mixin"]
    _order = "date desc, employee_id"

    employee_id = fields.Many2one("hr.employee", required=True, index=True, ondelete="restrict")
    company_id = fields.Many2one(related="employee_id.company_id", store=True, index=True)
    date = fields.Date(required=True, index=True)
    novelty_type_id = fields.Many2one("test.horas.novelty.type", required=True, ondelete="restrict")
    workday_id = fields.Many2one("test.horas.workday", ondelete="restrict", index=True)
    state = fields.Selection(
        [("draft", "Borrador"), ("submitted", "Presentada"), ("approved", "Aprobada"), ("rejected", "Rechazada"), ("cancelled", "Anulada")],
        required=True,
        default="draft",
        index=True,
    )
    reason = fields.Text(required=True)
    document_reference = fields.Char()
    submitted_by_id = fields.Many2one("res.users", readonly=True)
    submitted_at = fields.Datetime(readonly=True)
    approved_by_id = fields.Many2one("res.users", readonly=True)
    approved_at = fields.Datetime(readonly=True)
    rejection_reason = fields.Text(readonly=True)

    _sql_constraints = [
        ("employee_date_unique", "unique(employee_id, date)", "Ya existe una novedad para esa persona y fecha."),
    ]

    @api.model_create_multi
    def create(self, vals_list):
        self._assert_staging()
        return super().create(vals_list)

    def action_submit(self):
        self._assert_staging()
        self.write({"state": "submitted", "submitted_by_id": self.env.user.id, "submitted_at": fields.Datetime.now()})
        for record in self:
            record._log_test_horas_event("novelty.submitted", "Novedad presentada", {"code": record.novelty_type_id.code, "date": record.date})

    def action_approve(self):
        self._assert_staging()
        if not self.env.user.has_group("ebinox_test_horas.group_test_horas_supervisor"):
            raise ValidationError(_("Sólo un supervisor puede aprobar novedades."))
        self.write({"state": "approved", "approved_by_id": self.env.user.id, "approved_at": fields.Datetime.now()})
        for record in self:
            record._log_test_horas_event("novelty.approved", "Novedad aprobada", {"code": record.novelty_type_id.code, "date": record.date})

    def action_reject(self):
        self._assert_staging()
        self.write({"state": "rejected"})
        for record in self:
            record._log_test_horas_event("novelty.rejected", "Novedad rechazada", {"code": record.novelty_type_id.code, "date": record.date})

    def action_cancel(self):
        self._assert_staging()
        self.write({"state": "cancelled"})
        for record in self:
            record._log_test_horas_event("novelty.cancelled", "Novedad cancelada", {"code": record.novelty_type_id.code, "date": record.date})

