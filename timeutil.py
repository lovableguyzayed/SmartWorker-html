"""Indian Standard Time for every clock read in the app.

The production server (Render) runs on UTC, so bare datetime.now() /
date.today() are 5 hours 30 minutes behind the wall clock in India — attendance
check-ins were recorded 5:30 early, and anything marked between midnight and
05:30 IST landed on the previous day's date.

All stored timestamps are naive IST (matching the existing naive DB columns
and every strftime in the templates). No new dependencies: zoneinfo is stdlib.
"""
from datetime import date, datetime
from zoneinfo import ZoneInfo

IST = ZoneInfo('Asia/Kolkata')


def now_ist():
    """Current IST wall-clock time as a naive datetime."""
    return datetime.now(IST).replace(tzinfo=None)


def today_ist():
    """Current date in IST (not the server's UTC date)."""
    return datetime.now(IST).date()


class ISTDate(date):
    """Drop-in replacement for `date` in template contexts, so the existing
    `date.today()` calls inside templates resolve to the IST date."""
    @classmethod
    def today(cls):
        return today_ist()
