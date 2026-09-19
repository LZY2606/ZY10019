"""Shared constants for the croniter internals.

This module sits at the bottom of the internal dependency graph so that
``_expand`` (field normalization/expansion), ``_match`` (date candidate
matching) and ``_tzstep`` (timezone stepping) can all import it without
cycles.  Everything here is re-exported from ``croniter.croniter`` to keep
the historical module layout intact for downstream imports.
"""
from typing import Literal, Union

ExpandedExpression = list[Union[int, Literal["*", "l"]]]

M_ALPHAS: dict[str, Union[int, str]] = {
    "jan": 1,
    "feb": 2,
    "mar": 3,
    "apr": 4,
    "may": 5,
    "jun": 6,
    "jul": 7,
    "aug": 8,
    "sep": 9,
    "oct": 10,
    "nov": 11,
    "dec": 12,
}
DOW_ALPHAS: dict[str, Union[int, str]] = {
    "sun": 0,
    "mon": 1,
    "tue": 2,
    "wed": 3,
    "thu": 4,
    "fri": 5,
    "sat": 6,
}

MINUTE_FIELD = 0
HOUR_FIELD = 1
DAY_FIELD = 2
MONTH_FIELD = 3
DOW_FIELD = 4
SECOND_FIELD = 5
YEAR_FIELD = 6

UNIX_FIELDS = (MINUTE_FIELD, HOUR_FIELD, DAY_FIELD, MONTH_FIELD, DOW_FIELD)
SECOND_FIELDS = (MINUTE_FIELD, HOUR_FIELD, DAY_FIELD, MONTH_FIELD, DOW_FIELD, SECOND_FIELD)
YEAR_FIELDS = (
    MINUTE_FIELD,
    HOUR_FIELD,
    DAY_FIELD,
    MONTH_FIELD,
    DOW_FIELD,
    SECOND_FIELD,
    YEAR_FIELD,
)

DAYS = (31, 28, 31, 30, 31, 30, 31, 31, 30, 31, 30, 31)

CRON_FIELDS = {
    "unix": UNIX_FIELDS,
    "second": SECOND_FIELDS,
    "year": YEAR_FIELDS,
    len(UNIX_FIELDS): UNIX_FIELDS,
    len(SECOND_FIELDS): SECOND_FIELDS,
    len(YEAR_FIELDS): YEAR_FIELDS,
}
UNIX_CRON_LEN = len(UNIX_FIELDS)
SECOND_CRON_LEN = len(SECOND_FIELDS)
YEAR_CRON_LEN = len(YEAR_FIELDS)
# retrocompat
VALID_LEN_EXPRESSION = {a for a in CRON_FIELDS if isinstance(a, int)}
