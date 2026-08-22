from collections import Counter
from datetime import timedelta

from odoo import fields, models
from odoo.exceptions import ValidationError

from odoo.addons.ebinox_test_horas_calculation.engine.test_horas_engine import (
    AttendanceInput,
    Schedule,
    compute_ordinary,
    format_consultant_novcal_hours,
    round_consultant_novcal_minutes,
)


HOLIDAY_NOV_MINUTES = 8 * 60
ABSENCE_CODES = {"AJ", "AI", "S", "E", "ART", "L", "LS", "V", "D"}


class TestHorasTransitionExportNovReporting(models.Model):
    _inherit = "test.horas.transition.export"

    def _nov_dataset(self):
        self.ensure_one()
        workdays = self._workdays()
        novelties = self._approved_novelties()
        profiles = self.env["test.horas.employee.profile"].search(
            [("company_id", "=", self.company_id.id), ("active", "=", True)]
        )
        holidays = self.env["test.horas.holiday"].search(
            [
                ("company_id", "=", self.company_id.id),
                ("active", "=", True),
                ("date", ">=", self.date_from),
                ("date", "<=", self.date_to),
            ]
        )
        employees = workdays.mapped("employee_id") | novelties.mapped("employee_id")
        employees |= profiles.mapped("employee_id")
        return {
            "workdays": workdays,
            "novelties": novelties,
            "profiles": profiles,
            "holidays": holidays,
            "employees": employees,
            "workday_by_key": {(item.employee_id.id, item.operational_date): item for item in workdays},
            "novelty_by_key": {(item.employee_id.id, item.date): item for item in novelties},
            "profile_by_employee": {item.employee_id.id: item for item in profiles},
            "holiday_by_date": {item.date: item for item in holidays},
        }

    def _nov_dates(self):
        dates = []
        current = self.date_from
        while current <= self.date_to:
            dates.append(current)
            current += timedelta(days=1)
        return dates

    @staticmethod
    def _has_presence(workday):
        if not workday:
            return False
        return bool(
            workday.mark_count >= 2
            or (
                workday.effective_first_mark
                and workday.effective_last_mark
                and workday.effective_last_mark > workday.effective_first_mark
            )
        )

    @staticmethod
    def _theoretical_split(workday):
        if not workday or workday.schedule_start_hour == workday.schedule_end_hour:
            return 0, 0, 0
        try:
            schedule_start = workday._decimal_hour_to_time(workday.schedule_start_hour, "inicio")
            schedule_end = workday._decimal_hour_to_time(workday.schedule_end_hour, "fin")
            schedule = Schedule(
                schedule_start,
                schedule_end,
                segments=workday._parsed_schedule_segments(schedule_start, schedule_end),
            )
            result = compute_ordinary(
                AttendanceInput(
                    work_date=workday.operational_date,
                    schedule=schedule,
                    first_mark=None,
                    last_mark=None,
                    count_marks=0,
                    justified_absence=True,
                )
            )
            return result.expected_minutes, result.ordinary_diurnal_min, result.ordinary_nocturnal_min
        except (TypeError, ValueError, ValidationError):
            return 0, 0, 0

    def _nov_day(self, employee, day, dataset):
        workday = dataset["workday_by_key"].get((employee.id, day))
        novelty = dataset["novelty_by_key"].get((employee.id, day))
        holiday = dataset["holiday_by_date"].get(day)
        manual_code = novelty.novelty_type_id.code.upper() if novelty else ""
        presence = self._has_presence(workday)
        if holiday and manual_code in {"", "O"}:
            code = "FT" if presence else "F"
        elif manual_code:
            code = manual_code
        elif presence:
            code = "P"
        else:
            code = ""
        theoretical, theoretical_diurnal, theoretical_nocturnal = self._theoretical_split(workday)
        return {
            "workday": workday,
            "novelty": novelty,
            "holiday": holiday,
            "code": code,
            "presence": presence,
            "theoretical": theoretical,
            "theoretical_diurnal": theoretical_diurnal,
            "theoretical_nocturnal": theoretical_nocturnal,
            "ordinary_diurnal": workday.ordinary_diurnal_min if workday else 0,
            "ordinary_nocturnal": workday.ordinary_nocturnal_min if workday else 0,
        }

    def _generate_nov_calendar(self):
        dataset = self._nov_dataset()
        dates = self._nov_dates()
        count_codes = list(self._novelty_codes_with_consultant_absence())
        headers = [
            "employee_id", "identification_id", "employee_name", "company",
            "nov_treatment", "consultant_code", "classification_warning",
        ] + [fields.Date.to_string(day) for day in dates]
        headers += ["%s_days" % code for code in count_codes]
        headers += ["q1_diurnal_h", "q1_nocturnal_h", "q2_diurnal_h", "q2_nocturnal_h"]
        rows = []
        for employee in dataset["employees"].sorted(key=lambda item: (item.name or "", item.id)):
            profile = dataset["profile_by_employee"].get(employee.id)
            treatment = profile.nov_treatment if profile else "unclassified"
            consultant = treatment == "consultant"
            consultant_code = profile.consultant_code if profile else ""
            warning = "" if treatment != "unclassified" else "NOV_TREATMENT_UNCLASSIFIED"
            cells = []
            counts = Counter()
            q1_d = q1_n = q2_d = q2_n = 0.0
            for day in dates:
                info = self._nov_day(employee, day, dataset)
                code = info["code"]
                display = code
                count_key = code
                if consultant:
                    if code == "P":
                        if day.weekday() >= 5 or info["holiday"]:
                            display = count_key = ""
                        else:
                            theoretical = info["theoretical"]
                            diurnal_min = info["ordinary_diurnal"]
                            nocturnal_min = info["ordinary_nocturnal"]
                            total = diurnal_min + nocturnal_min
                            if theoretical and total > theoretical:
                                scale = theoretical / total
                                diurnal_min *= scale
                                nocturnal_min *= scale
                            diurnal = round_consultant_novcal_minutes(diurnal_min)
                            nocturnal = round_consultant_novcal_minutes(nocturnal_min)
                            display = format_consultant_novcal_hours(diurnal, nocturnal)
                            count_key = "P"
                            if day.day <= 15:
                                q1_d += diurnal
                                q1_n += nocturnal
                            else:
                                q2_d += diurnal
                                q2_n += nocturnal
                    elif code == "FT":
                        display = count_key = ""
                    elif code in {"AI", "AJ"}:
                        display = count_key = "A"
                cells.append(display)
                if count_key:
                    counts[count_key] += 1
            rows.append(
                self._employee_values(employee)
                + [treatment, consultant_code or "", warning]
                + cells
                + [counts[code] for code in count_codes]
                + [q1_d, q1_n, q2_d, q2_n]
            )
        return headers, rows, {
            "workday_ids": dataset["workdays"].ids,
            "novelty_ids": dataset["novelties"].ids,
            "profile_ids": dataset["profiles"].ids,
            "holiday_ids": dataset["holidays"].ids,
        }

    @staticmethod
    def _novelty_codes_with_consultant_absence():
        return ("P", "AJ", "A", "AI", "S", "E", "V", "ART", "O", "D", "L", "LS", "F", "FT")

    def _generate_nov_summary(self):
        dataset = self._nov_dataset()
        dates = self._nov_dates()
        headers = [
            "employee_id", "identification_id", "employee_name", "company",
            "nov_treatment", "consultant_code", "classification_warning", "date_from", "date_to",
            "q1_theoretical_h", "q1_diurnal_h", "q1_nocturnal_h",
            "q2_theoretical_h", "q2_diurnal_h", "q2_nocturnal_h",
            "holiday_not_worked_h", "holiday_worked_h",
            "aj_q1_h", "aj_q2_h", "e_q1_h", "e_q2_h", "art_q1_h", "art_q2_h",
            "leave_paid_q1_h", "leave_paid_q2_h", "leave_paid_q1_days", "leave_paid_q2_days",
            "leave_unpaid_q1_days", "leave_unpaid_q2_days", "rest_q1_h", "rest_q2_h",
            "unjustified_q1_h", "unjustified_q2_h", "suspension_h", "vacation_days",
            "total_nov_h", "tardiness_min", "pending_days", "payable_overtime_h",
            "detected_excess_h", "unliquidated_overtime_h",
        ] + ["%s_days" % code for code in self._novelty_codes_with_consultant_absence() if code != "A"]
        rows = []
        for employee in dataset["employees"].sorted(key=lambda item: (item.name or "", item.id)):
            profile = dataset["profile_by_employee"].get(employee.id)
            treatment = profile.nov_treatment if profile else "unclassified"
            consultant = treatment == "consultant"
            consultant_code = profile.consultant_code if profile else ""
            warning = "" if treatment != "unclassified" else "NOV_TREATMENT_UNCLASSIFIED"
            values = Counter()
            counts = Counter()
            for day in dates:
                info = self._nov_day(employee, day, dataset)
                workday = info["workday"]
                code = info["code"]
                half = "q1" if day.day <= 15 else "q2"
                theoretical = info["theoretical"]
                if code:
                    counts[code] += 1
                if workday:
                    values["tardiness"] += workday.tardiness_min
                    values["payable_overtime"] += (
                        workday.payable_50_diurnal_min + workday.payable_50_nocturnal_min
                        + workday.payable_100_diurnal_min + workday.payable_100_nocturnal_min
                    )
                    values["detected"] += workday.detected_overtime_min
                    values["unliquidated"] += workday.unliquidated_overtime_min
                    if workday.state not in {"calculated", "audited", "closed"} or workday.warning_code:
                        values["pending"] += 1
                if code == "F":
                    values["fn"] += HOLIDAY_NOV_MINUTES
                    continue
                if code == "FT":
                    worked = info["ordinary_diurnal"] + info["ordinary_nocturnal"]
                    values["ft"] += worked
                    if info["presence"]:
                        values[half + "_theoretical"] += theoretical
                        values[half + "_diurnal"] += info["ordinary_diurnal"]
                        values[half + "_nocturnal"] += info["ordinary_nocturnal"]
                    continue
                if code == "V":
                    values["vacation_days"] += 1
                    continue
                if consultant:
                    if info["presence"] and code in {"", "P"}:
                        values[half + "_theoretical"] += theoretical
                        values[half + "_diurnal"] += info["ordinary_diurnal"]
                        values[half + "_nocturnal"] += info["ordinary_nocturnal"]
                    continue
                if code == "O":
                    values[half + "_theoretical"] += theoretical
                    values[half + "_diurnal"] += info["theoretical_diurnal"]
                    values[half + "_nocturnal"] += info["theoretical_nocturnal"]
                elif code in {"AJ", "E", "ART", "L", "D", "AI"}:
                    values[code.lower() + "_" + half] += theoretical
                    if code == "L":
                        values["l_days_" + half] += 1
                elif code == "LS":
                    values["ls_days_" + half] += 1
                elif code == "S":
                    values["suspension"] += theoretical
                elif info["presence"]:
                    values[half + "_theoretical"] += theoretical
                    values[half + "_diurnal"] += info["ordinary_diurnal"]
                    values[half + "_nocturnal"] += info["ordinary_nocturnal"]

            total = (
                values["q1_diurnal"] + values["q1_nocturnal"]
                + values["q2_diurnal"] + values["q2_nocturnal"] + values["fn"]
                + values["aj_q1"] + values["aj_q2"] + values["e_q1"] + values["e_q2"]
                + values["art_q1"] + values["art_q2"] + values["l_q1"] + values["l_q2"]
                + values["d_q1"] + values["d_q2"]
                - values["ai_q1"] - values["ai_q2"] - values["suspension"]
            )
            minute_columns = (
                "q1_theoretical", "q1_diurnal", "q1_nocturnal", "q2_theoretical", "q2_diurnal",
                "q2_nocturnal", "fn", "ft", "aj_q1", "aj_q2", "e_q1", "e_q2", "art_q1",
                "art_q2", "l_q1", "l_q2",
            )
            first_values = [round(values[key] / 60.0, 2) for key in minute_columns]
            first_values += [
                values["l_days_q1"], values["l_days_q2"], values["ls_days_q1"],
                values["ls_days_q2"], round(values["d_q1"] / 60.0, 2),
                round(values["d_q2"] / 60.0, 2), round(values["ai_q1"] / 60.0, 2),
                round(values["ai_q2"] / 60.0, 2), round(values["suspension"] / 60.0, 2),
                values["vacation_days"], round(total / 60.0, 2), values["tardiness"],
                values["pending"], round(values["payable_overtime"] / 60.0, 2),
                round(values["detected"] / 60.0, 2), round(values["unliquidated"] / 60.0, 2),
            ]
            rows.append(
                self._employee_values(employee)
                + [
                    treatment, consultant_code or "", warning,
                    fields.Date.to_string(self.date_from), fields.Date.to_string(self.date_to),
                ]
                + first_values
                + [counts[code] for code in self._novelty_codes_with_consultant_absence() if code != "A"]
            )
        return headers, rows, {
            "workday_ids": dataset["workdays"].ids,
            "novelty_ids": dataset["novelties"].ids,
            "profile_ids": dataset["profiles"].ids,
            "holiday_ids": dataset["holidays"].ids,
            "ruleset": "NOV_AUSENCIAS_LIQ_2026_08",
        }
