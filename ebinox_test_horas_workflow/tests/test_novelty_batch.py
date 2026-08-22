from datetime import date

from odoo.tests import TransactionCase, tagged


@tagged("standard", "at_install")
class TestNoveltyBatchWizard(TransactionCase):
    @classmethod
    def setUpClass(cls):
        super().setUpClass()
        cls.env.user.group_ids |= cls.env.ref("ebinox_test_horas.group_test_horas_operator")
        cls.employee = cls.env["hr.employee"].create(
            {"name": "Empleado carga masiva", "company_id": cls.env.company.id}
        )
        cls.novelty_type = cls.env.ref("ebinox_test_horas_workflow.novelty_type_aj")

    def _wizard(self, **extra):
        values = {
            "company_id": self.env.company.id,
            "employee_ids": [(6, 0, self.employee.ids)],
            "date_from": date(2026, 8, 3),
            "date_to": date(2026, 8, 9),
            "novelty_type_id": self.novelty_type.id,
            "reason": "Carga de rango controlada",
        }
        values.update(extra)
        return self.env["test.horas.novelty.batch.wizard"].create(values)

    def test_full_week_includes_weekend_and_second_run_skips(self):
        first = self._wizard()
        first.action_generate()
        self.assertEqual(first.created_count, 7)
        self.assertEqual(first.skipped_count, 0)
        self.assertEqual(
            self.env["test.horas.daily.novelty"].search_count(
                [("employee_id", "=", self.employee.id)]
            ),
            7,
        )

        second = self._wizard()
        second.action_generate()
        self.assertEqual(second.created_count, 0)
        self.assertEqual(second.skipped_count, 7)

    def test_weekday_selection_and_submit_without_approval(self):
        wizard = self._wizard(saturday=False, sunday=False, submit_created=True)
        wizard.action_generate()
        records = self.env["test.horas.daily.novelty"].search(
            [("employee_id", "=", self.employee.id)]
        )
        self.assertEqual(len(records), 5)
        self.assertEqual(set(records.mapped("state")), {"submitted"})
