import hashlib
import json
from datetime import time, timedelta, timezone
from zoneinfo import ZoneInfo, ZoneInfoNotFoundError

from odoo import _, fields, models
from odoo.exceptions import ValidationError

from ..engine import (
    AttendanceInput,
    DayRegime,
    EnginePolicy,
    SaturdayRule,
    Schedule,
    TardinessRule,
    compute_ordinary,
    compute_overtime,
)


CALCULATION_VERSION = "2026-08-21.odoo19.v2.multisegment"


class TestHorasWorkdayCalculation(models.Model):
    _inherit = "test.horas.workday"

    schedule_start_hour = fields.Float(
        string="Inicio horario (local)", digits=(5, 2), help="Snapshot decimal, por ejemplo 8.0."
    )
    schedule_end_hour = fields.Float(
        string="Fin horario (local)", digits=(5, 2), help="Snapshot decimal; un valor menor o igual al inicio cruza medianoche."
    )
    schedule_timezone = fields.Char(string="Zona horaria del cálculo", default="America/Argentina/Buenos_Aires")
    schedule_snapshot_source = fields.Selection(
        [("manual", "Manual"), ("resource_calendar", "Calendario Odoo")],
        default="manual",
        required=True,
    )
    schedule_segments_json = fields.Text(string="Tramos horarios (snapshot)", readonly=True)

    day_regime = fields.Selection(
        [
            ("auto", "Automático por día"),
            ("laborable", "Laborable"),
            ("sabado", "Sábado"),
            ("domingo", "Domingo"),
            ("feriado", "Feriado"),
        ],
        required=True,
        default="auto",
    )
    assume_theoretical = fields.Boolean(string="Asumir jornada teórica")
    justified_absence = fields.Boolean(string="Ausencia justificada sin marcas")
    overtime_authorized = fields.Boolean(
        string="Extras autorizadas",
        default=False,
        help="Falla de forma segura: sin autorización explícita no hay extras liquidables.",
    )
    overtime_excluded = fields.Boolean(string="Excluir extras del día")
    overtime_exclusion_reason = fields.Char(string="Motivo de exclusión")
    tardiness_policy = fields.Selection(
        [
            ("actual_primera_hora_mayor_20", "Vigente: primera hora si supera 20 min"),
            ("minuto_a_minuto", "Alternativa: minuto a minuto"),
        ],
        required=True,
        default="actual_primera_hora_mayor_20",
    )
    saturday_policy = fields.Selection(
        [
            ("oficial_general", "Regla general vigente"),
            ("cde_567_documentada", "CDE horarios 5/6/7 documentada"),
        ],
        required=True,
        default="oficial_general",
    )
    rule_company_code = fields.Char(string="Código de empresa para reglas")
    schedule_code = fields.Integer(string="Código de horario para reglas")
    first_hour_penalty_min = fields.Integer(readonly=True)
    raw_50_diurnal_min = fields.Integer(readonly=True)
    raw_50_nocturnal_min = fields.Integer(readonly=True)
    raw_100_diurnal_min = fields.Integer(readonly=True)
    raw_100_nocturnal_min = fields.Integer(readonly=True)
    unliquidated_overtime_min = fields.Integer(readonly=True)
    calculation_input_hash = fields.Char(readonly=True, index=True)
    calculation_input_snapshot = fields.Text(readonly=True)

    def action_snapshot_schedule(self):
        for record in self:
            record._assert_staging()
            calendar = record.effective_calendar_id or record.declared_calendar_id
            if not calendar:
                raise ValidationError(_("La jornada no tiene un calendario declarado o efectivo."))
            schedule = record._schedule_from_calendar(calendar, record.operational_date)
            record.write(
                {
                    "schedule_start_hour": schedule.start.hour + schedule.start.minute / 60.0,
                    "schedule_end_hour": schedule.end.hour + schedule.end.minute / 60.0,
                    "schedule_timezone": getattr(calendar, "tz", False)
                    or record.env.user.tz
                    or "UTC",
                    "schedule_snapshot_source": "resource_calendar",
                    "schedule_segments_json": record._serialize_schedule_segments(schedule),
                }
            )
        return True

    def _schedule_from_calendar(self, calendar, work_date):
        lines = self._calendar_lines_for_date(calendar, work_date)
        if not lines:
            raise ValidationError(_("El calendario no tiene tramos laborables para la fecha operativa."))
        direct_cross = lines.filtered(lambda line: line.hour_to <= line.hour_from)
        if direct_cross:
            selected = direct_cross.sorted(key=lambda line: (line.hour_from, line.id))
        else:
            late = lines.filtered(lambda line: line.hour_from >= 12.0 and line.hour_to >= 23.5)
            early_next = self._calendar_lines_for_date(
                calendar, work_date + timedelta(days=1)
            ).filtered(lambda line: line.hour_from < 12.0)
            selected = (late | early_next).sorted(
                key=lambda line: (0 if line in late else 1, line.hour_from, line.id)
            ) if late and early_next else lines.sorted(key=lambda line: (line.hour_from, line.id))
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

    def action_calculate_test_horas(self):
        for record in self:
            record._calculate_test_horas_one()
        return True

    def _calculate_test_horas_one(self):
        self.ensure_one()
        self._assert_staging()
        schedule_start = self._decimal_hour_to_time(self.schedule_start_hour, "inicio")
        schedule_end = self._decimal_hour_to_time(self.schedule_end_hour, "fin")
        if schedule_start == schedule_end:
            raise ValidationError(
                _("La hora de inicio y fin no pueden ser iguales; capture un horario válido antes de calcular.")
            )
        segments = self._parsed_schedule_segments(schedule_start, schedule_end)
        schedule = Schedule(schedule_start, schedule_end, segments=segments)
        first_mark = self._to_local_naive(self.effective_first_mark)
        last_mark = self._to_local_naive(self.effective_last_mark)
        regime = self._resolved_day_regime()
        policy = EnginePolicy(
            tardiness_rule=TardinessRule(self.tardiness_policy),
            saturday_rule=SaturdayRule(self.saturday_policy),
        )
        attendance = AttendanceInput(
            work_date=self.operational_date,
            schedule=schedule,
            first_mark=first_mark,
            last_mark=last_mark,
            count_marks=self.mark_count,
            assume_theoretical=self.assume_theoretical,
            justified_absence=self.justified_absence,
            corrected_marks=bool(self.corrected_first_mark or self.corrected_last_mark),
        )
        ordinary = compute_ordinary(attendance, policy)
        overtime = compute_overtime(
            attendance,
            ordinary,
            regime,
            authorized=self.overtime_authorized,
            excluded=self.overtime_excluded,
            company=(self.rule_company_code or self.company_id.name or ""),
            schedule_code=self.schedule_code or None,
            policy=policy,
        )
        snapshot = self._calculation_snapshot(regime, schedule, first_mark, last_mark)
        encoded = json.dumps(snapshot, sort_keys=True, separators=(",", ":"), ensure_ascii=True)
        self.write(
            {
                "ordinary_diurnal_min": ordinary.ordinary_diurnal_min,
                "ordinary_nocturnal_min": ordinary.ordinary_nocturnal_min,
                "tardiness_min": ordinary.tardiness_min,
                "first_hour_penalty_min": ordinary.first_hour_penalty_min,
                "detected_overtime_min": overtime.detected_excess_min,
                "raw_50_diurnal_min": overtime.raw_50_diurnal_min,
                "raw_50_nocturnal_min": overtime.raw_50_nocturnal_min,
                "raw_100_diurnal_min": overtime.raw_100_diurnal_min,
                "raw_100_nocturnal_min": overtime.raw_100_nocturnal_min,
                "payable_50_diurnal_min": overtime.payable_50_diurnal_min,
                "payable_50_nocturnal_min": overtime.payable_50_nocturnal_min,
                "payable_100_diurnal_min": overtime.payable_100_diurnal_min,
                "payable_100_nocturnal_min": overtime.payable_100_nocturnal_min,
                "unliquidated_overtime_min": overtime.unliquidated_min,
                "calculation_version": CALCULATION_VERSION,
                "calculation_input_hash": hashlib.sha256(encoded.encode("ascii")).hexdigest(),
                "calculation_input_snapshot": json.dumps(snapshot, sort_keys=True, ensure_ascii=False),
                "calculated_at": fields.Datetime.now(),
                "calculated_by_id": self.env.user.id,
                "state": "calculated",
            }
        )
        self._log_test_horas_event(
            "workday.calculated",
            "Jornada calculada",
            {
                "date": self.operational_date,
                "version": CALCULATION_VERSION,
                "input_hash": self.calculation_input_hash,
                "detected_overtime_min": self.detected_overtime_min,
            },
        )

    def _parsed_schedule_segments(self, schedule_start, schedule_end):
        if not self.schedule_segments_json:
            return ((schedule_start, schedule_end),)
        try:
            payload = json.loads(self.schedule_segments_json)
            segments = tuple(
                (time.fromisoformat(item["start"]), time.fromisoformat(item["end"]))
                for item in payload
            )
        except (TypeError, ValueError, KeyError, json.JSONDecodeError) as exc:
            raise ValidationError(_("El snapshot de tramos horarios no es válido.")) from exc
        if not segments or segments[0][0] != schedule_start or segments[-1][1] != schedule_end:
            raise ValidationError(_("Los tramos no coinciden con el inicio y fin del horario snapshot."))
        return segments
    def _resolved_day_regime(self):
        self.ensure_one()
        if self.day_regime != "auto":
            return DayRegime(self.day_regime)
        weekday = self.operational_date.weekday()
        if weekday == 5:
            return DayRegime.SATURDAY
        if weekday == 6:
            return DayRegime.SUNDAY
        return DayRegime.WORKDAY

    def _to_local_naive(self, value):
        self.ensure_one()
        if not value:
            return None
        value = fields.Datetime.to_datetime(value)
        try:
            zone = ZoneInfo(self.schedule_timezone or "UTC")
        except ZoneInfoNotFoundError as exc:
            raise ValidationError(_("Zona horaria desconocida: %s", self.schedule_timezone)) from exc
        aware_utc = value.replace(tzinfo=timezone.utc)
        return aware_utc.astimezone(zone).replace(tzinfo=None)

    @staticmethod
    def _decimal_hour_to_time(value, label):
        if value is False or value is None:
            raise ValidationError(_("Falta la hora de %s del horario.", label))
        numeric = float(value)
        if numeric < 0 or numeric >= 24:
            raise ValidationError(_("La hora de %s debe estar entre 0 y menos de 24.", label))
        total_minutes = int(round(numeric * 60))
        if total_minutes >= 24 * 60:
            total_minutes = 24 * 60 - 1
        return time(total_minutes // 60, total_minutes % 60)

    def _calculation_snapshot(self, regime, schedule, first_mark, last_mark):
        self.ensure_one()
        return {
            "version": CALCULATION_VERSION,
            "workday_id": self.id,
            "employee_id": self.employee_id.id,
            "operational_date": fields.Date.to_string(self.operational_date),
            "schedule_start": schedule.start.isoformat(),
            "schedule_end": schedule.end.isoformat(),
            "schedule_segments": [
                {"start": start.isoformat(), "end": end.isoformat()}
                for start, end in schedule.segments
            ],
            "schedule_timezone": self.schedule_timezone,
            "first_mark_local": first_mark.isoformat() if first_mark else None,
            "last_mark_local": last_mark.isoformat() if last_mark else None,
            "mark_count": self.mark_count,
            "regime": regime.value,
            "authorized": self.overtime_authorized,
            "excluded": self.overtime_excluded,
            "tardiness_policy": self.tardiness_policy,
            "saturday_policy": self.saturday_policy,
            "rule_company_code": self.rule_company_code or self.company_id.name or "",
            "schedule_code": self.schedule_code or None,
            "assume_theoretical": self.assume_theoretical,
            "justified_absence": self.justified_absence,
        }

