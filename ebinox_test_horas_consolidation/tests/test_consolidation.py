from datetime import date, datetime

from odoo import Command
from odoo.tests import TransactionCase, tagged


@tagged("standard", "at_install")
class TestPrivateConsolidation(TransactionCase):
    @classmethod
    def setUpClass(cls):
        super().setUpClass()
        cls.env.user.group_ids |= cls.env.ref("ebinox_test_horas.group_test_horas_manager")

    def _calendar(self, name, lines):
        return self.env["resource.calendar"].create(
            {
                "name": name,
                "tz": "America/Argentina/Buenos_Aires",
                "company_id": self.env.company.id,
                "attendance_ids": [
                    Command.create(
                        {
                            "name": line[0],
                            "dayofweek": line[1],
                            "day_period": line[2],
                            "hour_from": line[3],
                            "hour_to": line[4],
                        }
                    )
                    for line in lines
                ],
            }
        )

    def _employee(self, name, calendar):
        return self.env["hr.employee"].create(
            {
                "name": name,
                "company_id": self.env.company.id,
                "resource_calendar_id": calendar.id,
            }
        )

    def _event(self, employee, timestamp, kind, suffix):
        return self.env["test.horas.clock.event"].create(
            {
                "employee_id": employee.id,
                "timestamp": timestamp,
                "source": "odoo_test",
                "external_id": "odoo_test:%s:%s" % (suffix, kind),
                "event_kind": kind,
            }
        )

    def _run(self, date_from, date_to):
        return self.env["test.horas.consolidation.run"].create(
            {
                "name": "Consolidación de prueba",
                "company_id": self.env.company.id,
                "date_from": date_from,
                "date_to": date_to,
            }
        )

    def test_day_events_create_one_private_workday(self):
        calendar = self._calendar("Lunes 8-17", [("Lunes", "0", "morning", 8.0, 17.0)])
        employee = self._employee("Empleado diurno", calendar)
        self._event(employee, datetime(2026, 8, 3, 11, 0), "in", "day")
        self._event(employee, datetime(2026, 8, 3, 21, 0), "out", "day")
        run = self._run(datetime(2026, 8, 3, 0, 0), datetime(2026, 8, 4, 0, 0))
        run.action_consolidate()
        workday = self.env["test.horas.workday"].search(
            [("employee_id", "=", employee.id), ("operational_date", "=", date(2026, 8, 3))]
        )
        self.assertEqual(len(workday), 1)
        self.assertEqual(workday.mark_count, 2)
        self.assertEqual(workday.schedule_start_hour, 8.0)
        self.assertEqual(workday.schedule_end_hour, 17.0)
        self.assertEqual(run.workdays_created, 1)
        self.assertEqual(run.unresolved_schedule_days, 0)

    def test_repeating_consolidation_updates_without_duplicate(self):
        calendar = self._calendar("Lunes idempotente", [("Lunes", "0", "morning", 8.0, 17.0)])
        employee = self._employee("Empleado idempotente", calendar)
        self._event(employee, datetime(2026, 8, 3, 11, 0), "in", "idem")
        self._event(employee, datetime(2026, 8, 3, 21, 0), "out", "idem")
        first = self._run(datetime(2026, 8, 3), datetime(2026, 8, 4))
        first.action_consolidate()
        second = self._run(datetime(2026, 8, 3), datetime(2026, 8, 4))
        second.action_consolidate()
        workdays = self.env["test.horas.workday"].search([("employee_id", "=", employee.id)])
        self.assertEqual(len(workdays), 1)
        self.assertEqual(second.workdays_created, 0)
        self.assertEqual(second.workdays_updated, 1)

    def test_night_pair_is_assigned_to_previous_operational_date(self):
        calendar = self._calendar(
            "Noche lunes 22-06",
            [
                ("Lunes noche", "0", "afternoon", 22.0, 24.0),
                ("Martes madrugada", "1", "morning", 0.0, 6.0),
            ],
        )
        employee = self._employee("Empleado nocturno", calendar)
        self._event(employee, datetime(2026, 8, 4, 1, 0), "in", "night")
        self._event(employee, datetime(2026, 8, 4, 8, 0), "out", "night")
        run = self._run(datetime(2026, 8, 4, 0, 0), datetime(2026, 8, 4, 12, 0))
        run.action_consolidate()
        workday = self.env["test.horas.workday"].search([("employee_id", "=", employee.id)])
        self.assertEqual(len(workday), 1)
        self.assertEqual(workday.operational_date, date(2026, 8, 3))
        self.assertEqual(workday.schedule_start_hour, 22.0)
        self.assertEqual(workday.schedule_end_hour, 6.0)

    def test_split_calendar_preserves_both_work_segments(self):
        calendar = self._calendar(
            "Lunes partido 8-12 y 13-17",
            [
                ("Lunes mañana", "0", "morning", 8.0, 12.0),
                ("Lunes tarde", "0", "afternoon", 13.0, 17.0),
            ],
        )
        employee = self._employee("Empleado horario partido", calendar)
        self._event(employee, datetime(2026, 8, 3, 11, 0), "in", "split")
        self._event(employee, datetime(2026, 8, 3, 21, 0), "out", "split")
        run = self._run(datetime(2026, 8, 3), datetime(2026, 8, 4))
        run.action_consolidate()
        workday = self.env["test.horas.workday"].search(
            [("employee_id", "=", employee.id)], limit=1
        )
        self.assertIn('"start": "08:00:00"', workday.schedule_segments_json)
        self.assertIn('"end": "12:00:00"', workday.schedule_segments_json)
        self.assertIn('"start": "13:00:00"', workday.schedule_segments_json)
        self.assertIn('"end": "17:00:00"', workday.schedule_segments_json)
