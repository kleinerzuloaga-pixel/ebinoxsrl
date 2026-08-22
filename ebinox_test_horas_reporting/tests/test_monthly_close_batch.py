from datetime import date

from odoo import Command
from odoo.exceptions import ValidationError
from odoo.tests import TransactionCase, tagged


@tagged("post_install", "-at_install")
class TestMonthlyCloseBatch(TransactionCase):
    @classmethod
    def setUpClass(cls):
        super().setUpClass()
        cls.env.user.groups_id = [
            Command.link(cls.env.ref("ebinox_test_horas.group_test_horas_auditor").id)
        ]

    def _employee(self, name, workday_state="calculated"):
        employee = self.env["hr.employee"].create(
            {"name": name, "company_id": self.env.company.id}
        )
        self.env["test.horas.employee.profile"].create(
            {
                "employee_id": employee.id,
                "population_type": "direct",
                "hire_date": date(2020, 1, 1),
            }
        )
        self.env["test.horas.workday"].create(
            {
                "employee_id": employee.id,
                "operational_date": date(2026, 8, 3),
                "state": workday_state,
                "calculation_version": "batch.test.v1",
                "ordinary_diurnal_min": 480,
            }
        )
        return employee

    def _wizard(self, employees):
        return self.env["test.horas.monthly.close.batch.wizard"].create(
            {
                "company_id": self.env.company.id,
                "month": date(2026, 8, 1),
                "employee_ids": [Command.set(employees.ids)],
                "audit_note": "Conciliación masiva controlada",
            }
        )

    def test_prepare_and_close_two_people(self):
        employees = self._employee("Persona A") | self._employee("Persona B")
        wizard = self._wizard(employees)
        wizard.action_prepare()
        closes = self.env["test.horas.monthly.close"].search(
            [("employee_id", "in", employees.ids), ("month", "=", date(2026, 8, 1))]
        )
        self.assertEqual(len(closes), 2)
        self.assertEqual(set(closes.mapped("state")), {"computed"})
        wizard.action_review_and_close()
        self.assertEqual(set(closes.mapped("state")), {"closed"})
        self.assertEqual(wizard.closed_count, 2)

    def test_batch_rejects_all_when_one_close_has_pending_workdays(self):
        ready = self._employee("Sin pendientes")
        pending = self._employee("Con pendientes", workday_state="review")
        employees = ready | pending
        wizard = self._wizard(employees)
        wizard.action_prepare()
        with self.assertRaises(ValidationError):
            wizard.action_review_and_close()
        closes = self.env["test.horas.monthly.close"].search(
            [("employee_id", "in", employees.ids), ("month", "=", date(2026, 8, 1))]
        )
        self.assertEqual(set(closes.mapped("state")), {"computed"})
