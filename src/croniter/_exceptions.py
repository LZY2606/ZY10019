"""Exception hierarchy for croniter.

These classes historically lived in ``croniter.croniter`` and remain
importable from there.  They are defined here so the internal components
(``_fields``, ``_matching``, ``_tzstep``) can raise them without importing
the main module.  ``__module__`` is pinned back to ``croniter.croniter`` so
that class reprs and pickle/serialization paths are byte-identical to the
pre-split layout.
"""


class CroniterError(ValueError):
    """General top-level Croniter base exception"""


class CroniterBadTypeRangeError(TypeError):
    """."""


class CroniterBadCronError(CroniterError):
    """Syntax, unknown value, or range error within a cron expression"""


class CroniterUnsupportedSyntaxError(CroniterBadCronError):
    """Valid cron syntax, but likely to produce inaccurate results"""

    # Extending CroniterBadCronError, which may be contridatory, but this allows
    # catching both errors with a single exception.  From a user perspective
    # these will likely be handled the same way.


class CroniterBadDateError(CroniterError):
    """Unable to find next/prev timestamp match"""


class CroniterNotAlphaError(CroniterBadCronError):
    """Cron syntax contains an invalid day or month abbreviation"""


for _exc in (
    CroniterError,
    CroniterBadTypeRangeError,
    CroniterBadCronError,
    CroniterUnsupportedSyntaxError,
    CroniterBadDateError,
    CroniterNotAlphaError,
):
    _exc.__module__ = "croniter.croniter"

del _exc
