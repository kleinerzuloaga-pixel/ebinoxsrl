from datetime import date, datetime

from odoo import Command
from odoo.exceptions import UserError
from odoo.tests import TransactionCase, tagged


@tagged("post_install", "-at_install")
class TestMonthlyCalendar(TransactionCase):
    @classmethod
    def setUpClass(cls):
        super().setUpClass()
        cls.env.user.groups_id = [
            Command.link(cls.env.ref("ebinox_test_horas.group_test_horas_operator").id)
        ]

    def test_monthly_snapshot_applies_presence_and_holiday_precedence(self):
        employee = self.env["hr.employee"].create(
            {"name": "Persona calendario", "company_id": self.env.company.id}
        )
        self.env["test.horas.employee.profile"].create(
            {
                "employee_id": employee.id,
                "population_type": "direct",
                "hire_date": date(2020, 1, 1),
            }
        )
        self.env["test.horas.workday"].with_context(test_horas_import=True).create(
            {
                "employee_id": employee.id,
                "operational_date": date(2026, 8, 3),
                "state": "calculated",
                "first_mark": datetime(2026, 8, 3, 8, 0),
                "last_mark": datetime(2026, 8, 3, 17, 0),
                "mark_count": 2,
                "calculation_version": "calendar.test.v1",
                "ordinary_diurnal_min": 480,
            }
        )
        self.env["test.horas.holiday"].create(
            {
                "date": date(2026, 8, 4),
                "name": "Feriado piloto",
                "company_id": self.env.company.id,
            }
        )
        monthly = self.env["test.horas.monthly.calendar"].create(
            {
                "name": "Agosto 2026",
                "company_id": self.env.company.id,
                "month": date(2026, 8, 1),
                "employee_ids": [Command.set(employee.ids)],
            }
        )
        monthly.action_generate()
        self.assertEqual(monthly.line_count, 31)
        self.assertEqual(
            monthly.line_ids.filtered(lambda line: line.date == date(2026, 8, 3)).code,
            "P",
        )
        self.assertEqual(
            monthly.line_ids.filtered(lambda line: line.date == date(2026, 8, 4)).code,
            "F",
        )
        self.assertTrue(monthly.result_hash)
        self.assertIn("Persona calendario", monthly.matrix_html)
        with self.assertRaises(UserError):
            monthly.name = "Cambio prohibido"
        with self.assertRaises(UserError):
            monthly.line_ids[0].code = "X"

    def test_days_before_hire_are_out_of_scope_not_pending(self):
        employee = self.env["hr.employee"].create(
            {"name": "Alta parcial", "company_id": self.env.company.id}
        )
        self.env["test.horas.employee.profile"].create(
            {
                "employee_id": employee.id,
                "population_type": "direct",
                "hire_date": date(2026, 8, 15),
            }
        )
        monthly = self.env["test.horas.monthly.calendar"].create(
            {
                "name": "Alta parcial agosto",
                "company_id": self.env.company.id,
                "month": date(2026, 8, 1),
                "employee_ids": [Command.set(employee.ids)],
            }
        )
        monthly.action_generate()
        before_hire = monthly.line_ids.filtered(lambda line: line.date == date(2026, 8, 14))
        first_day = monthly.line_ids.filtered(lambda line: line.date == date(2026, 8, 15))
        self.assertEqual(before_hire.source, "out_of_scope")
        self.assertEqual(before_hire.day_count, 0)
        self.assertEqual(first_day.source, "pending")
        self.assertEqual(first_day.day_count, 1)
        self.assertEqual(monthly.pending_count, 17)
