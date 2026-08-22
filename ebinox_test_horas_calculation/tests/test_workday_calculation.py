from datetime import date, datetime

from odoo.tests import TransactionCase, tagged


@tagged("standard", "at_install")
class TestWorkdayCalculation(TransactionCase):
    @classmethod
    def setUpClass(cls):
        super().setUpClass()
        cls.env.user.group_ids |= cls.env.ref("ebinox_test_horas.group_test_horas_operator")
        cls.employee = cls.env["hr.employee"].create(
            {"name": "Empleado cálculo piloto", "company_id": cls.env.company.id}
        )

    def _workday(self, authorized=False):
        return self.env["test.horas.workday"].create(
            {
                "employee_id": self.employee.id,
                "operational_date": date(2026, 8, 3),
                "first_mark": datetime(2026, 8, 3, 11, 0, 0),
                "last_mark": datetime(2026, 8, 3, 21, 0, 0),
                "mark_count": 2,
                "schedule_start_hour": 8.0,
                "schedule_end_hour": 17.0,
                "schedule_timezone": "America/Argentina/Buenos_Aires",
                "day_regime": "laborable",
                "overtime_authorized": authorized,
            }
        )

    def test_unauthorized_excess_is_detected_but_not_payable(self):
        workday = self._workday(authorized=False)
        workday.action_calculate_test_horas()
        self.assertEqual(workday.ordinary_diurnal_min, 540)
        self.assertEqual(workday.detected_overtime_min, 60)
        self.assertEqual(workday.payable_50_diurnal_min, 0)
        self.assertEqual(workday.unliquidated_overtime_min, 60)
        self.assertEqual(workday.state, "calculated")
        self.assertTrue(workday.calculation_input_hash)
        self.assertTrue(workday.calculation_input_snapshot)

    def test_explicit_authorization_makes_one_hour_payable(self):
        workday = self._workday(authorized=True)
        workday.action_calculate_test_horas()
        self.assertEqual(workday.detected_overtime_min, 60)
        self.assertEqual(workday.payable_50_diurnal_min, 60)
        self.assertEqual(workday.unliquidated_overtime_min, 0)

    def test_authorization_changes_input_hash_and_result(self):
        workday = self._workday(authorized=False)
        workday.action_calculate_test_horas()
        first_hash = workday.calculation_input_hash
        workday.overtime_authorized = True
        workday.action_calculate_test_horas()
        self.assertNotEqual(workday.calculation_input_hash, first_hash)
        self.assertEqual(workday.payable_50_diurnal_min, 60)

    def test_split_schedule_excludes_gap_and_preserves_post_shift_extra(self):
        workday = self._workday(authorized=True)
        workday.schedule_segments_json = (
            '[{"end": "12:00:00", "start": "08:00:00"}, '
            '{"end": "17:00:00", "start": "13:00:00"}]'
        )
        workday.action_calculate_test_horas()
        self.assertEqual(workday.ordinary_diurnal_min, 480)
        self.assertEqual(workday.detected_overtime_min, 60)
        self.assertEqual(workday.payable_50_diurnal_min, 60)
        self.assertIn("schedule_segments", workday.calculation_input_snapshot)
        self.assertEqual(workday.calculation_version, "2026-08-21.odoo19.v2.multisegment")
