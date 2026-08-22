from datetime import datetime, timedelta

from odoo.tests import TransactionCase, tagged


@tagged("standard", "at_install")
class TestAttendanceSyncIsolation(TransactionCase):
    @classmethod
    def setUpClass(cls):
        super().setUpClass()
        cls.env.user.group_ids |= cls.env.ref("ebinox_test_horas.group_test_horas_manager")
        cls.env.user.group_ids |= cls.env.ref("hr_attendance.group_hr_attendance_manager")
        cls.employee = cls.env["hr.employee"].create(
            {"name": "Empleado piloto aislado", "company_id": cls.env.company.id}
        )
        cls.check_in = datetime(2026, 8, 3, 11, 0, 0)
        cls.check_out = datetime(2026, 8, 3, 20, 0, 0)
        cls.attendance = cls.env["hr.attendance"].create(
            {
                "employee_id": cls.employee.id,
                "check_in": cls.check_in,
                "check_out": cls.check_out,
            }
        )

    def _new_run(self):
        return self.env["test.horas.attendance.sync.run"].create(
            {
                "name": "Prueba aislada",
                "company_id": self.env.company.id,
                "date_from": self.check_in - timedelta(hours=1),
                "date_to": self.check_out + timedelta(hours=1),
            }
        )

    def _source_values(self):
        return self.attendance.read(["employee_id", "check_in", "check_out", "write_date"])[0]

    def test_sync_reads_source_and_creates_two_private_events(self):
        before = self._source_values()
        run = self._new_run()
        run.action_preview()
        self.assertEqual(run.preview_attendance_count, 1)
        run.action_sync()
        events = self.env["test.horas.clock.event"].search(
            [("source", "=", "odoo_hr_attendance"), ("employee_id", "=", self.employee.id)]
        )
        self.assertEqual(len(events), 2)
        self.assertEqual(set(events.mapped("event_kind")), {"in", "out"})
        self.assertEqual(run.attendances_read, 1)
        self.assertEqual(run.events_created, 2)
        self.assertEqual(run.events_already_present, 0)
        self.assertEqual(self._source_values(), before)

    def test_second_sync_is_idempotent_and_source_is_unchanged(self):
        first = self._new_run()
        first.action_sync()
        before = self._source_values()
        second = self._new_run()
        second.action_sync()
        self.assertEqual(second.events_created, 0)
        self.assertEqual(second.events_already_present, 2)
        events = self.env["test.horas.clock.event"].search(
            [("source", "=", "odoo_hr_attendance"), ("employee_id", "=", self.employee.id)]
        )
        self.assertEqual(len(events), 2)
        self.assertEqual(self._source_values(), before)

    def test_open_attendance_creates_only_check_in_snapshot(self):
        other_employee = self.env["hr.employee"].create(
            {"name": "Empleado con asistencia abierta", "company_id": self.env.company.id}
        )
        self.env["hr.attendance"].create(
            {"employee_id": other_employee.id, "check_in": self.check_in + timedelta(minutes=5)}
        )
        run = self._new_run()
        run.action_sync()
        events = self.env["test.horas.clock.event"].search(
            [("source", "=", "odoo_hr_attendance"), ("employee_id", "=", other_employee.id)]
        )
        self.assertEqual(len(events), 1)
        self.assertEqual(events.event_kind, "in")
        self.assertEqual(run.open_attendances, 1)

