import hashlib
import json
from datetime import timedelta

from odoo import _, api, fields, models
from odoo.exceptions import AccessError, UserError, ValidationError


ABSENCE_CODES = {"AI", "AJ", "E", "ART", "L", "LS", "V", "S"}
MAX_WINDOW_DAYS = 62


class TestHorasAbsenteeismRun(models.Model):
    _name = "test.horas.absenteeism.run"
    _description = "Corrida de ausentismo y tardanzas"
    _inherit = ["test.horas.staging.guard.mixin", "test.horas.calendar.resolver.mixin"]
    _order = "create_date desc, id desc"

    name = fields.Char(required=True, default=lambda self: _("Nuevo reporte de ausentismo"))
    company_id = fields.Many2one(
        "res.company", required=True, default=lambda self: self.env.company, index=True
    )
    date_from = fields.Date(required=True)
    date_to = fields.Date(required=True)
    universe = fields.Selection(
        [("all", "Todos"), ("direct", "Directos"), ("indirect", "Indirectos")],
        required=True,
        default="all",
    )
    state = fields.Selection(
        [("draft", "Borrador"), ("done", "Calculado")],
        required=True,
        default="draft",
        readonly=True,
    )
    line_ids = fields.One2many("test.horas.absenteeism.line", "run_id", readonly=True)
    profiles_created = fields.Integer(readonly=True)
    employee_count = fields.Integer(readonly=True)
    expected_person_days = fields.Integer(readonly=True)
    absent_person_days = fields.Integer(readonly=True)
    absenteeism_percentage = fields.Float(readonly=True, digits=(8, 4))
    tardiness_events = fields.Integer(readonly=True)
    excluded_new_hires = fields.Integer(readonly=True)
    unresolved_calendars = fields.Integer(readonly=True)
    result_hash = fields.Char(readonly=True, index=True)
    executed_by_id = fields.Many2one("res.users", readonly=True)
    executed_at = fields.Datetime(readonly=True)
    operations_log = fields.Text(readonly=True)

    @api.model_create_multi
    def create(self, vals_list):
        self._assert_staging()
        return super().create(vals_list)

    @api.constrains("date_from", "date_to")
    def _check_window(self):
        for record in self:
            if record.date_from and record.date_to:
                if record.date_to < record.date_from:
                    raise ValidationError(_("La fecha final no puede ser anterior a la inicial."))
                if record.date_to - record.date_from > timedelta(days=MAX_WINDOW_DAYS):
                    raise ValidationError(_("La ventana máxima es de %s días.", MAX_WINDOW_DAYS))

    def _assert_permissions(self):
        self.ensure_one()
        if not self.env.user.has_group("ebinox_test_horas.group_test_horas_manager"):
            raise AccessError(_("Se requiere el rol Administrador funcional de Test de Horas."))

    def action_prepare_profiles(self):
        self.ensure_one()
        self._assert_staging()
        self._assert_permissions()
        employees = self.env["hr.employee"].search(
            [("company_id", "=", self.company_id.id), ("active", "=", True)]
        )
        existing = set(
            self.env["test.horas.employee.profile"].search(
                [("employee_id", "in", employees.ids)]
            ).mapped("employee_id").ids
        )
        missing = [
            {"employee_id": employee.id, "population_type": "unclassified"}
            for employee in employees
            if employee.id not in existing
        ]
        if missing:
            self.env["test.horas.employee.profile"].create(missing)
        self.profiles_created += len(missing)
        return True

    def action_compute(self):
        self.ensure_one()
        self._assert_staging()
        self._assert_permissions()
        if self.state != "draft" or self.line_ids:
            raise UserError(_("La corrida ya fue calculada; cree una nueva para recalcular."))
        domain = [("company_id", "=", self.company_id.id), ("active", "=", True)]
        if self.universe in {"direct", "indirect"}:
            domain.append(("population_type", "=", self.universe))
        profiles = self.env["test.horas.employee.profile"].search(domain, order="employee_id")
        employee_ids = profiles.mapped("employee_id").ids
        workdays = self.env["test.horas.workday"].search(
            [
                ("employee_id", "in", employee_ids),
                ("operational_date", ">=", self.date_from),
                ("operational_date", "<=", self.date_to),
            ]
        )
        workday_by_key = {(item.employee_id.id, item.operational_date): item for item in workdays}
        novelties = self.env["test.horas.daily.novelty"].search(
            [
                ("employee_id", "in", employee_ids),
                ("date", ">=", self.date_from),
                ("date", "<=", self.date_to),
                ("state", "=", "approved"),
            ]
        )
        novelty_by_key = {(item.employee_id.id, item.date): item for item in novelties}
        holidays = set(
            self.env["test.horas.holiday"].search(
                [
                    ("company_id", "=", self.company_id.id),
                    ("date", ">=", self.date_from),
                    ("date", "<=", self.date_to),
                    ("active", "=", True),
                ]
            ).mapped("date")
        )

        lines = []
        expected_total = 0
        absent_total = 0
        tardiness_total = 0
        excluded_profiles = 0
        unresolved_profiles = 0
        for profile in profiles:
            calendar = profile.employee_id.resource_calendar_id
            if not calendar:
                unresolved_profiles += 1
            excluded_new_hire = self._is_new_hire_excluded(profile, calendar, holidays)
            if excluded_new_hire:
                excluded_profiles += 1
            current = self.date_from
            while current <= self.date_to:
                after_hire = not profile.hire_date or current >= profile.hire_date
                before_or_on_termination = (
                    not profile.termination_date or current <= profile.termination_date
                )
                expected = (
                    after_hire
                    and before_or_on_termination
                    and self._is_expected(calendar, current, holidays)
                )
                workday = workday_by_key.get((profile.employee_id.id, current))
                novelty = novelty_by_key.get((profile.employee_id.id, current))
                code = novelty.novelty_type_id.code if novelty else ""
                if expected and not code and (not workday or workday.mark_count == 0):
                    code = "AI"
                absent = bool(expected and code in ABSENCE_CODES)
                tardiness = workday.tardiness_min if workday else 0
                tardy_event = tardiness > 5
                included = bool(expected and not excluded_new_hire)
                if expected or code or tardy_event:
                    line = {
                        "run_id": self.id,
                        "employee_id": profile.employee_id.id,
                        "profile_id": profile.id,
                        "date": current,
                        "week_start": current - timedelta(days=current.weekday()),
                        "workday_id": workday.id if workday else False,
                        "novelty_id": novelty.id if novelty else False,
                        "novelty_code": code,
                        "expected": expected,
                        "absent": absent,
                        "tardiness_min": tardiness,
                        "tardiness_event": tardy_event,
                        "excluded_new_hire": excluded_new_hire,
                        "included_in_rate": included,
                        "expected_weight": 1 if included else 0,
                        "absence_weight": 1 if included and absent else 0,
                    }
                    lines.append(line)
                    expected_total += line["expected_weight"]
                    absent_total += line["absence_weight"]
                    tardiness_total += 1 if tardy_event else 0
                current += timedelta(days=1)
        if lines:
            self.env["test.horas.absenteeism.line"].create(lines)
        snapshot = {
            "run_id": self.id,
            "company_id": self.company_id.id,
            "date_from": fields.Date.to_string(self.date_from),
            "date_to": fields.Date.to_string(self.date_to),
            "universe": self.universe,
            "employees": len(profiles),
            "expected_person_days": expected_total,
            "absent_person_days": absent_total,
            "tardiness_events": tardiness_total,
            "excluded_new_hires": excluded_profiles,
            "line_count": len(lines),
        }
        encoded = json.dumps(snapshot, sort_keys=True, separators=(",", ":"), ensure_ascii=True)
        self.write(
            {
                "state": "done",
                "employee_count": len(profiles),
                "expected_person_days": expected_total,
                "absent_person_days": absent_total,
                "absenteeism_percentage": (absent_total / expected_total * 100.0)
                if expected_total
                else 0.0,
                "tardiness_events": tardiness_total,
                "excluded_new_hires": excluded_profiles,
                "unresolved_calendars": unresolved_profiles,
                "result_hash": hashlib.sha256(encoded.encode("ascii")).hexdigest(),
                "executed_by_id": self.env.user.id,
                "executed_at": fields.Datetime.now(),
                "operations_log": (
                    "Lecturas estándar: hr.employee y resource.calendar. Escrituras estándar: 0. "
                    "Destino: test.horas.absenteeism.*"
                ),
            }
        )
        return True

    def _is_new_hire_excluded(self, profile, calendar, holidays):
        if not profile.hire_date or profile.hire_date > self.date_to:
            return False
        count = 0
        current = profile.hire_date
        employment_end = min(
            self.date_to, profile.termination_date or self.date_to
        )
        while current <= employment_end:
            if self._is_expected(calendar, current, holidays):
                count += 1
            current += timedelta(days=1)
        return count < 5

    def _is_expected(self, calendar, day, holidays):
        if not calendar or day in holidays:
            return False
        return bool(self._calendar_lines_for_date(calendar, day))


class TestHorasAbsenteeismLine(models.Model):
    _name = "test.horas.absenteeism.line"
    _description = "Detalle de ausentismo y tardanza"
    _order = "date, employee_id"

    run_id = fields.Many2one("test.horas.absenteeism.run", required=True, index=True, ondelete="cascade")
    company_id = fields.Many2one(related="run_id.company_id", store=True, index=True)
    employee_id = fields.Many2one("hr.employee", required=True, index=True, ondelete="restrict")
    profile_id = fields.Many2one("test.horas.employee.profile", required=True, ondelete="restrict")
    population_type = fields.Selection(related="profile_id.population_type", store=True, index=True)
    date = fields.Date(required=True, index=True)
    week_start = fields.Date(required=True, index=True)
    workday_id = fields.Many2one("test.horas.workday", ondelete="restrict")
    novelty_id = fields.Many2one("test.horas.daily.novelty", ondelete="restrict")
    novelty_code = fields.Char(index=True)
    expected = fields.Boolean()
    absent = fields.Boolean()
    tardiness_min = fields.Integer()
    tardiness_event = fields.Boolean(index=True)
    excluded_new_hire = fields.Boolean(index=True)
    included_in_rate = fields.Boolean(index=True)
    expected_weight = fields.Integer()
    absence_weight = fields.Integer()

