from datetime import time

from odoo import models


class TestHorasCalendarResolverMixin(models.AbstractModel):
    _name = "test.horas.calendar.resolver.mixin"
    _description = "Resolución única de tramos resource.calendar"

    def _calendar_attendance_week_type(self, work_date):
        """Paridad A/B de Odoo 19, no la semana ISO."""
        return str(self.env["resource.calendar.attendance"].get_week_type(work_date))

    def _calendar_lines_for_date(self, calendar, work_date):
        if not calendar:
            return calendar
        weekday = str(work_date.weekday())
        week_type = self._calendar_attendance_week_type(work_date)
        two_weeks = bool(getattr(calendar, "two_weeks_calendar", False))
        return calendar.attendance_ids.filtered(
            lambda line: line.dayofweek == weekday
            and not getattr(line, "display_type", False)
            and getattr(line, "day_period", "") != "lunch"
            and (not hasattr(line, "_is_work_period") or line._is_work_period())
            and (not getattr(line, "date_from", False) or line.date_from <= work_date)
            and (not getattr(line, "date_to", False) or line.date_to >= work_date)
            and (
                not two_weeks
                or not hasattr(line, "week_type")
                or not line.week_type
                or line.week_type == week_type
            )
        )

    @staticmethod
    def _calendar_float_to_time(value):
        total = int(round(float(value) * 60))
        if total >= 24 * 60:
            return time(23, 59)
        if total <= 0:
            return time(0, 0)
        return time(total // 60, total % 60)
