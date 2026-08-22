from odoo.exceptions import AccessError, UserError
from odoo.tests import TransactionCase, tagged


@tagged("post_install", "-at_install")
class TestAuditEvent(TransactionCase):
    def test_internal_event_is_hashed_and_immutable(self):
        employee = self.env["hr.employee"].create(
            {"name": "Persona auditada", "company_id": self.env.company.id}
        )
        workday = self.env["test.horas.workday"].create(
            {"employee_id": employee.id, "operational_date": "2026-08-03"}
        )
        event = workday._log_test_horas_event(
            "roster.read",
            "Lectura controlada de nómina",
            {"employee_id": employee.id, "writes_standard": 0},
        )
        self.assertEqual(event.source_model, "test.horas.workday")
        self.assertTrue(event.payload_sha256)
        self.assertIn("writes_standard", event.payload_json)
        with self.assertRaises(UserError):
            event.summary = "Cambio prohibido"
        with self.assertRaises(AccessError):
            self.env["test.horas.audit.event"].create(
                {
                    "company_id": self.env.company.id,
                    "action": "manual",
                    "source_model": "x",
                    "source_record_id": 1,
                    "source_display_name": "x",
                    "summary": "No permitido",
                    "payload_sha256": "0" * 64,
                }
            )

