"""Day counts, calendars, convention helpers, and numerical constants.

Numerical conventions
---------------------
- Vega is per **1 vol point** (1% absolute).
- Rho is per **1 rate point** (1% absolute).
- Theta is per **calendar day**.
- Greeks bump semantics:
  - Relative spot bump (e.g., 1% of spot).
  - Absolute vol bump (e.g., 0.001 = 0.1 vol points).
  - Absolute rate bump (e.g., 0.001 = 0.1% rate points).
- Zero-DTE handling: ``t < 1/365`` is floored to 1 day.
"""

import math
from datetime import date

import QuantLib as ql

from deskpricer.errors import InvalidInputError

MIN_T_YEARS = 1.0 / 365.0
DEFAULT_STEPS = 400
DEFAULT_BUMP_SPOT_REL = 0.01
DEFAULT_BUMP_VOL_ABS = 0.001
DEFAULT_BUMP_RATE_ABS = 0.001
DAY_COUNT = "ACT/365F"


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
