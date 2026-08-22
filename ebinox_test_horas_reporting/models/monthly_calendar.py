import calendar
import hashlib
import json
from datetime import date, timedelta
from html import escape

from odoo import _, Command, api, fields, models
from odoo.exceptions import AccessError, UserError, ValidationError


MAX_EMPLOYEES = 500


class TestHorasMonthlyCalendar(models.Model):
    _name = "test.horas.monthly.calendar"
    _description = "Calendario mensual privado de novedades y fichadas"
    _inherit = ["test.horas.staging.guard.mixin"]
    _order = "month desc, id desc"

    name = fields.Char(required=True, default=lambda self: _("Calendario mensual"))
    company_id = fields.Many2one(
        "res.company", required=True, default=lambda self: self.env.company, index=True
    )
    month = fields.Date(
        required=True,
        default=lambda self: fields.Date.context_today(self).replace(day=1),
        index=True,
    )
    employee_ids = fields.Many2many(
        "hr.employee",
        string="Personas",
        domain="[('company_id', '=', company_id)]",
    )
    state = fields.Selection(
        [("draft", "Borrador"), ("done", "Generado")],
        default="draft",
        required=True,
        readonly=True,
        index=True,
    )
    line_ids = fields.One2many(
        "test.horas.monthly.calendar.line", "calendar_id", readonly=True
    )
    matrix_html = fields.Html(readonly=True, sanitize=True)
    employee_count = fields.Integer(readonly=True)
    line_count = fields.Integer(readonly=True)
    pending_count = fields.Integer(readonly=True)
    warning_count = fields.Integer(readonly=True)
    result_hash = fields.Char(readonly=True, index=True)
    generated_by_id = fields.Many2one("res.users", readonly=True)
    generated_at = fields.Datetime(readonly=True)
    operations_log = fields.Text(readonly=True)

    @api.constrains("month")
    def _check_month(self):
        for record in self:
            if record.month and record.month.day != 1:
                raise ValidationError(_("El mes debe informarse con su primer día."))

    @api.constrains("employee_ids", "company_id")
    def _check_employee_companies(self):
        for record in self:
            if any(employee.company_id != record.company_id for employee in record.employee_ids):
                raise ValidationError(_("Todas las personas deben pertenecer a la compañía elegida."))

    @api.model_create_multi
    def create(self, vals_list):
        self._assert_staging()
        return super().create(vals_list)

    def write(self, vals):
        if any(record.state == "done" for record in self) and not self.env.context.get(
            "test_horas_calendar_generate"
        ):
            raise UserError(_("Un calendario generado es un snapshot y no puede modificarse."))
        return super().write(vals)

    def _assert_operator(self):
        if not self.env.user.has_group("ebinox_test_horas.group_test_horas_operator"):
            raise AccessError(_("Se requiere el rol Operador RRHH de Test de Horas."))

    def _month_end(self):
        self.ensure_one()
        last_day = calendar.monthrange(self.month.year, self.month.month)[1]
        return date(self.month.year, self.month.month, last_day)

    def action_load_roster(self):
        self.ensure_one()
        self._assert_staging()
        self._assert_operator()
        if self.state != "draft":
            raise UserError(_("La nómina sólo puede cambiarse antes de generar el calendario."))
        month_end = self._month_end()
        employees = self.env["hr.employee"].with_context(active_test=False).search(
            [("company_id", "=", self.company_id.id)]
        )
        profiles = self.env["test.horas.employee.profile"].search(
            [("employee_id", "in", employees.ids)]
        )
        profile_by_employee = {profile.employee_id.id: profile for profile in profiles}
        selected = employees.filtered(
            lambda employee: self._is_employed_in_month(
                employee, profile_by_employee.get(employee.id), month_end
            )
        )
        if not selected:
            raise UserError(_("No se encontraron personas vigentes para la compañía y mes."))
        if len(selected) > MAX_EMPLOYEES:
            raise ValidationError(
                _("La grilla admite como máximo %s personas por snapshot.", MAX_EMPLOYEES)
            )
        self.write(
            {
                "employee_ids": [Command.set(selected.ids)],
                "operations_log": _(
                    "Nómina leída: %(count)s personas. Escrituras estándar: 0.",
                    count=len(selected),
                ),
            }
        )
        return True

    def _is_employed_in_month(self, employee, profile, month_end):
        if profile:
            if profile.hire_date and profile.hire_date > month_end:
                return False
            if profile.termination_date and profile.termination_date < self.month:
                return False
            return True
        return bool(employee.active)

    def action_generate(self):
        self.ensure_one()
        self._assert_staging()
        self._assert_operator()
        if self.state != "draft" or self.line_ids:
            raise UserError(_("El calendario ya fue generado; cree uno nuevo para recalcular."))
        if not self.employee_ids:
            raise ValidationError(_("Seleccione o cargue al menos una persona."))
        if len(self.employee_ids) > MAX_EMPLOYEES:
            raise ValidationError(
                _("La grilla admite como máximo %s personas por snapshot.", MAX_EMPLOYEES)
            )

        month_end = self._month_end()
        employee_ids = self.employee_ids.ids
        workdays = self.env["test.horas.workday"].search(
            [
                ("employee_id", "in", employee_ids),
                ("operational_date", ">=", self.month),
                ("operational_date", "<=", month_end),
            ]
        )
        novelties = self.env["test.horas.daily.novelty"].search(
            [
                ("employee_id", "in", employee_ids),
                ("date", ">=", self.month),
                ("date", "<=", month_end),
                ("state", "=", "approved"),
            ]
        )
        holidays = self.env["test.horas.holiday"].search(
            [
                ("company_id", "=", self.company_id.id),
                ("date", ">=", self.month),
                ("date", "<=", month_end),
                ("active", "=", True),
            ]
        )
        profiles = self.env["test.horas.employee.profile"].search(
            [("employee_id", "in", employee_ids)]
        )
        profile_by_employee = {profile.employee_id.id: profile for profile in profiles}
        workday_by_key = {
            (workday.employee_id.id, workday.operational_date): workday
            for workday in workdays
        }
        novelty_by_key = {
            (novelty.employee_id.id, novelty.date): novelty for novelty in novelties
        }
        holiday_dates = set(holidays.mapped("date"))
        dates = []
        cursor = self.month
        while cursor <= month_end:
            dates.append(cursor)
            cursor += timedelta(days=1)

        values = []
        snapshot_lines = []
        pending_count = 0
        warning_count = 0
        for employee in self.employee_ids.sorted(key=lambda item: ((item.name or ""), item.id)):
            profile = profile_by_employee.get(employee.id)
            for day in dates:
                workday = workday_by_key.get((employee.id, day))
                novelty = novelty_by_key.get((employee.id, day))
                is_holiday = day in holiday_dates
                in_scope = self._is_day_in_employment(profile, day)
                if in_scope:
                    code, source, presence = self._resolve_day(workday, novelty, is_holiday)
                else:
                    code, source, presence = "", "out_of_scope", False
                warning_code = workday.warning_code if workday else ""
                warning_detail = workday.warning_detail if workday else ""
                if in_scope and not code:
                    pending_count += 1
                if warning_code:
                    warning_count += 1
                ordinary_min = (
                    workday.ordinary_diurnal_min + workday.ordinary_nocturnal_min
                    if workday
                    else 0
                )
                overtime_min = (
                    workday.payable_50_diurnal_min
                    + workday.payable_50_nocturnal_min
                    + workday.payable_100_diurnal_min
                    + workday.payable_100_nocturnal_min
                    if workday
                    else 0
                )
                line = {
                    "calendar_id": self.id,
                    "employee_id": employee.id,
                    "date": day,
                    "code": code or False,
                    "source": source,
                    "workday_id": workday.id if workday else False,
                    "novelty_id": novelty.id if novelty else False,
                    "is_holiday": is_holiday,
                    "in_scope": in_scope,
                    "presence": presence,
                    "ordinary_min": ordinary_min,
                    "payable_overtime_min": overtime_min,
                    "warning_code": warning_code or False,
                    "warning_detail": warning_detail or False,
                    "day_count": 1 if in_scope else 0,
                }
                values.append(line)
                snapshot_lines.append(
                    {
                        "employee_id": employee.id,
                        "date": fields.Date.to_string(day),
                        "code": code,
                        "in_scope": in_scope,
                        "source": source,
                        "workday_id": workday.id if workday else None,
                        "novelty_id": novelty.id if novelty else None,
                        "ordinary_min": ordinary_min,
                        "payable_overtime_min": overtime_min,
                        "warning_code": warning_code or "",
                    }
                )

        lines = self.env["test.horas.monthly.calendar.line"].create(values)
        encoded = json.dumps(snapshot_lines, sort_keys=True, separators=(",", ":"), ensure_ascii=True)
        self.with_context(test_horas_calendar_generate=True).write(
            {
                "state": "done",
                "matrix_html": self._build_matrix_html(dates, lines),
                "employee_count": len(self.employee_ids),
                "line_count": len(lines),
                "pending_count": pending_count,
                "warning_count": warning_count,
                "result_hash": hashlib.sha256(encoded.encode("ascii")).hexdigest(),
                "generated_by_id": self.env.user.id,
                "generated_at": fields.Datetime.now(),
                "operations_log": _(
                    "Snapshot generado: %(employees)s personas, %(days)s celdas, "
                    "%(pending)s pendientes y %(warnings)s alertas. Escrituras estándar: 0.",
                    employees=len(self.employee_ids),
                    days=len(lines),
                    pending=pending_count,
                    warnings=warning_count,
                ),
            }
        )
        self._log_test_horas_event(
            "calendar.generated",
            "Calendario mensual persona por día generado",
            {
                "month": self.month,
                "employee_count": self.employee_count,
                "line_count": self.line_count,
                "result_hash": self.result_hash,
                "writes_standard": 0,
            },
        )
        return True

    @staticmethod
    def _is_day_in_employment(profile, day):
        if not profile:
            return True
        if profile.hire_date and day < profile.hire_date:
            return False
        if profile.termination_date and day > profile.termination_date:
            return False
        return True

    @staticmethod
    def _resolve_day(workday, novelty, is_holiday):
        manual_code = novelty.novelty_type_id.code.upper() if novelty else ""
        presence = bool(
            workday and workday.effective_first_mark and workday.effective_last_mark
        )
        if is_holiday and manual_code in {"", "O"}:
            return ("FT" if presence else "F"), "holiday", presence
        if manual_code:
            return manual_code, "manual", presence
        if presence:
            return "P", "presence", True
        return "", "pending", False

    def _build_matrix_html(self, dates, lines):
        line_by_key = {(line.employee_id.id, line.date): line for line in lines}
        header = "".join("<th>%s</th>" % day.day for day in dates)
        rows = []
        for employee in self.employee_ids.sorted(key=lambda item: ((item.name or ""), item.id)):
            cells = []
            for day in dates:
                line = line_by_key[(employee.id, day)]
                value = escape("—" if line.source == "out_of_scope" else (line.code or "·"))
                title_parts = [line.source]
                if line.warning_code:
                    title_parts.append(line.warning_code)
                if line.warning_detail:
                    title_parts.append(line.warning_detail)
                title = escape(" — ".join(filter(None, title_parts)))
                cells.append('<td title="%s">%s</td>' % (title, value))
            rows.append(
                "<tr><th>%s</th>%s</tr>"
                % (escape(employee.name or str(employee.id)), "".join(cells))
            )
        return (
            '<div class="table-responsive"><table class="table table-sm table-bordered">'
            "<thead><tr><th>Persona</th>%s</tr></thead><tbody>%s</tbody></table></div>"
            % (header, "".join(rows))
        )


class TestHorasMonthlyCalendarLine(models.Model):
    _name = "test.horas.monthly.calendar.line"
    _description = "Celda auditable del calendario mensual privado"
    _inherit = [
        "test.horas.staging.guard.mixin",
        "test.horas.immutable.audit.mixin",
    ]
    _order = "date, employee_id"

    calendar_id = fields.Many2one(
        "test.horas.monthly.calendar", required=True, index=True, ondelete="restrict"
    )
    company_id = fields.Many2one(related="calendar_id.company_id", store=True, index=True)
    employee_id = fields.Many2one("hr.employee", required=True, index=True, ondelete="restrict")
    date = fields.Date(required=True, index=True)
    code = fields.Char(index=True)
    source = fields.Selection(
        [
            ("manual", "Novedad aprobada"),
            ("holiday", "Feriado"),
            ("presence", "Presencia"),
            ("pending", "Pendiente"),
            ("out_of_scope", "Fuera del vínculo"),
        ],
        required=True,
        index=True,
    )
    workday_id = fields.Many2one("test.horas.workday", ondelete="restrict")
    novelty_id = fields.Many2one("test.horas.daily.novelty", ondelete="restrict")
    is_holiday = fields.Boolean(index=True)
    in_scope = fields.Boolean(default=True, index=True)
    presence = fields.Boolean(index=True)
    ordinary_min = fields.Integer()
    payable_overtime_min = fields.Integer()
    warning_code = fields.Char(index=True)
    warning_detail = fields.Text()
    day_count = fields.Integer(default=1, readonly=True)

    _sql_constraints = [
        (
            "calendar_employee_date_unique",
            "unique(calendar_id, employee_id, date)",
            "Ya existe una celda para esa persona y fecha en el calendario.",
        ),
    ]

    @api.model_create_multi
    def create(self, vals_list):
        self._assert_staging()
        return super().create(vals_list)

    def write(self, vals):
        self._raise_immutable()

