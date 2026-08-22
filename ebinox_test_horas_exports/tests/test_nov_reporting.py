import base64
import csv
import io
from datetime import date

from odoo.tests import TransactionCase, tagged


@tagged("standard", "at_install")
class TestNovReporting(TransactionCase):
    @classmethod
    def setUpClass(cls):
        super().setUpClass()
        cls.env.user.group_ids |= cls.env.ref("ebinox_test_horas.group_test_horas_manager")

    def _employee(self, name, treatment):
        employee = self.env["hr.employee"].create(
            {"name": name, "company_id": self.env.company.id}
        )
        self.env["test.horas.employee.profile"].create(
            {
                "employee_id": employee.id,
                "population_type": "direct",
                "nov_treatment": treatment,
                "consultant_code": "CDE" if treatment == "consultant" else False,
            }
        )
        return employee

    def _workday(self, employee, day, *, diurnal=0, nocturnal=0, marks=0, start=8.0, end=16.0):
        return self.env["test.horas.workday"].create(
            {
                "employee_id": employee.id,
                "operational_date": day,
                "mark_count": marks,
                "state": "calculated",
                "schedule_start_hour": start,
                "schedule_end_hour": end,
                "schedule_timezone": "America/Argentina/Buenos_Aires",
                "ordinary_diurnal_min": diurnal,
                "ordinary_nocturnal_min": nocturnal,
            }
        )

    def _novelty(self, employee, day, code):
        novelty_type = self.env["test.horas.novelty.type"].search(
            [("code", "=", code), ("company_id", "=", False)], limit=1
        )
        return self.env["test.horas.daily.novelty"].create(
            {
                "employee_id": employee.id,
                "date": day,
                "novelty_type_id": novelty_type.id,
                "reason": "Caso NOV de prueba",
                "state": "approved",
            }
        )

    def _rows(self, export_type, date_from, date_to):
        export = self.env["test.horas.transition.export"].create(
            {
                "name": "NOV funcional",
                "company_id": self.env.company.id,
                "export_type": export_type,
                "date_from": date_from,
                "date_to": date_to,
            }
        )
        export.action_generate()
        text = base64.b64decode(export.file_data).decode("utf-8-sig")
        return list(csv.DictReader(io.StringIO(text), delimiter=";"))

    def test_own_summary_separates_buckets_and_holiday_overrides_obra(self):
        employee = self._employee("Propio NOV", "own")
        self._workday(employee, date(2026, 8, 3), diurnal=480, marks=2)
        self._workday(employee, date(2026, 8, 4))
        self._novelty(employee, date(2026, 8, 4), "AJ")
        self._workday(employee, date(2026, 8, 5))
        self._novelty(employee, date(2026, 8, 5), "O")
        self.env["test.horas.holiday"].create(
            {
                "name": "Feriado prueba",
                "date": date(2026, 8, 5),
                "company_id": self.env.company.id,
            }
        )
        self._workday(employee, date(2026, 8, 6))
        self._novelty(employee, date(2026, 8, 6), "D")
        self._workday(employee, date(2026, 8, 7))
        self._novelty(employee, date(2026, 8, 7), "AI")

        row = next(
            item for item in self._rows("nov_summary", date(2026, 8, 3), date(2026, 8, 7))
            if item["employee_name"] == "Propio NOV"
        )
        self.assertEqual(row["q1_diurnal_h"], "8.0")
        self.assertEqual(row["holiday_not_worked_h"], "8.0")
        self.assertEqual(row["aj_q1_h"], "8.0")
        self.assertEqual(row["rest_q1_h"], "8.0")
        self.assertEqual(row["unjustified_q1_h"], "8.0")
        self.assertEqual(row["total_nov_h"], "24.0")
        self.assertEqual(row["O_days"], "0")
        self.assertEqual(row["F_days"], "1")

    def test_consultant_calendar_uses_30_50_rounding_a_and_blank_weekend(self):
        employee = self._employee("Consultora NOV", "consultant")
        self._workday(
            employee, date(2026, 8, 3), diurnal=140, nocturnal=360,
            marks=2, start=20.0, end=4.0,
        )
        self._workday(employee, date(2026, 8, 4))
        self._novelty(employee, date(2026, 8, 4), "AI")
        self._workday(employee, date(2026, 8, 8), diurnal=480, marks=2)

        row = next(
            item for item in self._rows("nov_calendar", date(2026, 8, 3), date(2026, 8, 8))
            if item["employee_name"] == "Consultora NOV"
        )
        self.assertEqual(row["2026-08-03"], "2 + 6")
        self.assertEqual(row["2026-08-04"], "A")
        self.assertEqual(row["2026-08-08"], "")
        self.assertEqual(row["P_days"], "1")
        self.assertEqual(row["A_days"], "1")
        self.assertEqual(row["q1_diurnal_h"], "2.0")
        self.assertEqual(row["q1_nocturnal_h"], "6.0")
