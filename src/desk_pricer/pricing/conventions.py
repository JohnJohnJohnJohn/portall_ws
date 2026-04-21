"""Day counts, calendars and convention helpers."""

from datetime import date

import QuantLib as ql


def ql_date_from_iso(d: date) -> ql.Date:
    return ql.Date(d.day, d.month, d.year)


def default_calendar() -> ql.Calendar:
    return ql.UnitedStates(ql.UnitedStates.NYSE)


def default_day_count() -> ql.DayCounter:
    return ql.Actual365Fixed()


def expiry_from_t(valuation_date: ql.Date, t: float) -> ql.Date:
    # Round-half-up to avoid Python's banker's rounding bias
    import math
    days = max(1, int(math.floor(t * 365 + 0.5)))
    return valuation_date + int(days)
