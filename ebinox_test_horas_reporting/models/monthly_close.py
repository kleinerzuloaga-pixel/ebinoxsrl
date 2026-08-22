import calendar
import hashlib
import json
from collections import Counter
from datetime import date

from odoo import _, api, fields, models
from odoo.exceptions import AccessError, UserError, ValidationError


class TestHorasMonthlyClose(models.Model):
    _name = "test.horas.monthly.close"
    _description = "Cierre mensual aislado por empleado"
    _inherit = ["test.horas.staging.guard.mixin"]
    _order = "month desc, employee_id"

    employee_id = fields.Many2one("hr.employee", required=True, index=True, ondelete="restrict")
    company_id = fields.Many2one(related="employee_id.company_id", store=True, index=True)
    month = fields.Date(required=True, index=True, help="Usar el primer día del mes.")
    date_from = fields.Date(compute="_compute_range", store=True)
    date_to = fields.Date(compute="_compute_range", store=True)
    state = fields.Selection(
        [("draft", "Borrador"), ("computed", "Calculado"), ("reviewed", "Revisado"), ("closed", "Cerrado"), ("reopened", "Reabierto")],
        required=True,
        default="draft",
        index=True,
    )
    ordinary_diurnal_min = fields.Integer(readonly=True)
    ordinary_nocturnal_min = fields.Integer(readonly=True)
    tardiness_min = fields.Integer(readonly=True)
    overtime_50_diurnal_min = fields.Integer(readonly=True)
    overtime_50_nocturnal_min = fields.Integer(readonly=True)
    overtime_100_diurnal_min = fields.Integer(readonly=True)
    overtime_100_nocturnal_min = fields.Integer(readonly=True)
    pending_workdays = fields.Integer(readonly=True)
    novelty_summary = fields.Text(readonly=True)
    calculation_versions = fields.Char(readonly=True)
    close_hash = fields.Char(readonly=True, index=True)
    audit_note = fields.Text()
    reviewed_by_id = fields.Many2one("res.users", readonly=True)
    reviewed_at = fields.Datetime(readonly=True)
    closed_by_id = fields.Many2one("res.users", readonly=True)
    closed_at = fields.Datetime(readonly=True)
    reopen_reason = fields.Text()

    _sql_constraints = [
        ("employee_month_unique", "unique(employee_id, month)", "Ya existe un cierre para esa persona y mes."),
    ]

    @api.depends("month")
    def _compute_range(self):
        for record in self:
            if not record.month:
                record.date_from = False
                record.date_to = False
                continue
            first = record.month.replace(day=1)
            last = calendar.monthrange(first.year, first.month)[1]
            record.date_from = first
            record.date_to = date(first.year, first.month, last)

    @api.constrains("month")
    def _check_month(self):
        for record in self:
            if record.month and record.month.day != 1:
                raise ValidationError(_("El mes debe informarse con su primer día."))

    @api.model_create_multi
    def create(self, vals_list):
        self._assert_staging()
        return super().create(vals_list)

    def write(self, vals):
        if any(record.state == "closed" for record in self) and not self.env.context.get(
            "test_horas_reopen"
        ):
            raise UserError(_("Un cierre mensual cerrado no puede modificarse sin reapertura."))
        return super().write(vals)

    def action_compute(self):
        for record in self:
            record._assert_staging()
            if record.state not in {"draft", "reopened", "computed"}:
                raise ValidationError(_("El estado actual no permite recalcular."))
            workdays = self.env["test.horas.workday"].search(
                [
                    ("employee_id", "=", record.employee_id.id),
                    ("operational_date", ">=", record.date_from),
                    ("operational_date", "<=", record.date_to),
                ],
                order="operational_date",
            )
            novelties = self.env["test.horas.daily.novelty"].search(
                [
                    ("employee_id", "=", record.employee_id.id),
                    ("date", ">=", record.date_from),
                    ("date", "<=", record.date_to),
                    ("state", "=", "approved"),
                ]
            )
            novelty_counts = Counter(novelties.mapped("novelty_type_id.code"))
            pending = workdays.filtered(
                lambda day: day.state not in {"calculated", "audited", "closed"}
                or bool(day.warning_code)
            )
            values = {
                "ordinary_diurnal_min": sum(workdays.mapped("ordinary_diurnal_min")),
                "ordinary_nocturnal_min": sum(workdays.mapped("ordinary_nocturnal_min")),
                "tardiness_min": sum(workdays.mapped("tardiness_min")),
                "overtime_50_diurnal_min": sum(workdays.mapped("payable_50_diurnal_min")),
                "overtime_50_nocturnal_min": sum(workdays.mapped("payable_50_nocturnal_min")),
                "overtime_100_diurnal_min": sum(workdays.mapped("payable_100_diurnal_min")),
                "overtime_100_nocturnal_min": sum(workdays.mapped("payable_100_nocturnal_min")),
                "pending_workdays": len(pending),
                "novelty_summary": json.dumps(dict(sorted(novelty_counts.items())), ensure_ascii=False),
                "calculation_versions": ", ".join(sorted(set(workdays.mapped("calculation_version")) - {False})),
            }
            snapshot = {
                "employee_id": record.employee_id.id,
                "month": fields.Date.to_string(record.month),
                "workday_ids": workdays.ids,
                "novelty_ids": novelties.ids,
                **values,
            }
            encoded = json.dumps(snapshot, sort_keys=True, separators=(",", ":"), ensure_ascii=True)
            values.update(
                {
                    "close_hash": hashlib.sha256(encoded.encode("ascii")).hexdigest(),
                    "state": "computed",
                }
            )
            record.write(values)
        return True

    def action_review(self):
        for record in self:
            if record.state != "computed":
                raise ValidationError(_("Sólo puede revisarse un cierre calculado."))
            if not record.audit_note:
                raise ValidationError(_("La revisión requiere una nota de auditoría."))
            record.write(
                {"state": "reviewed", "reviewed_by_id": self.env.user.id, "reviewed_at": fields.Datetime.now()}
            )
        return True

    def action_close(self):
        for record in self:
            if not self.env.user.has_group("ebinox_test_horas.group_test_horas_auditor"):
                raise AccessError(_("Se requiere el rol Auditor de Test de Horas."))
            if record.state != "reviewed" or record.pending_workdays:
                raise ValidationError(_("El cierre debe estar revisado y sin jornadas pendientes."))
            record.write(
                {"state": "closed", "closed_by_id": self.env.user.id, "closed_at": fields.Datetime.now()}
            )
            record._log_test_horas_event(
                "monthly_close.closed",
                "Cierre mensual confirmado",
                {"month": record.month, "close_hash": record.close_hash, "pending_workdays": 0},
            )
        return True

    def action_reopen(self):
        for record in self:
            if not self.env.user.has_group("ebinox_test_horas.group_test_horas_manager"):
                raise AccessError(_("Se requiere el rol Administrador funcional."))
            if record.state != "closed" or not record.reopen_reason:
                raise ValidationError(_("La reapertura requiere un cierre cerrado y un motivo."))
            record.with_context(test_horas_reopen=True).write({"state": "reopened"})
            record._log_test_horas_event(
                "monthly_close.reopened",
                "Cierre mensual reabierto",
                {"month": record.month, "reason": record.reopen_reason},
            )
        return True

