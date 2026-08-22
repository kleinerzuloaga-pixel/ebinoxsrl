from datetime import date, datetime

from odoo import Command
from odoo.exceptions import UserError, ValidationError
from odoo.tests import TransactionCase, tagged


@tagged("standard", "at_install")
class TestPrivateReporting(TransactionCase):
    @classmethod
    def setUpClass(cls):
        super().setUpClass()
        cls.env.user.group_ids |= cls.env.ref("ebinox_test_horas.group_test_horas_manager")

    def _calendar(self):
        return self.env["resource.calendar"].create(
            {
                "name": "Calendario reporte lunes a viernes",
                "tz": "America/Argentina/Buenos_Aires",
                "company_id": self.env.company.id,
                "attendance_ids": [
                    Command.create(
                        {
                            "name": name,
                            "dayofweek": str(weekday),
                            "day_period": "morning",
                            "hour_from": 8.0,
                            "hour_to": 17.0,
                        }
                    )
                    for weekday, name in enumerate(
                        ["Lunes", "Martes", "Miércoles", "Jueves", "Viernes"]
                    )
                ],
            }
        )

    def _employee_profile(self, name="Empleado reporte", hire_date=date(2020, 1, 1)):
        calendar = self._calendar()
        employee = self.env["hr.employee"].create(
            {
                "name": name,
                "company_id": self.env.company.id,
                "resource_calendar_id": calendar.id,
            }
        )
        profile = self.env["test.horas.employee.profile"].create(
            {
                "employee_id": employee.id,
                "population_type": "direct",
                "hire_date": hire_date,
            }
        )
        return employee, profile

    def _workday(self, employee, day, marks=2, tardiness=0, **minutes):
        values = {
            "employee_id": employee.id,
            "operational_date": day,
            "mark_count": marks,
            "state": "calculated",
            "calculation_version": "test.v1",
            "tardiness_min": tardiness,
        }
        values.update(minutes)
        return self.env["test.horas.workday"].create(values)

    def test_absenteeism_one_of_five_expected_days_is_twenty_percent(self):
        employee, _profile = self._employee_profile()
        days = [date(2026, 8, day) for day in range(3, 8)]
        workdays = [self._workday(employee, day, tardiness=6 if day.day == 4 else 0) for day in days]
        novelty = self.env["test.horas.daily.novelty"].create(
            {
                "employee_id": employee.id,
                "date": days[2],
                "workday_id": workdays[2].id,
                "novelty_type_id": self.env.ref("ebinox_test_horas_workflow.novelty_type_ai").id,
                "reason": "Ausencia piloto",
            }
        )
        novelty.action_submit()
        novelty.action_approve()
        run = self.env["test.horas.absenteeism.run"].create(
            {
                "name": "Semana piloto",
                "company_id": self.env.company.id,
                "date_from": days[0],
                "date_to": days[-1],
                "universe": "direct",
            }
        )
        run.action_compute()
        self.assertEqual(run.expected_person_days, 5)
        self.assertEqual(run.absent_person_days, 1)
        self.assertAlmostEqual(run.absenteeism_percentage, 20.0)
        self.assertEqual(run.tardiness_events, 1)
        self.assertEqual(len(run.line_ids), 5)

    def test_new_hire_under_five_business_days_stays_in_detail_not_rate(self):
        employee, _profile = self._employee_profile(
            name="Alta reciente", hire_date=date(2026, 8, 6)
        )
        self._workday(employee, date(2026, 8, 6), marks=0)
        self._workday(employee, date(2026, 8, 7), marks=0)
        run = self.env["test.horas.absenteeism.run"].create(
            {
                "name": "Alta reciente piloto",
                "company_id": self.env.company.id,
                "date_from": date(2026, 8, 3),
                "date_to": date(2026, 8, 7),
                "universe": "direct",
            }
        )
        run.action_compute()
        self.assertEqual(run.excluded_new_hires, 1)
        self.assertEqual(run.expected_person_days, 0)
        self.assertEqual(run.absent_person_days, 0)
        self.assertEqual(len(run.line_ids), 2)
        self.assertTrue(all(run.line_ids.mapped("excluded_new_hire")))

    def test_termination_date_excludes_later_days_from_denominator(self):
        _employee, profile = self._employee_profile()
        profile.termination_date = date(2026, 8, 5)
        run = self.env["test.horas.absenteeism.run"].create(
            {
                "name": "Baja durante semana piloto",
                "company_id": self.env.company.id,
                "date_from": date(2026, 8, 3),
                "date_to": date(2026, 8, 7),
                "universe": "direct",
            }
        )
        run.action_compute()
        self.assertEqual(run.expected_person_days, 3)
        self.assertEqual(run.absent_person_days, 3)
        self.assertEqual(
            set(run.line_ids.mapped("date")),
            {date(2026, 8, 3), date(2026, 8, 4), date(2026, 8, 5)},
        )

    def test_termination_date_cannot_precede_hire_date(self):
        _employee, profile = self._employee_profile()
        with self.assertRaises(ValidationError):
            profile.termination_date = date(2019, 12, 31)

    def test_monthly_close_totals_and_locks_after_close(self):
        employee, _profile = self._employee_profile()
        self._workday(
            employee,
            date(2026, 8, 3),
            ordinary_diurnal_min=480,
            payable_50_diurnal_min=60,
        )
        self._workday(
            employee,
            date(2026, 8, 4),
            ordinary_diurnal_min=420,
            ordinary_nocturnal_min=60,
            payable_100_nocturnal_min=30,
        )
        close = self.env["test.horas.monthly.close"].create(
            {"employee_id": employee.id, "month": date(2026, 8, 1)}
        )
        close.action_compute()
        self.assertEqual(close.ordinary_diurnal_min, 900)
        self.assertEqual(close.ordinary_nocturnal_min, 60)
        self.assertEqual(close.overtime_50_diurnal_min, 60)
        self.assertEqual(close.overtime_100_nocturnal_min, 30)
        self.assertEqual(close.pending_workdays, 0)
        close.audit_note = "Cierre revisado en piloto"
        close.action_review()
        close.action_close()
        self.assertEqual(close.state, "closed")
        with self.assertRaises(UserError):
            close.audit_note = "Cambio no permitido"

