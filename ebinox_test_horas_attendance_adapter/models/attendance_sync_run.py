import hashlib
import json
from datetime import timedelta

from odoo import _, api, fields, models
from odoo.exceptions import AccessError, UserError, ValidationError


SOURCE = "odoo_hr_attendance"
MAX_WINDOW_DAYS = 62


class TestHorasAttendanceSyncRun(models.Model):
    _name = "test.horas.attendance.sync.run"
    _description = "Sincronización aislada de Asistencias"
    _inherit = ["test.horas.staging.guard.mixin"]
    _order = "create_date desc, id desc"

    name = fields.Char(required=True, default=lambda self: _("Nueva sincronización"))
    company_id = fields.Many2one(
        "res.company", required=True, default=lambda self: self.env.company, index=True
    )
    date_from = fields.Datetime(required=True)
    date_to = fields.Datetime(required=True)
    state = fields.Selection(
        [("draft", "Borrador"), ("previewed", "Previsualizada"), ("done", "Completada")],
        required=True,
        default="draft",
        readonly=True,
        index=True,
    )
    preview_attendance_count = fields.Integer(readonly=True)
    attendances_read = fields.Integer(readonly=True)
    events_detected = fields.Integer(readonly=True)
    events_created = fields.Integer(readonly=True)
    events_already_present = fields.Integer(readonly=True)
    open_attendances = fields.Integer(readonly=True)
    executed_by_id = fields.Many2one("res.users", readonly=True)
    started_at = fields.Datetime(readonly=True)
    finished_at = fields.Datetime(readonly=True)
    operations_log = fields.Text(readonly=True)

    @api.model_create_multi
    def create(self, vals_list):
        self._assert_staging()
        return super().create(vals_list)

    @api.constrains("date_from", "date_to")
    def _check_window(self):
        for record in self:
            if record.date_from and record.date_to:
                if record.date_to <= record.date_from:
                    raise ValidationError(_("La fecha final debe ser posterior a la inicial."))
                if record.date_to - record.date_from > timedelta(days=MAX_WINDOW_DAYS):
                    raise ValidationError(
                        _("La ventana máxima de sincronización es de %s días.", MAX_WINDOW_DAYS)
                    )

    def _assert_source_permissions(self):
        self.ensure_one()
        if not self.env.user.has_group("ebinox_test_horas.group_test_horas_manager"):
            raise AccessError(_("Se requiere el rol Administrador funcional de Test de Horas."))
        if not self.env.user.has_group("hr_attendance.group_hr_attendance_manager"):
            raise AccessError(_("Se requieren permisos existentes de administración de Asistencias."))

    def _source_domain(self):
        self.ensure_one()
        return [
            ("employee_id.company_id", "=", self.company_id.id),
            ("check_in", ">=", self.date_from),
            ("check_in", "<=", self.date_to),
        ]

    def action_preview(self):
        self.ensure_one()
        self._assert_staging()
        self._assert_source_permissions()
        count = self.env["hr.attendance"].search_count(self._source_domain())
        self.write(
            {
                "state": "previewed",
                "preview_attendance_count": count,
                "operations_log": "hr.attendance.search_count; escrituras estándar: 0",
            }
        )
        return True

    def action_sync(self):
        self.ensure_one()
        self._assert_staging()
        self._assert_source_permissions()
        if self.state not in {"draft", "previewed"}:
            raise UserError(_("Esta corrida ya fue ejecutada."))

        started_at = fields.Datetime.now()
        attendances = self.env["hr.attendance"].search(
            self._source_domain(), order="check_in, id"
        )
        candidates = []
        open_attendances = 0
        for attendance in attendances:
            candidates.append(self._event_values(attendance, "in", attendance.check_in))
            if attendance.check_out:
                candidates.append(self._event_values(attendance, "out", attendance.check_out))
            else:
                open_attendances += 1

        event_model = self.env["test.horas.clock.event"]
        external_ids = [item["external_id"] for item in candidates]
        existing = set(
            event_model.search(
                [("source", "=", SOURCE), ("external_id", "in", external_ids)]
            ).mapped("external_id")
        )
        missing = [item for item in candidates if item["external_id"] not in existing]
        if missing:
            event_model.create(missing)

        finished_at = fields.Datetime.now()
        self.write(
            {
                "state": "done",
                "attendances_read": len(attendances),
                "events_detected": len(candidates),
                "events_created": len(missing),
                "events_already_present": len(candidates) - len(missing),
                "open_attendances": open_attendances,
                "executed_by_id": self.env.user.id,
                "started_at": started_at,
                "finished_at": finished_at,
                "operations_log": (
                    "Lecturas estándar: hr.attendance.search. "
                    "Escrituras estándar: 0. Destino: test.horas.clock.event."
                ),
            }
        )
        self._log_test_horas_event(
            "attendance.synced",
            "Asistencias leídas y fichadas privadas sincronizadas",
            {
                "attendances_read": len(attendances),
                "events_created": len(missing),
                "open_attendances": open_attendances,
                "writes_standard": 0,
            },
        )
        return True

    def _event_values(self, attendance, event_kind, timestamp):
        self.ensure_one()
        normalized_timestamp = fields.Datetime.to_string(timestamp)
        version_material = "%s|%s|%s" % (attendance.id, event_kind, normalized_timestamp)
        version_hash = hashlib.sha256(version_material.encode("utf-8")).hexdigest()[:16]
        external_id = "hr.attendance:%s:%s:%s" % (
            attendance.id,
            event_kind,
            version_hash,
        )
        payload = {
            "model": "hr.attendance",
            "record_id": attendance.id,
            "employee_id": attendance.employee_id.id,
            "event_kind": event_kind,
            "timestamp": normalized_timestamp,
            "snapshot_version": version_hash,
        }
        return {
            "employee_id": attendance.employee_id.id,
            "timestamp": timestamp,
            "source": SOURCE,
            "external_id": external_id,
            "event_kind": event_kind,
            "source_payload": json.dumps(payload, sort_keys=True),
        }

