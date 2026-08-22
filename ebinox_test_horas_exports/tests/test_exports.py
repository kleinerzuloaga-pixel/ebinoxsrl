import base64
import hashlib
from datetime import date

from odoo.exceptions import UserError
from odoo.tests import TransactionCase, tagged


@tagged("standard", "at_install")
class TestPrivateTransitionExports(TransactionCase):
    @classmethod
    def setUpClass(cls):
        super().setUpClass()
        cls.env.user.group_ids |= cls.env.ref("ebinox_test_horas.group_test_horas_manager")
        cls.employee = cls.env["hr.employee"].create(
            {
                "name": "Empleado exportación piloto",
                "company_id": cls.env.company.id,
                "identification_id": "20123456789",
            }
        )

    def _workday(self):
        return self.env["test.horas.workday"].create(
            {
                "employee_id": self.employee.id,
                "operational_date": date(2026, 8, 3),
                "mark_count": 2,
                "state": "calculated",
                "ordinary_diurnal_min": 480,
                "detected_overtime_min": 60,
                "payable_50_diurnal_min": 60,
                "schedule_start_hour": 8.0,
                "schedule_end_hour": 17.0,
                "schedule_timezone": "America/Argentina/Buenos_Aires",
                "calculation_version": "test.v1",
            }
        )

    def _decoded(self, export):
        return base64.b64decode(export.file_data)

    def test_nov_daily_is_private_bom_csv_hashed_and_immutable(self):
        self._workday()
        export = self.env["test.horas.transition.export"].create(
            {
                "name": "NOV diario piloto",
                "company_id": self.env.company.id,
                "export_type": "nov_daily",
                "date_from": date(2026, 8, 1),
                "date_to": date(2026, 8, 15),
            }
        )
        attachment_count = self.env["ir.attachment"].search_count([])
        export.action_generate()
        raw = self._decoded(export)
        self.assertTrue(raw.startswith(b"\xef\xbb\xbf"))
        text = raw.decode("utf-8-sig")
        self.assertIn("employee_id;identification_id;employee_name", text)
        self.assertIn("20123456789", text)
        self.assertEqual(export.row_count, 1)
        self.assertEqual(export.content_sha256, hashlib.sha256(raw).hexdigest())
        self.assertEqual(self.env["ir.attachment"].search_count([]), attachment_count)
        with self.assertRaises(UserError):
            export.name = "No modificable"

    def test_nov_calendar_has_one_column_per_day(self):
        self._workday()
        export = self.env["test.horas.transition.export"].create(
            {
                "name": "NOVCAL piloto",
                "company_id": self.env.company.id,
                "export_type": "nov_calendar",
                "date_from": date(2026, 8, 3),
                "date_to": date(2026, 8, 5),
            }
        )
        export.action_generate()
        text = self._decoded(export).decode("utf-8-sig")
        self.assertIn("2026-08-03;2026-08-04;2026-08-05", text)
        self.assertIn(";P;;", text)
        self.assertEqual(export.row_count, 1)

    def _period_data(self):
        workday = self._workday()
        period = self.env["test.horas.overtime.period"].create(
            {
                "name": "Período exportación",
                "company_id": self.env.company.id,
                "date_from": date(2026, 8, 1),
                "date_to": date(2026, 8, 15),
                "state": "approved",
                "approval_reason": "Aprobación piloto",
            }
        )
        line = self.env["test.horas.overtime.line"].create(
            {
                "period_id": period.id,
                "employee_id": self.employee.id,
                "date": workday.operational_date,
                "workday_id": workday.id,
                "detected_excess_min": 60,
                "raw_50_diurnal_min": 60,
                "payable_50_diurnal_min": 60,
            }
        )
        valuation = self.env["test.horas.overtime.valuation"].create(
            {
                "employee_id": self.employee.id,
                "period_id": period.id,
                "source_hour_value": 100.0,
                "rule_version": "test.v1",
                "amount_50_diurnal": 120.75,
                "raw_amount": 120.75,
                "rounded_amount": 200.0,
            }
        )
        return period, line, valuation

    def test_extras_and_valuation_exports_use_private_period_data(self):
        period, _line, _valuation = self._period_data()
        extras = self.env["test.horas.transition.export"].create(
            {
                "name": "EXTRAS piloto",
                "company_id": self.env.company.id,
                "export_type": "overtime",
                "period_id": period.id,
            }
        )
        extras.action_generate()
        extras_text = self._decoded(extras).decode("utf-8-sig")
        self.assertIn("detected_excess_min", extras_text)
        self.assertIn("20123456789", extras_text)
        self.assertEqual(extras.row_count, 1)

        valuation_export = self.env["test.horas.transition.export"].create(
            {
                "name": "Val piloto",
                "company_id": self.env.company.id,
                "export_type": "valuation",
                "period_id": period.id,
            }
        )
        valuation_export.action_generate()
        valuation_text = self._decoded(valuation_export).decode("utf-8-sig")
        self.assertIn("rounded_amount", valuation_text)
        self.assertIn("200.0", valuation_text)
        self.assertEqual(valuation_export.row_count, 1)

