from __future__ import annotations

from dataclasses import dataclass
from datetime import date, datetime, time, timedelta
from enum import Enum
from math import floor
from typing import Iterable


class DayRegime(str, Enum):
    WORKDAY = "laborable"
    SATURDAY = "sabado"
    SUNDAY = "domingo"
    HOLIDAY = "feriado"


class RoundMode(str, Enum):
    FULL_HOUR = "hora_entera"
    THRESHOLD25_BLOCK30 = "umbral25_bloques30"


class SaturdayRule(str, Enum):
    OFFICIAL_GENERAL = "oficial_general"
    CDE_567_DOCUMENTED = "cde_567_documentada"


class TardinessRule(str, Enum):
    CURRENT_FIRST_HOUR_AFTER_20 = "actual_primera_hora_mayor_20"
    MINUTE_BY_MINUTE = "minuto_a_minuto"


@dataclass(frozen=True)
class Schedule:
    start: time
    end: time
    segments: tuple[tuple[time, time], ...] = ()

    def __post_init__(self):
        if self.start == self.end:
            raise ValueError("Schedule start and end must be different")
        normalized = tuple(self.segments) or ((self.start, self.end),)
        if any(segment_start == segment_end for segment_start, segment_end in normalized):
            raise ValueError("Schedule segments must have different start and end")
        if normalized[0][0] != self.start or normalized[-1][1] != self.end:
            raise ValueError("Schedule boundaries must match its first and last segment")
        object.__setattr__(self, "segments", normalized)

    @property
    def crosses_midnight(self) -> bool:
        return self.end <= self.start

    @property
    def duration_minutes(self) -> int:
        return sum(
            _minutes_between(start, end)
            for start, end in _schedule_windows(date(2000, 1, 1), self)
        )


@dataclass(frozen=True)
class EnginePolicy:
    night_start: time = time(21, 0)
    night_end: time = time(6, 0)
    tardiness_rule: TardinessRule = TardinessRule.CURRENT_FIRST_HOUR_AFTER_20
    tardiness_first_hour_threshold_min: int = 20
    workday_first_50_min: int = 6 * 60
    workday_round_mode: RoundMode = RoundMode.FULL_HOUR
    nonworkday_round_mode: RoundMode = RoundMode.THRESHOLD25_BLOCK30
    saturday_rule: SaturdayRule = SaturdayRule.OFFICIAL_GENERAL
    saturday_early_start_max: time = time(7, 0)
    saturday_early_50_until: time = time(13, 0)
    saturday_late_first_50_min: int = 6 * 60
    saturday_all_100_from: time = time(12, 0)
    saturday_start_round_up_from_minute: int = 35
    sunday_start_keep_through_minute: int = 20
    night_operational_margin_hours: int = 5
    night_operational_min_cutoff: time = time(6, 0)
    night_operational_max_cutoff: time = time(10, 0)
    afternoon_operational_cutoff: time = time(4, 0)


@dataclass(frozen=True)
class AttendanceInput:
    work_date: date
    schedule: Schedule
    first_mark: datetime | None
    last_mark: datetime | None
    count_marks: int = 2
    assume_theoretical: bool = False
    justified_absence: bool = False
    corrected_marks: bool = False


@dataclass(frozen=True)
class OrdinaryResult:
    expected_start: datetime
    expected_end: datetime
    expected_minutes: int
    ordinary_diurnal_min: int
    ordinary_nocturnal_min: int
    tardiness_min: int
    first_hour_penalty_min: int
    journey_type: str
    effective_work_start: datetime | None
    effective_work_end: datetime | None
    effective_work_minutes: int

    @property
    def ordinary_total_min(self) -> int:
        return self.ordinary_diurnal_min + self.ordinary_nocturnal_min


@dataclass(frozen=True)
class OvertimeResult:
    regime: DayRegime
    detected_excess_min: int
    base_raw_min: int
    raw_50_diurnal_min: int
    raw_50_nocturnal_min: int
    raw_100_diurnal_min: int
    raw_100_nocturnal_min: int
    payable_50_diurnal_min: int
    payable_50_nocturnal_min: int
    payable_100_diurnal_min: int
    payable_100_nocturnal_min: int
    unliquidated_min: int
    authorized: bool
    excluded: bool
    round_mode: RoundMode

    @property
    def payable_total_min(self) -> int:
        return (
            self.payable_50_diurnal_min
            + self.payable_50_nocturnal_min
            + self.payable_100_diurnal_min
            + self.payable_100_nocturnal_min
        )


def _minutes_between(start: datetime, end: datetime) -> int:
    seconds = max(0.0, (end - start).total_seconds())
    return int(floor(seconds / 60.0 + 0.5))


def _clock_minutes(value: time) -> int:
    return value.hour * 60 + value.minute


def _window(work_date: date, schedule: Schedule) -> tuple[datetime, datetime]:
    windows = _schedule_windows(work_date, schedule)
    return windows[0][0], windows[-1][1]


def _schedule_windows(
    work_date: date, schedule: Schedule
) -> list[tuple[datetime, datetime]]:
    windows: list[tuple[datetime, datetime]] = []
    previous_end: datetime | None = None
    for segment_start, segment_end in schedule.segments:
        start = datetime.combine(work_date, segment_start)
        if previous_end is not None and start < previous_end:
            if previous_end.date() == work_date:
                raise ValueError("Schedule segments must be ordered and non-overlapping")
            while start < previous_end:
                start += timedelta(days=1)
        end = datetime.combine(start.date(), segment_end)
        if end <= start:
            end += timedelta(days=1)
        windows.append((start, end))
        previous_end = end
    return windows


def _intersect_windows(
    windows: Iterable[tuple[datetime, datetime]],
    actual: tuple[datetime, datetime],
) -> list[tuple[datetime, datetime]]:
    actual_start, actual_end = actual
    result = []
    for start, end in windows:
        overlap_start = max(start, actual_start)
        overlap_end = min(end, actual_end)
        if overlap_end > overlap_start:
            result.append((overlap_start, overlap_end))
    return result


def _subtract_window(
    segment: tuple[datetime, datetime],
    cut: tuple[datetime, datetime],
) -> list[tuple[datetime, datetime]]:
    start, end = segment
    cut_start, cut_end = cut
    if cut_end <= start or cut_start >= end:
        return [segment]
    result: list[tuple[datetime, datetime]] = []
    if start < cut_start:
        result.append((start, min(cut_start, end)))
    if cut_end < end:
        result.append((max(cut_end, start), end))
    return [item for item in result if item[1] > item[0]]


def _split_diurnal_nocturnal(
    segments: Iterable[tuple[datetime, datetime]],
    policy: EnginePolicy,
) -> tuple[int, int]:
    total = 0
    nocturnal = 0
    for start, end in segments:
        if end <= start:
            continue
        segment_min = _minutes_between(start, end)
        total += segment_min
        cursor = start.date() - timedelta(days=1)
        final_date = end.date()
        while cursor <= final_date:
            night_start = datetime.combine(cursor, policy.night_start)
            night_end = datetime.combine(cursor + timedelta(days=1), policy.night_end)
            overlap_start = max(start, night_start)
            overlap_end = min(end, night_end)
            if overlap_end > overlap_start:
                nocturnal += _minutes_between(overlap_start, overlap_end)
            cursor += timedelta(days=1)
    nocturnal = min(nocturnal, total)
    return total - nocturnal, nocturnal


def _journey_type(diurnal: int, nocturnal: int) -> str:
    if diurnal and nocturnal:
        return "mixta"
    if nocturnal:
        return "nocturna_integra"
    if diurnal:
        return "diurna"
    return ""


def compute_ordinary(
    attendance: AttendanceInput,
    policy: EnginePolicy | None = None,
) -> OrdinaryResult:
    policy = policy or EnginePolicy()
    expected_windows = _schedule_windows(attendance.work_date, attendance.schedule)
    expected_start, expected_end = expected_windows[0][0], expected_windows[-1][1]
    expected_minutes = sum(_minutes_between(start, end) for start, end in expected_windows)
    first = attendance.first_mark
    last = attendance.last_mark

    if attendance.justified_absence and first is None and last is None:
        diurnal, nocturnal = _split_diurnal_nocturnal(expected_windows, policy)
        return OrdinaryResult(
            expected_start,
            expected_end,
            expected_minutes,
            diurnal,
            nocturnal,
            0,
            0,
            _journey_type(diurnal, nocturnal),
            None,
            None,
            0,
        )

    if attendance.assume_theoretical and first is not None:
        tardiness = max(0, _minutes_between(expected_start, first)) if first > expected_start else 0
        diurnal, nocturnal = _split_diurnal_nocturnal(expected_windows, policy)
        return OrdinaryResult(
            expected_start,
            expected_end,
            expected_minutes,
            diurnal,
            nocturnal,
            tardiness,
            0,
            _journey_type(diurnal, nocturnal),
            max(first, expected_start),
            last,
            _minutes_between(max(first, expected_start), last) if last and last > max(first, expected_start) else 0,
        )

    if first is None or last is None or last <= first:
        return OrdinaryResult(
            expected_start, expected_end, expected_minutes, 0, 0, 0, 0, "", None, None, 0
        )

    tardiness = max(0, _minutes_between(expected_start, first)) if first > expected_start else 0
    effective_start = max(first, expected_start)
    effective_end = last
    effective_minutes = _minutes_between(effective_start, effective_end) if effective_end > effective_start else 0
    comp_end = min(last, expected_end)
    segments = _intersect_windows(expected_windows, (effective_start, comp_end))
    if not segments:
        return OrdinaryResult(
            expected_start,
            expected_end,
            expected_minutes,
            0,
            0,
            tardiness,
            0,
            "",
            effective_start,
            effective_end,
            effective_minutes,
        )

    penalty = 0
    if (
        policy.tardiness_rule == TardinessRule.CURRENT_FIRST_HOUR_AFTER_20
        and tardiness > policy.tardiness_first_hour_threshold_min
    ):
        first_hour = (expected_start, expected_start + timedelta(hours=1))
        reduced = []
        for segment in segments:
            before = _minutes_between(*segment)
            remaining = _subtract_window(segment, first_hour)
            after = sum(_minutes_between(start, end) for start, end in remaining)
            penalty += before - after
            reduced.extend(remaining)
        segments = reduced

    diurnal, nocturnal = _split_diurnal_nocturnal(segments, policy)
    return OrdinaryResult(
        expected_start,
        expected_end,
        expected_minutes,
        diurnal,
        nocturnal,
        tardiness,
        penalty,
        _journey_type(diurnal, nocturnal),
        effective_start,
        effective_end,
        effective_minutes,
    )


def round_consultant_novcal_minutes(minutes: int | float) -> float:
    value = max(0, int(floor(float(minutes or 0) + 0.5)))
    hours, remainder = divmod(value, 60)
    if remainder >= 50:
        return float(hours + 1)
    if remainder >= 30:
        return hours + 0.5
    return float(hours)


def format_consultant_novcal_hours(diurnal: float, nocturnal: float) -> str:
    def label(value: float) -> str:
        return str(int(value)) if value == int(value) else str(value)

    if diurnal <= 0 and nocturnal <= 0:
        return "0"
    if nocturnal <= 0:
        return label(diurnal)
    if diurnal <= 0:
        return "0 + %s" % label(nocturnal)
    return "%s + %s" % (label(diurnal), label(nocturnal))

def round_minutes(minutes: int, mode: RoundMode) -> int:
    value = max(0, int(minutes))
    if mode == RoundMode.THRESHOLD25_BLOCK30:
        if value < 25:
            return 0
        return floor(value / 30) * 30
    return floor(value / 60) * 60


def _split_interval_at(
    start: datetime,
    end: datetime,
    split: datetime,
) -> tuple[list[tuple[datetime, datetime]], list[tuple[datetime, datetime]]]:
    if split <= start:
        return [], [(start, end)]
    if split >= end:
        return [(start, end)], []
    return [(start, split)], [(split, end)]


def _rounded_saturday_start(mark: datetime, policy: EnginePolicy) -> datetime:
    if mark.minute >= policy.saturday_start_round_up_from_minute:
        return mark.replace(minute=0, second=0, microsecond=0) + timedelta(hours=1)
    return mark.replace(minute=0, second=0, microsecond=0)


def _rounded_sunday_start(mark: datetime, policy: EnginePolicy) -> datetime:
    if mark.minute <= policy.sunday_start_keep_through_minute:
        return mark.replace(second=0, microsecond=0)
    return mark.replace(minute=0, second=0, microsecond=0) + timedelta(hours=1)


def _empty_overtime(
    regime: DayRegime,
    detected: int,
    authorized: bool,
    excluded: bool,
    mode: RoundMode,
) -> OvertimeResult:
    return OvertimeResult(
        regime,
        detected,
        0,
        0,
        0,
        0,
        0,
        0,
        0,
        0,
        0,
        detected,
        authorized,
        excluded,
        mode,
    )


def compute_overtime(
    attendance: AttendanceInput,
    ordinary: OrdinaryResult,
    regime: DayRegime,
    *,
    authorized: bool = False,
    excluded: bool = False,
    company: str = "",
    schedule_code: int | None = None,
    policy: EnginePolicy | None = None,
) -> OvertimeResult:
    policy = policy or EnginePolicy()
    first = attendance.first_mark
    last = attendance.last_mark
    mode = policy.workday_round_mode if regime == DayRegime.WORKDAY else policy.nonworkday_round_mode
    if (
        first is None
        or last is None
        or last <= first
        or (attendance.count_marks == 1 and not attendance.corrected_marks)
    ):
        return _empty_overtime(regime, 0, authorized, excluded, mode)

    expected_for_day = (
        _minutes_between(ordinary.expected_start, ordinary.expected_end)
        if regime == DayRegime.WORKDAY
        else 0
    )
    effective_start = max(first, ordinary.expected_start) if regime == DayRegime.WORKDAY else first
    effective_work = _minutes_between(effective_start, last) if last > effective_start else 0
    detected = max(0, effective_work - expected_for_day)
    if detected <= 0:
        return _empty_overtime(regime, 0, authorized, excluded, mode)

    intervals_50: list[tuple[datetime, datetime]] = []
    intervals_100: list[tuple[datetime, datetime]] = []

    if regime == DayRegime.WORKDAY:
        base_start = effective_start + timedelta(minutes=expected_for_day)
        if last <= base_start:
            return _empty_overtime(regime, detected, authorized, excluded, mode)
        split = base_start + timedelta(minutes=policy.workday_first_50_min)
        intervals_50, intervals_100 = _split_interval_at(base_start, last, split)
    elif regime == DayRegime.SATURDAY:
        if (
            policy.saturday_rule == SaturdayRule.CDE_567_DOCUMENTED
            and company.strip().upper() == "CDE"
            and schedule_code in {5, 6, 7}
        ):
            base_start = first + timedelta(hours=4)
            if last <= base_start:
                return _empty_overtime(regime, detected, authorized, excluded, mode)
            intervals_50 = [(base_start, last)]
        else:
            base_start = _rounded_saturday_start(first, policy)
            if last <= base_start:
                return _empty_overtime(regime, detected, authorized, excluded, mode)
            start_clock = base_start.time()
            if start_clock >= policy.saturday_all_100_from:
                intervals_100 = [(base_start, last)]
            else:
                if start_clock <= policy.saturday_early_start_max:
                    split = datetime.combine(attendance.work_date, policy.saturday_early_50_until)
                else:
                    split = base_start + timedelta(minutes=policy.saturday_late_first_50_min)
                intervals_50, intervals_100 = _split_interval_at(base_start, last, split)
    else:
        base_start = _rounded_sunday_start(first, policy)
        if last <= base_start:
            return _empty_overtime(regime, detected, authorized, excluded, mode)
        intervals_100 = [(base_start, last)]

    raw_50_d, raw_50_n = _split_diurnal_nocturnal(intervals_50, policy)
    raw_100_d, raw_100_n = _split_diurnal_nocturnal(intervals_100, policy)
    base_raw = raw_50_d + raw_50_n + raw_100_d + raw_100_n
    is_payable = authorized and not excluded
    pay_50_d = round_minutes(raw_50_d, mode) if is_payable else 0
    pay_50_n = round_minutes(raw_50_n, mode) if is_payable else 0
    pay_100_d = round_minutes(raw_100_d, mode) if is_payable else 0
    pay_100_n = round_minutes(raw_100_n, mode) if is_payable else 0
    payable_total = pay_50_d + pay_50_n + pay_100_d + pay_100_n
    unliquidated = detected if not is_payable else max(0, base_raw - payable_total)

    return OvertimeResult(
        regime,
        detected,
        base_raw,
        raw_50_d,
        raw_50_n,
        raw_100_d,
        raw_100_n,
        pay_50_d,
        pay_50_n,
        pay_100_d,
        pay_100_n,
        unliquidated,
        authorized,
        excluded,
        mode,
    )


def operational_date(
    mark: datetime,
    schedule: Schedule | None,
    *,
    declared_night: bool = False,
    declared_afternoon: bool = False,
    previous_day_expected: bool = True,
    policy: EnginePolicy | None = None,
) -> date:
    policy = policy or EnginePolicy()
    clock = mark.time()
    if declared_afternoon and clock < policy.afternoon_operational_cutoff:
        return mark.date() - timedelta(days=1) if previous_day_expected else mark.date()

    crosses = bool(schedule and schedule.crosses_midnight)
    if not (declared_night or crosses):
        return mark.date()

    end_min = _clock_minutes(schedule.end) if schedule else 6 * 60
    cutoff_min = end_min + policy.night_operational_margin_hours * 60
    cutoff_min = max(cutoff_min, _clock_minutes(policy.night_operational_min_cutoff))
    cutoff_min = min(cutoff_min, _clock_minutes(policy.night_operational_max_cutoff))
    mark_min = mark.hour * 60 + mark.minute
    if mark_min < cutoff_min and previous_day_expected:
        return mark.date() - timedelta(days=1)
    return mark.date()

