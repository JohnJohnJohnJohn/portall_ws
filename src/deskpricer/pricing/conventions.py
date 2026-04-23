"""Day counts, calendars, convention helpers, and numerical constants.

Numerical conventions
---------------------
- Vega is per **1 vol point** (1% absolute).
- Rho is per **1 rate point** (1% absolute).
- Theta is per **trading day** (1 business day per the chosen calendar).
  Both European and American styles compute theta by revaluing the option
  at the next business day and subtracting today's price.  This is a
  forward-looking P&L figure: theta < 0 for a typical long option because
  the position decays as time passes.
  PnL attribution: theta_pnl = theta * count_business_days(t_minus_1, t, calendar).
- Greeks bump semantics:
  - Relative spot bump (e.g., 1% of spot).
  - Absolute vol bump (e.g., 0.001 = 0.1 vol points).
  - Absolute rate bump (e.g., 0.001 = 0.1% rate points).
- Zero-DTE handling: ``t < 1/365`` is floored to 1 calendar day.
  This prevents QuantLib singularities at t → 0.  0-DTE is an intentionally
  supported workflow; callers are expected to supply live market data (spot
  and IV) that already reflects intraday decay as expiry approaches, so the
  floored t is not a source of meaningful pricing error.
- Default calendar: Hong Kong (`ql.HongKong()`).
- Supported calendars: hong_kong, us_nyse, us_settlement, united_kingdom, null.
"""

import math
from datetime import date
from typing import Literal

import QuantLib as ql

from deskpricer.errors import InvalidInputError

MIN_T_YEARS = 1.0 / 365.0
DEFAULT_STEPS = 400
DEFAULT_BUMP_SPOT_REL = 0.01
DEFAULT_BUMP_VOL_ABS = 0.001
DEFAULT_BUMP_RATE_ABS = 0.001
DAY_COUNT = "ACT/365F"

CalendarLiteral = Literal["hong_kong", "us_nyse", "us_settlement", "united_kingdom", "null"]
DEFAULT_CALENDAR: CalendarLiteral = "hong_kong"


def ql_date_from_iso(d: date) -> ql.Date:
    if d.year < 1901 or d.year > 2199:
        raise InvalidInputError(
            f"Date {d.isoformat()} is outside supported range (1901-2199)",
            field="valuation_date",
        )
    return ql.Date(d.day, d.month, d.year)


_CALENDAR_MAP: dict[str, ql.Calendar] = {
    "hong_kong": ql.HongKong(),
    "us_nyse": ql.UnitedStates(ql.UnitedStates.NYSE),
    "us_settlement": ql.UnitedStates(ql.UnitedStates.Settlement),
    "united_kingdom": ql.UnitedKingdom(),
    "null": ql.NullCalendar(),
}


def get_calendar(name: CalendarLiteral | None = None) -> ql.Calendar:
    """Return a QuantLib Calendar by name. Defaults to Hong Kong."""
    key = name or DEFAULT_CALENDAR
    if key not in _CALENDAR_MAP:
        raise InvalidInputError(f"Unknown calendar '{key}'", field="calendar")
    return _CALENDAR_MAP[key]


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


def next_business_day(date: ql.Date, calendar: ql.Calendar) -> ql.Date:
    """Return the next business day strictly after ``date`` according to ``calendar``."""
    d = date + 1
    while not calendar.isBusinessDay(d):
        d += 1
    return d


def count_business_days(start: ql.Date, end: ql.Date, calendar: ql.Calendar) -> int:
    """Count the number of business days in ``[start, end)`` using ``calendar``.

    Returns 1 minimum so zero-day moves still produce a finite theta_pnl.
    """
    count = 0
    d = start
    while d < end:
        if calendar.isBusinessDay(d):
            count += 1
        d += 1
    return max(count, 1)
