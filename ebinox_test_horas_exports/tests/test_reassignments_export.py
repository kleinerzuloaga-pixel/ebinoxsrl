import base64
from datetime import date, datetime

from odoo.tests import TransactionCase, tagged


@tagged("standard", "at_install")
class TestReassignmentsExport(TransactionCase):
    @classmethod
    def setUpClass(cls):
        super().setUpClass()
        cls.env.user.group_ids |= cls.env.ref("ebinox_test_horas.group_test_horas_manager")
        cls.employee = cls.env["hr.employee"].create(
            {
                "name": "Empleado REASIG piloto",
                "company_id": cls.env.company.id,
                "identification_id": "20999999991",
            }
        )

    def test_reassignments_export_contains_before_after_and_audit(self):
        workday = self.env["test.horas.workday"].create(
            {
                "employee_id": self.employee.id,
                "operational_date": date(2026, 8, 3),
                "mark_count": 1,
            }
        )
        self.env["test.horas.workday.adjustment"].create(
            {
                "workday_id": workday.id,
                "reason": "Corrección de marca con evidencia",
                "previous_first_mark": datetime(2026, 8, 3, 11, 10),
                "new_first_mark": datetime(2026, 8, 3, 11, 0),
            }
        )
        export = self.env["test.horas.transition.export"].create(
            {
                "name": "REASIG piloto",
                "company_id": self.env.company.id,
                "export_type": "reassignments",
                "date_from": date(2026, 8, 1),
                "date_to": date(2026, 8, 15),
            }
        )
        export.action_generate()
        text = base64.b64decode(export.file_data).decode("utf-8-sig")
        self.assertIn("previous_first_mark", text)
        self.assertIn("new_first_mark", text)
        self.assertIn("Corrección de marca con evidencia", text)
        self.assertIn("20999999991", text)
        self.assertEqual(export.row_count, 1)
