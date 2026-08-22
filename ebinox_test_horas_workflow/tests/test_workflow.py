from datetime import date, datetime

from odoo.tests import TransactionCase, tagged


@tagged("standard", "at_install")
class TestPrivateWorkflow(TransactionCase):
    @classmethod
    def setUpClass(cls):
        super().setUpClass()
        cls.env.user.group_ids |= cls.env.ref("ebinox_test_horas.group_test_horas_manager")
        cls.employee = cls.env["hr.employee"].create(
            {"name": "Empleado flujo piloto", "company_id": cls.env.company.id}
        )

    def _calculated_workday(self):
        workday = self.env["test.horas.workday"].create(
            {
                "employee_id": self.employee.id,
                "operational_date": date(2026, 8, 3),
                "first_mark": datetime(2026, 8, 3, 11, 0),
                "last_mark": datetime(2026, 8, 3, 21, 0),
                "mark_count": 2,
                "schedule_start_hour": 8.0,
                "schedule_end_hour": 17.0,
                "schedule_timezone": "America/Argentina/Buenos_Aires",
                "day_regime": "laborable",
                "overtime_authorized": False,
            }
        )
        workday.action_calculate_test_horas()
        return workday

    def _period_with_line(self):
        workday = self._calculated_workday()
        period = self.env["test.horas.overtime.period"].create(
            {
                "name": "Extras agosto piloto",
                "company_id": self.env.company.id,
                "date_from": date(2026, 8, 1),
                "date_to": date(2026, 8, 15),
                "approval_reason": "Autorización de prueba auditable",
            }
        )
        period.action_generate_lines()
        self.assertEqual(len(period.line_ids), 1)
        self.assertEqual(period.line_ids.workday_id, workday)
        return period, workday

    def _approved_period(self):
        period, workday = self._period_with_line()
        period.action_submit()
        period.action_approve()
        return period, workday

    def test_approved_novelty_creates_only_private_workday(self):
        novelty = self.env["test.horas.daily.novelty"].create(
            {
                "employee_id": self.employee.id,
                "date": date(2026, 8, 5),
                "novelty_type_id": self.env.ref("ebinox_test_horas_workflow.novelty_type_aj").id,
                "reason": "Justificación piloto",
            }
        )
        novelty.action_submit()
        novelty.action_approve()
        self.assertEqual(novelty.state, "approved")
        self.assertTrue(novelty.workday_id)
        self.assertEqual(novelty.workday_id.employee_id, self.employee)
        self.assertEqual(novelty.workday_id.novelty_id, novelty)
        self.assertTrue(novelty.workday_id.justified_absence)
        self.assertEqual(novelty.workday_id._name, "test.horas.workday")

    def test_period_authorization_recalculates_payable_buckets(self):
        period, workday = self._approved_period()
        self.assertEqual(period.state, "approved")
        self.assertTrue(period.authorization_input_hash)
        self.assertTrue(period.authorization_snapshot)
        self.assertTrue(workday.overtime_authorized)
        self.assertEqual(workday.detected_overtime_min, 60)
        self.assertEqual(workday.payable_50_diurnal_min, 60)
        self.assertEqual(period.line_ids.payable_50_diurnal_min, 60)

    def test_daily_exclusion_keeps_excess_but_pays_zero(self):
        period, workday = self._period_with_line()
        period.line_ids.write({"excluded": True, "exclusion_reason": "No autorizada ese día"})
        period.action_submit()
        period.action_approve()
        self.assertEqual(workday.detected_overtime_min, 60)
        self.assertEqual(workday.payable_50_diurnal_min, 0)
        self.assertEqual(period.line_ids.payable_50_diurnal_min, 0)

    def test_valuation_uses_versioned_factors_and_ceiling_to_hundreds(self):
        period, _workday = self._approved_period()
        valuation = self.env["test.horas.overtime.valuation"].create(
            {
                "employee_id": self.employee.id,
                "period_id": period.id,
                "source_hour_value": 100.0,
                "manual_source_reference": "Tarifa manual de prueba",
                "rule_version": "initial",
                "authorization_reference": "Autorización de prueba auditable",
            }
        )
        valuation.action_compute_valuation()
        self.assertAlmostEqual(valuation.amount_50_diurnal, 120.75, places=2)
        self.assertAlmostEqual(valuation.raw_amount, 120.75, places=2)
        self.assertEqual(valuation.rounded_amount, 200.0)
        self.assertTrue(valuation.valuation_input_hash)
        self.assertTrue(valuation.valuation_snapshot)

