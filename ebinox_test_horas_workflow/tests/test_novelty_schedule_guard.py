from datetime import date

from odoo import Command
from odoo.tests import TransactionCase, tagged


@tagged("standard", "at_install")
class TestNoveltyScheduleGuard(TransactionCase):
    @classmethod
    def setUpClass(cls):
        super().setUpClass()
        cls.env.user.group_ids |= cls.env.ref("ebinox_test_horas.group_test_horas_manager")
        cls.calendar = cls.env["resource.calendar"].create(
            {
                "name": "Calendario novedad 08–17",
                "tz": "America/Argentina/Buenos_Aires",
                "company_id": cls.env.company.id,
                "attendance_ids": [
                    Command.create(
                        {
                            "name": "Lunes",
                            "dayofweek": "0",
                            "day_period": "morning",
                            "hour_from": 8.0,
                            "hour_to": 17.0,
                        }
                    )
                ],
            }
        )
        cls.employee = cls.env["hr.employee"].create(
            {
                "name": "Empleado guardia horario",
                "company_id": cls.env.company.id,
                "resource_calendar_id": cls.calendar.id,
            }
        )
        cls.aj = cls.env.ref("ebinox_test_horas_workflow.novelty_type_aj")

    def _approve(self, novelty_date):
        novelty = self.env["test.horas.daily.novelty"].create(
            {
                "employee_id": self.employee.id,
                "date": novelty_date,
                "novelty_type_id": self.aj.id,
                "reason": "Prueba de horario teórico",
            }
        )
        novelty.action_submit()
        novelty.action_approve()
        return novelty

    def test_weekday_snapshots_schedule_before_granting_hours(self):
        novelty = self._approve(date(2026, 8, 3))
        workday = novelty.workday_id
        self.assertEqual(workday.schedule_start_hour, 8.0)
        self.assertEqual(workday.schedule_end_hour, 17.0)
        self.assertTrue(workday.justified_absence)
        workday.action_calculate_test_horas()
        self.assertEqual(workday.ordinary_diurnal_min, 540)

    def test_day_without_schedule_records_code_but_grants_zero_hours(self):
        novelty = self._approve(date(2026, 8, 8))  # sábado sin tramo
        workday = novelty.workday_id
        self.assertFalse(workday.justified_absence)
        self.assertEqual(workday.warning_code, "SIN_JORNADA_TEORICA")
