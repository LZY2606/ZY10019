"""Date candidate matching component.

Given an already-expanded expression (see ``_expand``) and a naive start
datetime, step field-by-field (year, month, day, hour, minute, second) to
the next or previous local wall-clock time that matches every field.  The
result is still timezone-unaware; re-attaching the timezone and resolving
DST is the job of ``_tzstep.localize_candidate``, which this module calls
at the end of each step (and which may call back into :meth:`find_match`
via the ``recalc`` callback for DST gap handling).
"""
import calendar
import datetime

from dateutil.relativedelta import relativedelta

from ._const import (
    DAY_FIELD,
    DOW_FIELD,
    HOUR_FIELD,
    MINUTE_FIELD,
    MONTH_FIELD,
    SECOND_FIELD,
    UNIX_CRON_LEN,
    YEAR_CRON_LEN,
    YEAR_FIELD,
    DAYS,
    ExpandedExpression,
)
from ._exceptions import CroniterBadDateError
from ._tzstep import localize_candidate

MONTHS_IN_YEAR = 12


def _is_leap(year: int) -> bool:
    return year % 400 == 0 or (year % 4 == 0 and year % 100 != 0)


def _last_day_of_month(year: int, month: int) -> int:
    """Calculate the last day of the given month (honor leap years)."""
    last_day = DAYS[month - 1]
    if month == 2 and _is_leap(year):
        last_day += 1
    return last_day


def next_nearest_diff(x, to_check, range_val):
    """
    `range_val` is the range of a field.
    If no available time, we can move to next loop(like next month).
    `range_val` can also be set to `None` to indicate that there is no loop.
    ( Currently, should only used for `year` field )
    """
    for i, d in enumerate(to_check):
        if range_val is not None:
            if d == "l":
                # if 'l' then it is the last day of month
                # => its value of range_val
                d = range_val
            elif d > range_val:
                continue
        if d >= x:
            return d - x
    # When range_val is None and x not exists in to_check,
    # `None` will be returned to suggest no more available time
    if range_val is None:
        return None
    return to_check[0] - x + range_val


def prev_nearest_diff(x, to_check, range_val):
    """
    `range_val` is the range of a field.
    If no available time, we can move to previous loop(like previous month).
    Range_val can also be set to `None` to indicate that there is no loop.
    ( Currently should only used for `year` field )
    """
    candidates = to_check[:]
    candidates.reverse()
    for d in candidates:
        if d != "l" and d <= x:
            return d - x
    if "l" in candidates:
        return -x
    # When range_val is None and x not exists in to_check,
    # `None` will be returned to suggest no more available time
    if range_val is None:
        return None
    candidate = candidates[0]
    for c in candidates:
        # fixed: c < range_val
        # this code will reject all 31 day of month, 12 month, 59 second,
        # 23 hour and so on.
        # if candidates has just a element, this will not harmful.
        # but candidates have multiple elements, then values equal to
        # range_val will rejected.
        if c <= range_val:
            candidate = c
            break
    # fix crontab "0 6 30 3 *" condidates only a element, then get_prev error
    # return 2021-03-02 06:00:00
    if candidate > range_val:
        return -range_val
    return candidate - x - range_val


def nth_weekday_of_month_days(year: int, month: int, day_of_week: int) -> tuple[int, ...]:
    """For a given year/month return a list of days in nth-day-of-month order.
    The last weekday of the month is always [-1].
    """
    w = (day_of_week + 6) % 7
    c = calendar.Calendar(w).monthdayscalendar(year, month)
    if c[0][0] == 0:
        c.pop(0)
    return tuple(i[0] for i in c)


def nearest_weekday_day(year, month, day):
    """Get the nearest weekday (Mon-Fri) to the given day in the given month.

    Rules:
    - If the day is a weekday, return it.
    - If Saturday, return Friday (day-1), unless that crosses into previous month,
      then return Monday (day+2).
    - If Sunday, return Monday (day+1), unless that crosses into next month,
      then return Friday (day-2).
    """
    last_day = _last_day_of_month(year, month)
    day = min(day, last_day)
    weekday = calendar.weekday(year, month, day)  # 0=Mon, 6=Sun
    if weekday < 5:  # Mon-Fri
        return day
    if weekday == 5:  # Saturday
        if day > 1:
            return day - 1  # Friday
        else:
            return day + 2  # Monday (1st is Sat, so 3rd is Mon)
    # Sunday
    if day < last_day:
        return day + 1  # Monday
    else:
        return day - 2  # Friday (last day is Sun, go back to Fri)


def find_match(
    now: datetime.datetime,
    expanded: list[ExpandedExpression],
    nth_weekday_of_month: dict[int, set[int]],
    nearest_weekday,
    max_years_between_matches: int,
    is_prev: bool,
    months_in_year: int = MONTHS_IN_YEAR,
) -> datetime.datetime:
    """Find the next/previous local wall-clock time matching the expanded fields.

    This is the candidate-matching stage: it works purely on naive local
    datetimes and delegates timezone re-attachment to ``_tzstep``.
    """
    stepper = _FieldStepper(
        expanded, nth_weekday_of_month, nearest_weekday, max_years_between_matches,
        is_prev, months_in_year,
    )
    return stepper.step(now)


class _FieldStepper:
    """Per-step matching state: the expanded fields plus the search direction.

    The ``proc_*`` methods each try to move one field of the candidate ``d``
    closer to a match and return ``(changed, d)``; ``changed is None`` means
    the search ran out of representable years.  At the time each proc is
    called, ``d`` is the current candidate, so the current month and year are
    always available as ``d.month`` / ``d.year``.
    """

    def __init__(self, expanded, nth_weekday_of_month, nearest_weekday,
                 max_years_between_matches, is_prev, months_in_year=MONTHS_IN_YEAR):
        self.expanded = expanded
        self.nth_weekday_of_month = nth_weekday_of_month
        self.nearest_weekday = nearest_weekday
        self.max_years_between_matches = max_years_between_matches
        self.is_prev = is_prev
        self.months_in_year = months_in_year
        self.nearest_diff_method = prev_nearest_diff if is_prev else next_nearest_diff
        self.procs = [
            self.proc_year,
            self.proc_month,
            self.proc_nearest_weekday if nearest_weekday else self.proc_day_of_month,
            self.proc_day_of_week_nth if nth_weekday_of_month else self.proc_day_of_week,
            self.proc_hour,
            self.proc_minute,
            self.proc_second,
        ]

    def proc_year(self, d):
        if len(self.expanded) == YEAR_CRON_LEN:
            try:
                self.expanded[YEAR_FIELD].index("*")
            except ValueError:
                # use None as range_val to indicate no loop
                diff_year = self.nearest_diff_method(d.year, self.expanded[YEAR_FIELD], None)
                if diff_year is None:
                    return None, d
                if diff_year != 0:
                    if self.is_prev:
                        d += relativedelta(
                            years=diff_year, month=12, day=31, hour=23, minute=59, second=59
                        )
                    else:
                        d += relativedelta(
                            years=diff_year, month=1, day=1, hour=0, minute=0, second=0
                        )
                    return True, d
        return False, d

    def proc_month(self, d):
        try:
            self.expanded[MONTH_FIELD].index("*")
        except ValueError:
            diff_month = self.nearest_diff_method(
                d.month, self.expanded[MONTH_FIELD], self.months_in_year
            )
            reset_day = 1

            if diff_month is not None and diff_month != 0:
                if self.is_prev:
                    d += relativedelta(months=diff_month)
                    reset_day = _last_day_of_month(d.year, d.month)
                    d += relativedelta(day=reset_day, hour=23, minute=59, second=59)
                else:
                    d += relativedelta(
                        months=diff_month, day=reset_day, hour=0, minute=0, second=0
                    )
                return True, d
        return False, d

    def proc_day_of_month(self, d):
        try:
            self.expanded[DAY_FIELD].index("*")
        except ValueError:
            days = _last_day_of_month(d.year, d.month)
            if "l" in self.expanded[DAY_FIELD] and days == d.day:
                return False, d

            if self.is_prev:
                prev_month = (d.month - 2) % self.months_in_year + 1
                prev_year = d.year - 1 if d.month == 1 else d.year
                days_in_prev_month = _last_day_of_month(prev_year, prev_month)
                diff_day = self.nearest_diff_method(
                    d.day, self.expanded[DAY_FIELD], days_in_prev_month
                )
            else:
                diff_day = self.nearest_diff_method(d.day, self.expanded[DAY_FIELD], days)

            if diff_day is not None and diff_day != 0:
                if self.is_prev:
                    d += relativedelta(days=diff_day, hour=23, minute=59, second=59)
                else:
                    d += relativedelta(days=diff_day, hour=0, minute=0, second=0)
                return True, d
        return False, d

    def proc_day_of_week(self, d):
        try:
            self.expanded[DOW_FIELD].index("*")
        except ValueError:
            diff_day_of_week = self.nearest_diff_method(
                d.isoweekday() % 7, self.expanded[DOW_FIELD], 7
            )
            if diff_day_of_week is not None and diff_day_of_week != 0:
                if self.is_prev:
                    d += relativedelta(days=diff_day_of_week, hour=23, minute=59, second=59)
                else:
                    d += relativedelta(days=diff_day_of_week, hour=0, minute=0, second=0)
                return True, d
        return False, d

    def proc_day_of_week_nth(self, d):
        nth_weekday_of_month = self.nth_weekday_of_month
        if "*" in nth_weekday_of_month:
            s = nth_weekday_of_month["*"]
            for i in range(0, 7):
                if i in nth_weekday_of_month:
                    nth_weekday_of_month[i].update(s)
                else:
                    nth_weekday_of_month[i] = s
            del nth_weekday_of_month["*"]

        candidates = []
        for wday, nth in nth_weekday_of_month.items():
            c = nth_weekday_of_month_days(d.year, d.month, wday)
            for n in nth:
                if n == "l":
                    candidate = c[-1]
                elif len(c) < n:
                    continue
                else:
                    candidate = c[n - 1]
                if (self.is_prev and candidate <= d.day) or (
                    not self.is_prev and d.day <= candidate
                ):
                    candidates.append(candidate)

        if not candidates:
            if self.is_prev:
                d += relativedelta(days=-d.day, hour=23, minute=59, second=59)
            else:
                days = _last_day_of_month(d.year, d.month)
                d += relativedelta(days=(days - d.day + 1), hour=0, minute=0, second=0)
            return True, d

        candidates.sort()
        diff_day = (candidates[-1] if self.is_prev else candidates[0]) - d.day
        if diff_day != 0:
            if self.is_prev:
                d += relativedelta(days=diff_day, hour=23, minute=59, second=59)
            else:
                d += relativedelta(days=diff_day, hour=0, minute=0, second=0)
            return True, d
        return False, d

    def proc_nearest_weekday(self, d):
        """Process W (nearest weekday) day-of-month entries."""
        candidates = []
        for w_day in self.nearest_weekday:
            candidate = nearest_weekday_day(d.year, d.month, w_day)
            if (self.is_prev and candidate <= d.day) or (not self.is_prev and d.day <= candidate):
                candidates.append(candidate)

        if not candidates:
            if self.is_prev:
                d += relativedelta(days=-d.day, hour=23, minute=59, second=59)
            else:
                days = _last_day_of_month(d.year, d.month)
                d += relativedelta(days=(days - d.day + 1), hour=0, minute=0, second=0)
            return True, d

        candidates.sort()
        diff_day = (candidates[-1] if self.is_prev else candidates[0]) - d.day
        if diff_day != 0:
            if self.is_prev:
                d += relativedelta(days=diff_day, hour=23, minute=59, second=59)
            else:
                d += relativedelta(days=diff_day, hour=0, minute=0, second=0)
            return True, d
        return False, d

    def proc_hour(self, d):
        try:
            self.expanded[HOUR_FIELD].index("*")
        except ValueError:
            diff_hour = self.nearest_diff_method(d.hour, self.expanded[HOUR_FIELD], 24)
            if diff_hour is not None and diff_hour != 0:
                if self.is_prev:
                    d += relativedelta(hours=diff_hour, minute=59, second=59)
                else:
                    d += relativedelta(hours=diff_hour, minute=0, second=0)
                return True, d
        return False, d

    def proc_minute(self, d):
        try:
            self.expanded[MINUTE_FIELD].index("*")
        except ValueError:
            diff_min = self.nearest_diff_method(d.minute, self.expanded[MINUTE_FIELD], 60)
            if diff_min is not None and diff_min != 0:
                if self.is_prev:
                    d += relativedelta(minutes=diff_min, second=59)
                else:
                    d += relativedelta(minutes=diff_min, second=0)
                return True, d
        return False, d

    def proc_second(self, d):
        if len(self.expanded) > UNIX_CRON_LEN:
            try:
                self.expanded[SECOND_FIELD].index("*")
            except ValueError:
                diff_sec = self.nearest_diff_method(d.second, self.expanded[SECOND_FIELD], 60)
                if diff_sec is not None and diff_sec != 0:
                    d += relativedelta(seconds=diff_sec)
                    return True, d
        else:
            d += relativedelta(second=0)
        return False, d

    def step(self, now: datetime.datetime) -> datetime.datetime:
        expanded = self.expanded
        is_prev = self.is_prev
        if is_prev:
            offset = relativedelta(microseconds=-1)
        elif len(expanded) > UNIX_CRON_LEN:
            offset = relativedelta(seconds=1)
        else:
            offset = relativedelta(minutes=1)
        # Calculate the next cron time in local time a.k.a. timezone unaware time.
        unaware_time = now.replace(tzinfo=None) + offset
        if len(expanded) > UNIX_CRON_LEN:
            unaware_time = unaware_time.replace(microsecond=0)
        else:
            unaware_time = unaware_time.replace(second=0, microsecond=0)

        year = current_year = unaware_time.year

        while abs(year - current_year) <= self.max_years_between_matches:
            next = False
            stop = False
            for proc in self.procs:
                (changed, unaware_time) = proc(unaware_time)
                # `None` can be set mostly for year processing
                # so please see proc_year / prev_nearest_diff / next_nearest_diff
                if changed is None:
                    stop = True
                    break
                if changed:
                    year = unaware_time.year
                    next = True
                    break
            if stop:
                break
            if next:
                continue

            unaware_time = unaware_time.replace(microsecond=0)
            if now.tzinfo is None:
                return unaware_time

            # Add timezone information back and handle DST changes
            return localize_candidate(
                now,
                unaware_time,
                is_prev,
                recalc=self.step,
                hour_field_is_star="*" in expanded[HOUR_FIELD],
            )

        if is_prev:
            raise CroniterBadDateError("failed to find prev date")
        raise CroniterBadDateError("failed to find next date")
