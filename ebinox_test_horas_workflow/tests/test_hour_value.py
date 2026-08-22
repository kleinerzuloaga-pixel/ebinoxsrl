from datetime import date

from odoo.exceptions import ValidationError
from odoo.tests import TransactionCase, tagged


@tagged("standard", "at_install")
class TestHourValueSource(TransactionCase):
    @classmethod
    def setUpClass(cls):
        super().setUpClass()
        cls.env.user.group_ids |= cls.env.ref("ebinox_test_horas.group_test_horas_manager")
        cls.employee = cls.env["hr.employee"].create(
            {
                "name": "Empleado tarifa piloto",
                "company_id": cls.env.company.id,
                "identification_id": "20-00000000-1",
            }
        )

    def test_resolves_unique_tariff_and_snapshots_identity(self):
        tariff = self.env["test.horas.hour.value"].create(
            {
                "employee_id": self.employee.id,
                "hourly_value": 123.45,
                "source": "Planilla consultora",
                "source_reference": "VAL-2026-08",
                "valid_from": date(2026, 8, 1),
            }
        )
        period = self.env["test.horas.overtime.period"].create(
            {
                "name": "Período tarifa",
                "company_id": self.env.company.id,
                "date_from": date(2026, 8, 1),
                "date_to": date(2026, 8, 15),
            }
        )
        valuation = self.env["test.horas.overtime.valuation"].create(
            {
                "employee_id": self.employee.id,
                "period_id": period.id,
                "valuation_date": date(2026, 8, 15),
                "rule_version": "pending",
            }
        )
        valuation.action_resolve_hour_value()
        self.assertEqual(valuation.hour_value_id, tariff)
        self.assertEqual(valuation.source_hour_value, 123.45)
        self.assertIn("20-00000000-1", valuation.hour_value_source_snapshot)

    def test_overlapping_tariffs_are_rejected(self):
        self.env["test.horas.hour.value"].create(
            {
                "employee_id": self.employee.id,
                "hourly_value": 100,
                "source": "Fuente A",
                "source_reference": "A",
                "valid_from": date(2026, 8, 1),
                "valid_to": date(2026, 8, 31),
            }
        )
        with self.assertRaises(ValidationError):
            self.env["test.horas.hour.value"].create(
                {
                    "employee_id": self.employee.id,
                    "hourly_value": 110,
                    "source": "Fuente B",
                    "source_reference": "B",
                    "valid_from": date(2026, 8, 15),
                }
            )
