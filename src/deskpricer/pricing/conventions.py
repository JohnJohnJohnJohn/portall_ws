"""Day counts, calendars and convention helpers."""

import math
from datetime import date

import QuantLib as ql

from deskpricer.errors import InvalidInputError


def ql_date_from_iso(d: date) -> ql.Date:
    if d.year < 1901 or d.year > 2199:
        raise InvalidInputError(
            f"Date {d.isoformat()} is outside supported range (1901-2199)",
            field="valuation_date",
        )
    return ql.Date(d.day, d.month, d.year)


def default_calendar() -> ql.Calendar:
    return ql.UnitedStates(ql.UnitedStates.NYSE)


def default_day_count() -> ql.DayCounter:
    return ql.Actual365Fixed()


def expiry_from_t(valuation_date: ql.Date, t: float) -> ql.Date:
    if t < 0:
        raise InvalidInputError("time to expiry must be non-negative", field="t")
    # Round-half-up to avoid Python's banker's rounding bias
    days = max(1, math.floor(t * 365 + 0.5))
    try:
        expiry = valuation_date + days
    except RuntimeError as exc:
        raise InvalidInputError(
            "Expiry date exceeds QuantLib maximum supported date (2199-12-31)",
            field="t",
        ) from exc
    if expiry.year() > 2199:
        raise InvalidInputError(
            f"Expiry date ({expiry}) exceeds QuantLib maximum supported date (2199-12-31)",
            field="t",
        )
    return expiry
