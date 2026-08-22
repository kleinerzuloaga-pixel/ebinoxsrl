from odoo import _, api, fields, models
from odoo.exceptions import ValidationError


class TestHorasNoveltyTypeWorkflow(models.Model):
    _inherit = "test.horas.novelty.type"

    grants_theoretical_hours = fields.Boolean(
        string="Acredita jornada teórica sin marcas",
        help="Se aplica sólo a una novedad aprobada y queda registrada en la jornada propia.",
    )


class TestHorasDailyNoveltyWorkflow(models.Model):
    _inherit = "test.horas.daily.novelty"

    @api.constrains("workday_id", "employee_id", "date")
    def _check_workday_consistency(self):
        for record in self:
            if record.workday_id and (
                record.workday_id.employee_id != record.employee_id
                or record.workday_id.operational_date != record.date
            ):
                raise ValidationError(
                    _("La jornada vinculada debe corresponder a la misma persona y fecha.")
                )

    def action_approve(self):
        result = super().action_approve()
        self._apply_approved_novelty_to_private_workday()
        return result

    def action_cancel(self):
        for record in self:
            if record.workday_id and record.workday_id.novelty_id == record:
                record.workday_id.write(
                    {
                        "novelty_id": False,
                        "justified_absence": False,
                        "state": "review",
                        "warning_code": "NOVEDAD_ANULADA",
                        "warning_detail": "La novedad aplicada fue anulada y la jornada requiere revisión.",
                    }
                )
        return super().action_cancel()

    def _apply_approved_novelty_to_private_workday(self):
        workday_model = self.env["test.horas.workday"]
        for record in self:
            if record.state != "approved":
                continue
            workday = record.workday_id or workday_model.search(
                [
                    ("employee_id", "=", record.employee_id.id),
                    ("operational_date", "=", record.date),
                ],
                limit=1,
            )
            if not workday:
                calendar = record.employee_id.resource_calendar_id
                workday = workday_model.create(
                    {
                        "employee_id": record.employee_id.id,
                        "operational_date": record.date,
                        "declared_calendar_id": calendar.id or False,
                        "effective_calendar_id": calendar.id or False,
                        "mark_count": 0,
                        "state": "classified",
                    }
                )
            schedule_resolved = workday.schedule_start_hour != workday.schedule_end_hour
            if not schedule_resolved and (workday.effective_calendar_id or workday.declared_calendar_id):
                calendar = workday.effective_calendar_id or workday.declared_calendar_id
                if workday._calendar_lines_for_date(calendar, record.date):
                    workday.action_snapshot_schedule()
                    schedule_resolved = workday.schedule_start_hour != workday.schedule_end_hour
            grants_hours = record.novelty_type_id.grants_theoretical_hours and schedule_resolved
            warning_code = False
            warning_detail = False
            if record.novelty_type_id.grants_theoretical_hours and not schedule_resolved:
                warning_code = "SIN_JORNADA_TEORICA"
                warning_detail = "La novedad quedó registrada sin horas porque no existe un horario válido para ese día."
            workday.write(
                {
                    "novelty_id": record.id,
                    "justified_absence": grants_hours,
                    "state": "classified",
                    "warning_code": warning_code,
                    "warning_detail": warning_detail,
                }
            )
            if record.workday_id != workday:
                record.workday_id = workday

