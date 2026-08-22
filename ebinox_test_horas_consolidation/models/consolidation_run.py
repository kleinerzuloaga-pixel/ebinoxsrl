import json
from collections import defaultdict
from datetime import timedelta, timezone
from zoneinfo import ZoneInfo, ZoneInfoNotFoundError

from odoo import _, api, fields, models
from odoo.exceptions import AccessError, UserError, ValidationError

from odoo.addons.ebinox_test_horas_calculation.engine.test_horas_engine import Schedule, operational_date


MAX_WINDOW_DAYS = 62


class TestHorasConsolidationRun(models.Model):
    _name = "test.horas.consolidation.run"
    _description = "Consolidación de snapshots en jornadas"
    _inherit = ["test.horas.staging.guard.mixin", "test.horas.calendar.resolver.mixin"]
    _order = "create_date desc, id desc"

    name = fields.Char(required=True, default=lambda self: _("Nueva consolidación"))
    company_id = fields.Many2one(
        "res.company", required=True, default=lambda self: self.env.company, index=True
    )
    date_from = fields.Datetime(required=True)
    date_to = fields.Datetime(required=True)
    state = fields.Selection(
        [("draft", "Borrador"), ("previewed", "Previsualizada"), ("done", "Completada")],
        default="draft",
        required=True,
        readonly=True,
        index=True,
    )
    preview_event_count = fields.Integer(readonly=True)
    events_read = fields.Integer(readonly=True)
    superseded_events_ignored = fields.Integer(readonly=True)
    workdays_created = fields.Integer(readonly=True)
    workdays_updated = fields.Integer(readonly=True)
    unresolved_schedule_days = fields.Integer(readonly=True)
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
                        _("La ventana máxima de consolidación es de %s días.", MAX_WINDOW_DAYS)
                    )

    def _assert_permissions(self):
        self.ensure_one()
        if not self.env.user.has_group("ebinox_test_horas.group_test_horas_manager"):
            raise AccessError(_("Se requiere el rol Administrador funcional de Test de Horas."))

    def _event_domain(self):
        self.ensure_one()
        return [
            ("company_id", "=", self.company_id.id),
            ("timestamp", ">=", self.date_from),
            ("timestamp", "<=", self.date_to),
        ]

    def action_preview(self):
        self.ensure_one()
        self._assert_staging()
        self._assert_permissions()
        count = self.env["test.horas.clock.event"].search_count(self._event_domain())
        self.write(
            {
                "state": "previewed",
                "preview_event_count": count,
                "operations_log": "Lectura: test.horas.clock.event.search_count; escrituras estándar: 0",
            }
        )
        return True

    def action_consolidate(self):
        self.ensure_one()
        self._assert_staging()
        self._assert_permissions()
        if self.state not in {"draft", "previewed"}:
            raise UserError(_("Esta corrida ya fue ejecutada."))

        started_at = fields.Datetime.now()
        event_model = self.env["test.horas.clock.event"]
        source_events = event_model.search(self._event_domain(), order="timestamp, id")
        events = self._current_event_versions(source_events)
        grouped = defaultdict(list)
        schedules = {}
        unresolved = set()
        for event in events:
            employee = event.employee_id
            calendar = employee.resource_calendar_id
            local_mark, zone_name = self._local_mark(event.timestamp, calendar)
            work_date, schedule = self._resolve_operational_date(local_mark, calendar)
            key = (employee.id, work_date)
            grouped[key].append(event.id)
            if schedule:
                schedules[key] = (schedule, zone_name, calendar)
            else:
                unresolved.add(key)

        created = 0
        updated = 0
        workday_model = self.env["test.horas.workday"]
        for key, grouped_event_ids in grouped.items():
            employee_id, work_date = key
            day_events = event_model.browse(grouped_event_ids).sorted(
                key=lambda event: (event.timestamp, event.id)
            )
            first_mark = day_events[0].timestamp
            last_mark = day_events[-1].timestamp if len(day_events) > 1 else False
            schedule_info = schedules.get(key)
            values = {
                "employee_id": employee_id,
                "operational_date": work_date,
                "clock_event_ids": [(6, 0, day_events.ids)],
                "first_mark": first_mark,
                "last_mark": last_mark,
                "mark_count": len(day_events),
            }
            if schedule_info:
                schedule, zone_name, calendar = schedule_info
                values.update(
                    {
                        "declared_calendar_id": calendar.id,
                        "effective_calendar_id": calendar.id,
                        "schedule_start_hour": schedule.start.hour + schedule.start.minute / 60.0,
                        "schedule_end_hour": schedule.end.hour + schedule.end.minute / 60.0,
                        "schedule_timezone": zone_name,
                        "schedule_snapshot_source": "resource_calendar",
                        "schedule_segments_json": self._serialize_schedule_segments(schedule),
                        "warning_code": False,
                        "warning_detail": False,
                    }
                )
            else:
                values.update(
                    {
                        "warning_code": "HORARIO_NO_RESUELTO",
                        "warning_detail": "No se pudo obtener un tramo simple del calendario Odoo.",
                    }
                )

            workday = workday_model.search(
                [("employee_id", "=", employee_id), ("operational_date", "=", work_date)],
                limit=1,
            )
            if workday:
                if workday.state == "closed":
                    raise UserError(
                        _("No se puede actualizar la jornada cerrada %(employee)s / %(date)s.", employee=workday.employee_id.name, date=work_date)
                    )
                if workday.state not in {"imported", "review"}:
                    values["state"] = "review"
                    values["warning_code"] = "RECALCULO_REQUERIDO"
                    values["warning_detail"] = "Cambió la evidencia de una jornada previamente procesada."
                workday.with_context(test_horas_import=True).write(values)
                updated += 1
            else:
                workday_model.with_context(test_horas_import=True).create(values)
                created += 1

        finished_at = fields.Datetime.now()
        self.write(
            {
                "state": "done",
                "events_read": len(source_events),
                "superseded_events_ignored": len(source_events) - len(events),
                "workdays_created": created,
                "workdays_updated": updated,
                "unresolved_schedule_days": len(unresolved),
                "executed_by_id": self.env.user.id,
                "started_at": started_at,
                "finished_at": finished_at,
                "operations_log": (
                    "Lecturas estándar: hr.employee.resource_calendar_id y resource.calendar.attendance_ids. "
                    "Escrituras estándar: 0. Destino: test.horas.workday."
                ),
            }
        )
        self._log_test_horas_event(
            "workdays.consolidated",
            "Fichadas privadas consolidadas en jornadas",
            {
                "events_read": len(source_events),
                "workdays_created": created,
                "workdays_updated": updated,
                "unresolved_schedule_days": len(unresolved),
                "writes_standard": 0,
            },
        )
        return True

    def _current_event_versions(self, events):
        self.ensure_one()
        selected = {}
        passthrough = []
        for event in events:
            if event.source != "odoo_hr_attendance":
                passthrough.append(event)
                continue
            try:
                payload = json.loads(event.source_payload or "{}")
                key = (event.source, int(payload["record_id"]), str(payload["event_kind"]))
            except (ValueError, TypeError, KeyError, json.JSONDecodeError):
                passthrough.append(event)
                continue
            previous = selected.get(key)
            if not previous or (event.imported_at, event.id) > (previous.imported_at, previous.id):
                selected[key] = event
        kept_ids = [event.id for event in passthrough]
        kept_ids.extend(event.id for event in selected.values())
        return (
            self.env["test.horas.clock.event"]
            .browse(kept_ids)
            .sorted(key=lambda event: (event.timestamp, event.id))
        )

    def _local_mark(self, value, calendar):
        self.ensure_one()
        zone_name = getattr(calendar, "tz", False) or self.env.user.tz or "UTC"
        try:
            zone = ZoneInfo(zone_name)
        except ZoneInfoNotFoundError as exc:
            raise ValidationError(_("Zona horaria desconocida: %s", zone_name)) from exc
        mark = fields.Datetime.to_datetime(value).replace(tzinfo=timezone.utc)
        return mark.astimezone(zone).replace(tzinfo=None), zone_name

    def _resolve_operational_date(self, local_mark, calendar):
        self.ensure_one()
        if not calendar:
            return local_mark.date(), None
        previous_date = local_mark.date() - timedelta(days=1)
        previous_schedule = self._schedule_for_date(calendar, previous_date)
        if previous_schedule and previous_schedule.crosses_midnight:
            candidate = operational_date(
                local_mark,
                previous_schedule,
                declared_night=True,
                previous_day_expected=True,
            )
            if candidate == previous_date:
                return previous_date, previous_schedule
        current_schedule = self._schedule_for_date(calendar, local_mark.date())
        if not current_schedule:
            return local_mark.date(), None
        return (
            operational_date(
                local_mark,
                current_schedule,
                declared_night=current_schedule.crosses_midnight,
                previous_day_expected=bool(previous_schedule),
            ),
            current_schedule,
        )

    def _schedule_for_date(self, calendar, work_date):
        self.ensure_one()
        lines = self._calendar_lines_for_date(calendar, work_date)
        if not lines:
            return None
        direct_cross = lines.filtered(lambda line: line.hour_to <= line.hour_from)
        if direct_cross:
            selected = direct_cross.sorted(key=lambda line: (line.hour_from, line.id))
        else:
            late = lines.filtered(lambda line: line.hour_from >= 12.0 and line.hour_to >= 23.5)
            early_next = self._calendar_lines_for_date(
                calendar, work_date + timedelta(days=1)
            ).filtered(lambda line: line.hour_from < 12.0)
            selected = (
                (late | early_next).sorted(
                    key=lambda line: (0 if line in late else 1, line.hour_from, line.id)
                )
                if late and early_next
                else lines.sorted(key=lambda line: (line.hour_from, line.id))
            )
        segments = tuple(
            (self._calendar_float_to_time(line.hour_from), self._calendar_float_to_time(line.hour_to))
            for line in selected
        )
        return Schedule(segments[0][0], segments[-1][1], segments=segments)

    @staticmethod
    def _serialize_schedule_segments(schedule):
        return json.dumps(
            [
                {"start": start.isoformat(), "end": end.isoformat()}
                for start, end in schedule.segments
            ],
            sort_keys=True,
        )

