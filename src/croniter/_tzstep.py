"""Timezone stepping component.

Attaches timezone information back to a naive candidate datetime and
resolves DST transitions (nonexistent wall-clock times in spring, ambiguous
repeated wall-clock times in autumn).  This is deliberately independent of
both the field expansion (``_expand``) and the candidate matching
(``_match``) stages: it only sees a naive candidate, the aware previous
date, and a ``recalc`` callback used to ask the matcher for another
candidate when the first one falls inside a DST gap.
"""
import datetime

from dateutil.tz import datetime_exists

UTC_DT = datetime.timezone.utc


def is_successor(date: datetime.datetime, previous_date: datetime.datetime, is_prev: bool) -> bool:
    """Check if the given date is a successor (after/before) of the previous date."""
    if is_prev:
        return date.astimezone(UTC_DT) < previous_date.astimezone(UTC_DT)
    return date.astimezone(UTC_DT) > previous_date.astimezone(UTC_DT)


def timezone_delta(date1: datetime.datetime, date2: datetime.datetime) -> datetime.timedelta:
    """Calculate the timezone difference of the given dates."""
    offset1 = date1.utcoffset()
    offset2 = date2.utcoffset()
    assert offset1 is not None
    assert offset2 is not None
    return offset2 - offset1


def _localize_pytz(date, previous_date, is_prev, localize):
    """pytz flavor of add_tzinfo, using the tzinfo's own localize()."""
    # pylint: disable-next=import-outside-toplevel
    import pytz

    try:
        result = localize(date, is_dst=None)
    except pytz.NonExistentTimeError:
        while True:
            date += datetime.timedelta(minutes=1)
            try:
                result = localize(date, is_dst=None)
            except pytz.NonExistentTimeError:
                continue
            break
        return result, False
    except pytz.AmbiguousTimeError:
        closer = localize(date, is_dst=not is_prev)
        farther = localize(date, is_dst=is_prev)
        # TODO: Check negative DST
        assert (closer.astimezone(UTC_DT) > farther.astimezone(UTC_DT)) == is_prev
        if is_successor(closer, previous_date, is_prev):
            result = closer
        else:
            assert is_successor(farther, previous_date, is_prev)
            result = farther
    return result, True


def add_tzinfo(
    date: datetime.datetime, previous_date: datetime.datetime, is_prev: bool
) -> tuple[datetime.datetime, bool]:
    """Add the tzinfo from the previous date to the given date.

    In case the new date is ambiguous, determine the correct date
    based on it being closer to the previous date but still a successor
    (after/before based on `is_prev`).

    In case the date does not exist, jump forward to the next existing date.
    """
    localize = getattr(previous_date.tzinfo, "localize", None)
    if localize is not None:
        return _localize_pytz(date, previous_date, is_prev, localize)

    result = date.replace(fold=1 if is_prev else 0, tzinfo=previous_date.tzinfo)
    if not datetime_exists(result):
        while not datetime_exists(result):
            result += datetime.timedelta(minutes=1)
        return result, False

    # result is closer to the previous date
    farther = date.replace(fold=0 if is_prev else 1, tzinfo=previous_date.tzinfo)
    # Comparing the UTC offsets in the check for the date being ambiguous.
    if result.utcoffset() != farther.utcoffset():
        # TODO: Check negative DST
        assert (result.astimezone(UTC_DT) > farther.astimezone(UTC_DT)) == is_prev
        if not is_successor(result, previous_date, is_prev):
            assert is_successor(farther, previous_date, is_prev)
            result = farther
    return result, True


def localize_candidate(now, unaware_time, is_prev, recalc, hour_field_is_star):
    """Re-attach ``now``'s timezone to a naive candidate and fix up DST.

    ``recalc`` is the matcher's step function (``unaware -> aware-naive``)
    used to fetch another candidate when the current one does not exist in
    local time, or to probe the alternative UTC offset after a DST change.
    """
    aware_time, exists = add_tzinfo(unaware_time, now, is_prev)

    if not exists and (not is_successor(aware_time, now, is_prev) or hour_field_is_star):
        # The calculated local date does not exist and moving the time forward
        # to the next valid time isn't the correct solution. Search for the
        # next matching cron time that exists.
        while not exists:
            unaware_time = recalc(unaware_time)
            aware_time, exists = add_tzinfo(unaware_time, now, is_prev)

    offset_delta = timezone_delta(now, aware_time)
    if not offset_delta:
        # There was no DST change.
        return aware_time

    # There was a DST change. So check if there is a alternative cron time
    # for the other UTC offset.
    alternative_unaware_time = now.replace(tzinfo=None) + offset_delta
    alternative_unaware_time = recalc(alternative_unaware_time)
    alternative_aware_time, exists = add_tzinfo(alternative_unaware_time, now, is_prev)

    if not is_successor(alternative_aware_time, now, is_prev):
        # The alternative time is an ancestor of now. Thus it is not an alternative.
        return aware_time

    if is_successor(aware_time, alternative_aware_time, is_prev):
        return alternative_aware_time

    return aware_time
