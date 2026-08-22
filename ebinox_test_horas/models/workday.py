from odoo import _, api, fields, models
from odoo.exceptions import UserError, ValidationError


class TestHorasWorkday(models.Model):
    _name = "test.horas.workday"
    _description = "Jornada consolidada"
    _inherit = ["test.horas.staging.guard.mixin", "test.horas.calendar.resolver.mixin"]
    _order = "operational_date desc, employee_id"

    employee_id = fields.Many2one("hr.employee", required=True, index=True, ondelete="restrict")
    company_id = fields.Many2one(related="employee_id.company_id", store=True, index=True)
    operational_date = fields.Date(required=True, index=True)
    state = fields.Selection(
        [("imported", "Importada"), ("review", "A revisar"), ("classified", "Corregida / clasificada"), ("calculated", "Calculada"), ("audited", "Auditada"), ("closed", "Cerrada")],
        required=True,
        default="imported",
        index=True,
    )
    clock_event_ids = fields.Many2many("test.horas.clock.event", string="Marcaciones crudas", copy=False)
    declared_calendar_id = fields.Many2one("resource.calendar", string="Horario declarado", ondelete="restrict")
    effective_calendar_id = fields.Many2one("resource.calendar", string="Horario efectivo", ondelete="restrict")
    first_mark = fields.Datetime(readonly=True)
    last_mark = fields.Datetime(readonly=True)
    mark_count = fields.Integer(readonly=True)
    corrected_first_mark = fields.Datetime(copy=False)
    corrected_last_mark = fields.Datetime(copy=False)
    effective_first_mark = fields.Datetime(compute="_compute_effective_marks", store=True)
    effective_last_mark = fields.Datetime(compute="_compute_effective_marks", store=True)
    novelty_id = fields.Many2one("test.horas.daily.novelty", ondelete="restrict")
    warning_code = fields.Char(readonly=True, index=True)
    warning_detail = fields.Text(readonly=True)
    ordinary_diurnal_min = fields.Integer(readonly=True)
    ordinary_nocturnal_min = fields.Integer(readonly=True)
    tardiness_min = fields.Integer(readonly=True)
    detected_overtime_min = fields.Integer(readonly=True)
    payable_50_diurnal_min = fields.Integer(readonly=True)
    payable_50_nocturnal_min = fields.Integer(readonly=True)
    payable_100_diurnal_min = fields.Integer(readonly=True)
    payable_100_nocturnal_min = fields.Integer(readonly=True)
    calculation_version = fields.Char(readonly=True)
    calculated_at = fields.Datetime(readonly=True)
    calculated_by_id = fields.Many2one("res.users", readonly=True)
    audit_note = fields.Text(copy=False)

    _sql_constraints = [
        ("employee_operational_date_unique", "unique(employee_id, operational_date)", "Ya existe una jornada para esa persona y fecha operativa."),
        ("minutes_nonnegative", "check(ordinary_diurnal_min >= 0 AND ordinary_nocturnal_min >= 0 AND tardiness_min >= 0 AND detected_overtime_min >= 0)", "Los minutos no pueden ser negativos."),
    ]

    @api.depends("first_mark", "last_mark", "corrected_first_mark", "corrected_last_mark")
    def _compute_effective_marks(self):
        for record in self:
            record.effective_first_mark = record.corrected_first_mark or record.first_mark
            record.effective_last_mark = record.corrected_last_mark or record.last_mark

    @api.model_create_multi
    def create(self, vals_list):
        self._assert_staging()
        return super().create(vals_list)

    def write(self, vals):
        protected = {"first_mark", "last_mark", "mark_count", "clock_event_ids"}
        if protected.intersection(vals) and not self.env.context.get("test_horas_import"):
            raise UserError(_("Las marcaciones consolidadas sólo pueden cambiarse mediante una importación auditada."))
        if any(record.state == "closed" for record in self) and not self.env.context.get("test_horas_reopen"):
            raise UserError(_("Una jornada cerrada debe reabrirse con permiso y motivo antes de modificarse."))
        return super().write(vals)

    def action_mark_review(self):
        self._assert_staging()
        self.write({"state": "review"})

    def action_mark_audited(self):
        self._assert_staging()
        if not self.audit_note:
            raise ValidationError(_("Indique una nota de auditoría."))
        self.write({"state": "audited"})

    def action_close(self):
        self._assert_staging()
        if self.state != "audited":
            raise ValidationError(_("Sólo puede cerrarse una jornada auditada."))
        self.write({"state": "closed"})
        for record in self:
            record._log_test_horas_event("workday.closed", "Jornada cerrada", {"date": record.operational_date, "calculation_version": record.calculation_version})


class TestHorasWorkdayAdjustment(models.Model):
    _name = "test.horas.workday.adjustment"
    _description = "Ajuste auditable de jornada"
    _inherit = ["test.horas.staging.guard.mixin", "test.horas.immutable.audit.mixin"]
    _order = "created_at desc, id desc"

    workday_id = fields.Many2one("test.horas.workday", required=True, index=True, ondelete="restrict")
    employee_id = fields.Many2one(related="workday_id.employee_id", store=True, index=True)
    company_id = fields.Many2one(related="employee_id.company_id", store=True, index=True)
    reason = fields.Text(required=True)
    previous_calendar_id = fields.Many2one("resource.calendar", ondelete="restrict", readonly=True)
    new_calendar_id = fields.Many2one("resource.calendar", ondelete="restrict", readonly=True)
    previous_first_mark = fields.Datetime(readonly=True)
    new_first_mark = fields.Datetime(readonly=True)
    previous_last_mark = fields.Datetime(readonly=True)
    new_last_mark = fields.Datetime(readonly=True)
    absorbed_into_previous_day = fields.Boolean(readonly=True)
    created_at = fields.Datetime(default=fields.Datetime.now, required=True, readonly=True)
    created_by_id = fields.Many2one("res.users", default=lambda self: self.env.user, readonly=True)

    @api.model_create_multi
    def create(self, vals_list):
        self._assert_staging()
        records = super().create(vals_list)
        for record in records:
            record.workday_id.with_context(test_horas_adjustment=True).write({
                "effective_calendar_id": record.new_calendar_id.id or record.workday_id.effective_calendar_id.id,
                "corrected_first_mark": record.new_first_mark or record.workday_id.corrected_first_mark,
                "corrected_last_mark": record.new_last_mark or record.workday_id.corrected_last_mark,
                "state": "classified",
            })
            record._log_test_horas_event(
                "workday.adjusted",
                "Horario o marcas corregidos",
                {"workday_id": record.workday_id.id, "adjustment_id": record.id, "reason": record.reason},
            )
        return records

    def write(self, vals):
        self._raise_immutable()

