"""Exception hierarchy for croniter.

Kept in a dedicated module so the internal components (``_expand``,
``_match``, ``_tzstep``) can raise the public exception types without
importing the main ``croniter.croniter`` module (which would be a circular
import).  ``croniter.croniter`` re-exports these classes and restores their
``__module__`` so that reprs and pickling are unchanged.
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
