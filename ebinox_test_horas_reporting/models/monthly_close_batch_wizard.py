import calendar
from datetime import date

from odoo import _, Command, api, fields, models
from odoo.exceptions import AccessError, UserError, ValidationError


class TestHorasMonthlyCloseBatchWizard(models.TransientModel):
    _name = "test.horas.monthly.close.batch.wizard"
    _description = "Preparación y cierre mensual masivo aislado"
    _inherit = ["test.horas.staging.guard.mixin"]

    company_id = fields.Many2one(
        "res.company", required=True, default=lambda self: self.env.company
    )
    month = fields.Date(required=True, default=lambda self: fields.Date.context_today(self).replace(day=1))
    employee_ids = fields.Many2many(
        "hr.employee",
        string="Personas",
        domain="[('company_id', '=', company_id)]",
    )
    audit_note = fields.Text(
        help="Obligatoria para revisar los cierres calculados antes del cierre definitivo."
    )
    state = fields.Selection(
        [("draft", "Borrador"), ("prepared", "Preparado"), ("done", "Cerrado")],
        default="draft",
        readonly=True,
    )
    selected_count = fields.Integer(readonly=True)
    created_count = fields.Integer(readonly=True)
    computed_count = fields.Integer(readonly=True)
    closed_count = fields.Integer(readonly=True)
    skipped_count = fields.Integer(readonly=True)
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

    def _assert_auditor(self):
        if not self.env.user.has_group("ebinox_test_horas.group_test_horas_auditor"):
            raise AccessError(_("Se requiere el rol Auditor de Test de Horas."))

    def _assert_employees(self):
        if not self.employee_ids:
            raise ValidationError(_("Seleccione o cargue al menos una persona."))

    def _month_end(self):
        self.ensure_one()
        last_day = calendar.monthrange(self.month.year, self.month.month)[1]
        return date(self.month.year, self.month.month, last_day)

    def action_load_roster(self):
        self.ensure_one()
        self._assert_staging()
        self._assert_auditor()
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
        self.write(
            {
                "employee_ids": [Command.set(selected.ids)],
                "selected_count": len(selected),
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

    def action_prepare(self):
        self.ensure_one()
        self._assert_staging()
        self._assert_auditor()
        self._assert_employees()
        close_model = self.env["test.horas.monthly.close"]
        closes = close_model.search(
            [("employee_id", "in", self.employee_ids.ids), ("month", "=", self.month)]
        )
        by_employee = {close.employee_id.id: close for close in closes}
        missing_values = [
            {"employee_id": employee.id, "month": self.month}
            for employee in self.employee_ids.sorted(key=lambda item: item.id)
            if employee.id not in by_employee
        ]
        created = close_model.create(missing_values) if missing_values else close_model.browse()
        closes |= created
        computable = closes.filtered(lambda close: close.state in {"draft", "reopened", "computed"})
        skipped = closes - computable
        if computable:
            computable.action_compute()
        self.write(
            {
                "state": "prepared",
                "selected_count": len(self.employee_ids),
                "created_count": len(created),
                "computed_count": len(computable),
                "skipped_count": len(skipped),
                "operations_log": _(
                    "Creados: %(created)s. Calculados: %(computed)s. "
                    "Omitidos por estado revisado/cerrado: %(skipped)s. Escrituras estándar: 0.",
                    created=len(created),
                    computed=len(computable),
                    skipped=len(skipped),
                ),
            }
        )
        return self._close_action(closes)

    def action_review_and_close(self):
        self.ensure_one()
        self._assert_staging()
        self._assert_auditor()
        self._assert_employees()
        if not self.audit_note or not self.audit_note.strip():
            raise ValidationError(_("El cierre masivo requiere una nota de auditoría."))
        closes = self.env["test.horas.monthly.close"].search(
            [("employee_id", "in", self.employee_ids.ids), ("month", "=", self.month)]
        )
        found_ids = set(closes.mapped("employee_id").ids)
        missing = self.employee_ids.filtered(lambda employee: employee.id not in found_ids)
        invalid = closes.filtered(
            lambda close: close.state not in {"computed", "reviewed", "closed"}
            or (close.state != "closed" and close.pending_workdays)
        )
        if missing or invalid:
            details = []
            if missing:
                details.append(_("sin preparar: %s", ", ".join(missing.mapped("name"))))
            if invalid:
                details.append(_("con estado o pendientes incompatibles: %s", ", ".join(invalid.mapped("employee_id.name"))))
            raise ValidationError(_("No se cerró ningún registro: %s", "; ".join(details)))

        already_closed = closes.filtered(lambda close: close.state == "closed")
        computed = closes.filtered(lambda close: close.state == "computed")
        reviewed = closes.filtered(lambda close: close.state == "reviewed")
        if computed:
            computed.write({"audit_note": self.audit_note.strip()})
            computed.action_review()
        to_close = computed | reviewed
        if to_close:
            to_close.action_close()
        self.write(
            {
                "state": "done",
                "selected_count": len(self.employee_ids),
                "closed_count": len(to_close),
                "skipped_count": len(already_closed),
                "operations_log": _(
                    "Cerrados: %(closed)s. Ya cerrados: %(skipped)s. Escrituras estándar: 0.",
                    closed=len(to_close),
                    skipped=len(already_closed),
                ),
            }
        )
        return self._close_action(closes)

    def _close_action(self, closes):
        return {
            "type": "ir.actions.act_window",
            "name": _("Cierres mensuales del lote"),
            "res_model": "test.horas.monthly.close",
            "view_mode": "list,form",
            "domain": [("id", "in", closes.ids)],
        }
