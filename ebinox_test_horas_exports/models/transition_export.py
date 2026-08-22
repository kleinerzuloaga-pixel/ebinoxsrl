import base64
import csv
import hashlib
import io
import json
from collections import Counter, defaultdict
from datetime import timedelta

from odoo import _, api, fields, models
from odoo.exceptions import AccessError, UserError, ValidationError


NOVELTY_CODES = ("P", "AJ", "AI", "S", "E", "V", "ART", "O", "D", "L", "LS", "F", "FT")
MAX_WINDOW_DAYS = 62


class TestHorasTransitionExport(models.Model):
    _name = "test.horas.transition.export"
    _description = "Exportación diagnóstica de transición"
    _inherit = ["test.horas.staging.guard.mixin"]
    _order = "create_date desc, id desc"

    name = fields.Char(required=True, default=lambda self: _("Nueva exportación"))
    company_id = fields.Many2one(
        "res.company", required=True, default=lambda self: self.env.company, index=True
    )
    export_type = fields.Selection(
        [
            ("nov_daily", "NOV - detalle diario"),
            ("nov_calendar", "NOVCAL - calendario"),
            ("nov_summary", "NOV - resumen diagnóstico"),
            ("overtime", "EXTRAS - detalle autorizado"),
            ("valuation", "Val - valorización"),
            ("reassignments", "REASIG - correcciones de jornada"),
            ("monthly_close", "Cierres mensuales"),
        ],
        required=True,
        default="nov_daily",
        index=True,
    )
    date_from = fields.Date()
    date_to = fields.Date()
    period_id = fields.Many2one("test.horas.overtime.period", ondelete="restrict")
    state = fields.Selection(
        [("draft", "Borrador"), ("generated", "Generado")],
        required=True,
        default="draft",
        readonly=True,
        index=True,
    )
    file_data = fields.Binary(readonly=True, attachment=False)
    file_name = fields.Char(readonly=True)
    row_count = fields.Integer(readonly=True)
    content_sha256 = fields.Char(readonly=True, index=True)
    source_snapshot = fields.Text(readonly=True)
    generated_by_id = fields.Many2one("res.users", readonly=True)
    generated_at = fields.Datetime(readonly=True)
    format_note = fields.Text(readonly=True)

    @api.model_create_multi
    def create(self, vals_list):
        self._assert_staging()
        return super().create(vals_list)

    @api.constrains("date_from", "date_to", "export_type", "period_id")
    def _check_parameters(self):
        for record in self:
            if record.export_type in {"overtime", "valuation"}:
                if not record.period_id:
                    raise ValidationError(_("EXTRAS y Val requieren un período de horas extra."))
                if record.period_id.company_id != record.company_id:
                    raise ValidationError(_("El período pertenece a otra compañía."))
            else:
                if not record.date_from or not record.date_to:
                    raise ValidationError(_("El tipo seleccionado requiere fecha inicial y final."))
                if record.date_to < record.date_from:
                    raise ValidationError(_("La fecha final no puede ser anterior a la inicial."))
                if record.date_to - record.date_from > timedelta(days=MAX_WINDOW_DAYS):
                    raise ValidationError(_("La ventana máxima es de %s días.", MAX_WINDOW_DAYS))

    def write(self, vals):
        if any(record.state == "generated" for record in self) and not self.env.context.get(
            "test_horas_export_generation"
        ):
            raise UserError(_("Una exportación generada es inmutable; cree una nueva corrida."))
        return super().write(vals)

    def unlink(self):
        if any(record.state == "generated" for record in self):
            raise UserError(_("Una exportación generada no puede eliminarse."))
        return super().unlink()

    def action_generate(self):
        self.ensure_one()
        self._assert_staging()
        if not self.env.user.has_group("ebinox_test_horas.group_test_horas_manager"):
            raise AccessError(_("Se requiere el rol Administrador funcional de Test de Horas."))
        if self.state != "draft":
            raise UserError(_("La exportación ya fue generada."))
        generators = {
            "nov_daily": self._generate_nov_daily,
            "nov_calendar": self._generate_nov_calendar,
            "nov_summary": self._generate_nov_summary,
            "overtime": self._generate_overtime,
            "valuation": self._generate_valuation,
            "reassignments": self._generate_reassignments,
            "monthly_close": self._generate_monthly_close,
        }
        headers, rows, source_ids = generators[self.export_type]()
        text = self._csv_text(headers, rows)
        raw = text.encode("utf-8-sig")
        snapshot = {
            "export_id": self.id,
            "type": self.export_type,
            "company_id": self.company_id.id,
            "date_from": fields.Date.to_string(self.date_from) if self.date_from else None,
            "date_to": fields.Date.to_string(self.date_to) if self.date_to else None,
            "period_id": self.period_id.id or None,
            "row_count": len(rows),
            "source_ids": source_ids,
        }
        self.with_context(test_horas_export_generation=True).write(
            {
                "state": "generated",
                "file_data": base64.b64encode(raw),
                "file_name": self._file_name(),
                "row_count": len(rows),
                "content_sha256": hashlib.sha256(raw).hexdigest(),
                "source_snapshot": json.dumps(snapshot, sort_keys=True, ensure_ascii=False),
                "generated_by_id": self.env.user.id,
                "generated_at": fields.Datetime.now(),
                "format_note": (
                    "CSV UTF-8 con BOM, separador punto y coma. Salida diagnóstica; "
                    "no constituye liquidación ni modifica módulos estándar."
                ),
            }
        )
        self._log_test_horas_event(
            "export.generated",
            "Exportación transitoria generada",
            {
                "export_type": self.export_type,
                "row_count": len(rows),
                "content_sha256": self.content_sha256,
                "writes_standard": 0,
            },
        )
        return True

    def _workdays(self):
        return self.env["test.horas.workday"].search(
            [
                ("company_id", "=", self.company_id.id),
                ("operational_date", ">=", self.date_from),
                ("operational_date", "<=", self.date_to),
            ],
            order="employee_id, operational_date",
        )

    def _approved_novelties(self):
        return self.env["test.horas.daily.novelty"].search(
            [
                ("company_id", "=", self.company_id.id),
                ("date", ">=", self.date_from),
                ("date", "<=", self.date_to),
                ("state", "=", "approved"),
            ]
        )

    @staticmethod
    def _employee_values(employee):
        return [employee.id, employee.identification_id or "", employee.name or "", employee.company_id.name or ""]

    def _generate_nov_daily(self):
        workdays = self._workdays()
        novelties = self._approved_novelties()
        novelty_by_key = {(item.employee_id.id, item.date): item for item in novelties}
        headers = [
            "employee_id", "identification_id", "employee_name", "company", "date", "fortnight",
            "workday_state", "novelty_code", "mark_count", "effective_first_mark_utc",
            "effective_last_mark_utc", "schedule_start_hour", "schedule_end_hour", "schedule_timezone",
            "ordinary_diurnal_min", "ordinary_nocturnal_min", "tardiness_min", "detected_overtime_min",
            "payable_50_diurnal_min", "payable_50_nocturnal_min", "payable_100_diurnal_min",
            "payable_100_nocturnal_min", "calculation_version", "warning_code", "warning_detail",
        ]
        rows = []
        for day in workdays:
            novelty = novelty_by_key.get((day.employee_id.id, day.operational_date))
            code = novelty.novelty_type_id.code if novelty else ("P" if day.mark_count >= 2 else "")
            rows.append(
                self._employee_values(day.employee_id)
                + [
                    fields.Date.to_string(day.operational_date),
                    1 if day.operational_date.day <= 15 else 2,
                    day.state,
                    code,
                    day.mark_count,
                    fields.Datetime.to_string(day.effective_first_mark) if day.effective_first_mark else "",
                    fields.Datetime.to_string(day.effective_last_mark) if day.effective_last_mark else "",
                    day.schedule_start_hour,
                    day.schedule_end_hour,
                    day.schedule_timezone or "",
                    day.ordinary_diurnal_min,
                    day.ordinary_nocturnal_min,
                    day.tardiness_min,
                    day.detected_overtime_min,
                    day.payable_50_diurnal_min,
                    day.payable_50_nocturnal_min,
                    day.payable_100_diurnal_min,
                    day.payable_100_nocturnal_min,
                    day.calculation_version or "",
                    day.warning_code or "",
                    day.warning_detail or "",
                ]
            )
        return headers, rows, {"workday_ids": workdays.ids, "novelty_ids": novelties.ids}

    def _generate_nov_calendar(self):
        workdays = self._workdays()
        novelties = self._approved_novelties()
        workday_by_key = {(item.employee_id.id, item.operational_date): item for item in workdays}
        novelty_by_key = {(item.employee_id.id, item.date): item for item in novelties}
        employee_set = workdays.mapped("employee_id") | novelties.mapped("employee_id")
        dates = []
        current = self.date_from
        while current <= self.date_to:
            dates.append(current)
            current += timedelta(days=1)
        headers = ["employee_id", "identification_id", "employee_name", "company"] + [
            fields.Date.to_string(day) for day in dates
        ]
        rows = []
        for employee in employee_set.sorted(key=lambda item: (item.name or "", item.id)):
            cells = []
            for day in dates:
                novelty = novelty_by_key.get((employee.id, day))
                workday = workday_by_key.get((employee.id, day))
                if novelty:
                    cells.append(novelty.novelty_type_id.code)
                elif workday and workday.mark_count >= 2:
                    cells.append("P")
                else:
                    cells.append("")
            rows.append(self._employee_values(employee) + cells)
        return headers, rows, {"workday_ids": workdays.ids, "novelty_ids": novelties.ids}

    def _generate_nov_summary(self):
        workdays = self._workdays()
        novelties = self._approved_novelties()
        novelty_by_key = {(item.employee_id.id, item.date): item for item in novelties}
        grouped = defaultdict(list)
        for day in workdays:
            grouped[day.employee_id].append(day)
        headers = [
            "employee_id", "identification_id", "employee_name", "company", "date_from", "date_to",
            "q1_ordinary_min", "q2_ordinary_min", "q1_overtime_min", "q2_overtime_min",
            "tardiness_min", "pending_days",
        ] + ["%s_days" % code for code in NOVELTY_CODES]
        rows = []
        for employee, days in sorted(grouped.items(), key=lambda pair: (pair[0].name or "", pair[0].id)):
            q1_ordinary = q2_ordinary = q1_extra = q2_extra = tardiness = pending = 0
            counts = Counter()
            for day in days:
                first_half = day.operational_date.day <= 15
                ordinary = day.ordinary_diurnal_min + day.ordinary_nocturnal_min
                extra = (
                    day.payable_50_diurnal_min + day.payable_50_nocturnal_min
                    + day.payable_100_diurnal_min + day.payable_100_nocturnal_min
                )
                if first_half:
                    q1_ordinary += ordinary
                    q1_extra += extra
                else:
                    q2_ordinary += ordinary
                    q2_extra += extra
                tardiness += day.tardiness_min
                pending += 1 if day.state not in {"calculated", "audited", "closed"} or day.warning_code else 0
                novelty = novelty_by_key.get((employee.id, day.operational_date))
                code = novelty.novelty_type_id.code if novelty else ("P" if day.mark_count >= 2 else "")
                if code:
                    counts[code] += 1
            rows.append(
                self._employee_values(employee)
                + [
                    fields.Date.to_string(self.date_from), fields.Date.to_string(self.date_to),
                    q1_ordinary, q2_ordinary, q1_extra, q2_extra, tardiness, pending,
                ]
                + [counts[code] for code in NOVELTY_CODES]
            )
        return headers, rows, {"workday_ids": workdays.ids, "novelty_ids": novelties.ids}

    def _generate_overtime(self):
        lines = self.period_id.line_ids.filtered("active").sorted(
            key=lambda item: (item.date, item.employee_id.name or "", item.id)
        )
        headers = [
            "period_id", "period_state", "employee_id", "identification_id", "employee_name", "company",
            "date", "workday_id", "detected_excess_min", "raw_50_diurnal_min", "raw_50_nocturnal_min",
            "raw_100_diurnal_min", "raw_100_nocturnal_min", "payable_50_diurnal_min",
            "payable_50_nocturnal_min", "payable_100_diurnal_min", "payable_100_nocturnal_min",
            "excluded", "exclusion_reason", "approval_reason", "authorization_hash",
        ]
        rows = []
        for line in lines:
            rows.append(
                [self.period_id.id, self.period_id.state]
                + self._employee_values(line.employee_id)
                + [
                    fields.Date.to_string(line.date), line.workday_id.id, line.detected_excess_min,
                    line.raw_50_diurnal_min, line.raw_50_nocturnal_min, line.raw_100_diurnal_min,
                    line.raw_100_nocturnal_min, line.payable_50_diurnal_min, line.payable_50_nocturnal_min,
                    line.payable_100_diurnal_min, line.payable_100_nocturnal_min, line.excluded,
                    line.exclusion_reason or "", self.period_id.approval_reason or "",
                    self.period_id.authorization_input_hash or "",
                ]
            )
        return headers, rows, {"period_id": self.period_id.id, "line_ids": lines.ids}

    def _generate_valuation(self):
        valuations = self.env["test.horas.overtime.valuation"].search(
            [("period_id", "=", self.period_id.id)], order="employee_id, id"
        )
        headers = [
            "period_id", "employee_id", "identification_id", "employee_name", "company", "currency",
            "source_hour_value", "base_factor", "overtime_50_factor", "overtime_100_factor",
            "nocturnal_factor", "amount_50_diurnal", "amount_50_nocturnal", "amount_100_diurnal",
            "amount_100_nocturnal", "raw_amount", "rounded_amount", "state", "authorization_reference",
            "payment_reference", "rule_version", "valuation_hash",
        ]
        rows = []
        for valuation in valuations:
            rows.append(
                [self.period_id.id]
                + self._employee_values(valuation.employee_id)
                + [
                    valuation.currency_id.name or "", valuation.source_hour_value, valuation.base_factor,
                    valuation.overtime_50_factor, valuation.overtime_100_factor, valuation.nocturnal_factor,
                    valuation.amount_50_diurnal, valuation.amount_50_nocturnal,
                    valuation.amount_100_diurnal, valuation.amount_100_nocturnal, valuation.raw_amount,
                    valuation.rounded_amount, valuation.state, valuation.authorization_reference or "",
                    valuation.payment_reference or "", valuation.rule_version,
                    valuation.valuation_input_hash or "",
                ]
            )
        return headers, rows, {"period_id": self.period_id.id, "valuation_ids": valuations.ids}

    def _generate_reassignments(self):
        adjustments = self.env["test.horas.workday.adjustment"].search(
            [
                ("company_id", "=", self.company_id.id),
                ("workday_id.operational_date", ">=", self.date_from),
                ("workday_id.operational_date", "<=", self.date_to),
            ],
            order="workday_id, created_at, id",
        )
        headers = [
            "adjustment_id", "workday_id", "employee_id", "identification_id", "employee_name",
            "company", "operational_date", "previous_calendar", "new_calendar",
            "previous_first_mark", "new_first_mark", "previous_last_mark", "new_last_mark",
            "absorbed_into_previous_day", "reason", "created_by", "created_at",
        ]
        rows = []
        for adjustment in adjustments:
            rows.append(
                [adjustment.id, adjustment.workday_id.id]
                + self._employee_values(adjustment.employee_id)
                + [
                    fields.Date.to_string(adjustment.workday_id.operational_date),
                    adjustment.previous_calendar_id.display_name or "",
                    adjustment.new_calendar_id.display_name or "",
                    fields.Datetime.to_string(adjustment.previous_first_mark) if adjustment.previous_first_mark else "",
                    fields.Datetime.to_string(adjustment.new_first_mark) if adjustment.new_first_mark else "",
                    fields.Datetime.to_string(adjustment.previous_last_mark) if adjustment.previous_last_mark else "",
                    fields.Datetime.to_string(adjustment.new_last_mark) if adjustment.new_last_mark else "",
                    adjustment.absorbed_into_previous_day,
                    adjustment.reason,
                    adjustment.created_by_id.display_name or "",
                    fields.Datetime.to_string(adjustment.created_at),
                ]
            )
        return headers, rows, {"adjustment_ids": adjustments.ids}
    def _generate_monthly_close(self):
        closes = self.env["test.horas.monthly.close"].search(
            [
                ("company_id", "=", self.company_id.id),
                ("month", ">=", self.date_from.replace(day=1)),
                ("month", "<=", self.date_to),
            ],
            order="month, employee_id",
        )
        headers = [
            "close_id", "employee_id", "identification_id", "employee_name", "company", "month", "state",
            "ordinary_diurnal_min", "ordinary_nocturnal_min", "tardiness_min", "overtime_50_diurnal_min",
            "overtime_50_nocturnal_min", "overtime_100_diurnal_min", "overtime_100_nocturnal_min",
            "pending_workdays", "novelty_summary", "calculation_versions", "close_hash",
        ]
        rows = []
        for close in closes:
            rows.append(
                [close.id]
                + self._employee_values(close.employee_id)
                + [
                    fields.Date.to_string(close.month), close.state, close.ordinary_diurnal_min,
                    close.ordinary_nocturnal_min, close.tardiness_min, close.overtime_50_diurnal_min,
                    close.overtime_50_nocturnal_min, close.overtime_100_diurnal_min,
                    close.overtime_100_nocturnal_min, close.pending_workdays, close.novelty_summary or "",
                    close.calculation_versions or "", close.close_hash or "",
                ]
            )
        return headers, rows, {"close_ids": closes.ids}

    @staticmethod
    def _csv_text(headers, rows):
        buffer = io.StringIO(newline="")
        writer = csv.writer(buffer, delimiter=";", quoting=csv.QUOTE_MINIMAL, lineterminator="\r\n")
        writer.writerow(headers)
        writer.writerows(rows)
        return buffer.getvalue()

    def _file_name(self):
        self.ensure_one()
        suffix = self.period_id.name if self.period_id else "%s_%s" % (self.date_from, self.date_to)
        safe = "".join(character if character.isalnum() or character in "-_" else "_" for character in str(suffix))
        return "test_horas_%s_%s.csv" % (self.export_type, safe)

