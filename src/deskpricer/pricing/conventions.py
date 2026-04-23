"""Day counts, calendars, convention helpers, and numerical constants.

Numerical conventions
---------------------
- Vega is per **1 vol point** (1% absolute).
- Rho is per **1 rate point** (1% absolute).
- Theta is per **trading day** (1 business day per the chosen calendar).
  Both European and American styles compute theta by revaluing the option
  at the next business day and subtracting today's price.  This is a
  forward-looking P&L figure: theta < 0 for a typical long option because
  the position decays as time passes.  Sign is opposite of Bloomberg
  DM<GO>, which reports theta as positive decay.
  Worked example: a long call with theta = -0.05 loses approximately $0.05
  in value for each business day that passes, all else equal.
  PnL attribution: theta_pnl = theta * trading_days, where trading_days is the
  elapsed business-day hold period (not a DTE-proxy).
- Charm inherits the same forward-difference, forward-looking convention as
  theta: it is the change in delta per one business day passing.
- Greeks bump semantics:
  - Relative spot bump (e.g., 1% of spot).
  - Absolute vol bump (e.g., 0.001 = 0.1 vol points).
  - Absolute rate bump (e.g., 0.001 = 0.1% rate points).
- Zero-DTE handling: ``t < 1/365`` is floored to 1 day.
  This prevents QuantLib singularities at t → 0.  0-DTE is an intentionally
  supported workflow; callers are expected to supply live market data (spot
  and IV) that already reflects intraday decay as expiry approaches, so the
  floored t is not a source of meaningful pricing error.
- Expiry conversion: ``t`` (years, ACT/365) is the sole expiry input.
  The pricer intentionally does not accept an explicit expiry date.
  Callers are expected to derive ``t`` from a real, pre-validated
  business-day expiry date (e.g., ``t = (expiry_date - today).days / 365``).
  The ``ql.Following`` business-day roll is a safety guard only; it is not
  expected to trigger in normal usage because callers should ensure the
  implied expiry date is already a business day.  If the roll does trigger,
  the effective ``t`` seen by QuantLib will be slightly longer than the
  input ``t``, which is documented and accepted behaviour.
- Default calendar: Hong Kong (`ql.HongKong()`).
- Supported calendars: hong_kong, us_nyse, us_settlement, united_kingdom, null.
"""

import logging
from datetime import date
from typing import Literal

import QuantLib as ql

from deskpricer.errors import InvalidInputError

MIN_T_YEARS = 1.0 / 365.0
_MAX_EXPIRY_T_DISCREPANCY = 0.20
DEFAULT_STEPS = 500
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


def expiry_from_t(valuation_date: ql.Date, t: float, calendar: ql.Calendar) -> ql.Date:
    """Convert a time-to-expiry ``t`` (ACT/365 years) into a QuantLib Date.

    ``t`` is the sole expiry interface; the pricer does **not** accept an
    explicit expiry date.  Callers must derive ``t`` from a real, pre-validated
    business-day expiry (e.g. ``(expiry_date - today).days / 365``).  The
    conversion uses ``round(t * 365)`` calendar days with a floor of 1, then
    rolls the landed date to the next business day using ``ql.Following``.  The
    roll is a safety guard only; it is not expected to trigger in normal
    usage because callers should ensure the implied expiry is already a
    business day.  If it does trigger, the effective ``t`` seen by QuantLib
    will be slightly longer than the input ``t``, which is documented and
    accepted behaviour.

    A warning is logged if the discrepancy between input ``t`` and the
    effective ACT/365 year fraction exceeds 20 %.
    """

    if t < 0:
        raise InvalidInputError("time to expiry must be non-negative", field="t")
    # Convert years to calendar days (ACT/365) with a hard floor of 1.
    n_cal_days = max(1, round(t * 365))
    try:
        expiry = valuation_date + ql.Period(n_cal_days, ql.Days)
    except RuntimeError as exc:
        raise InvalidInputError(
            "Expiry date exceeds QuantLib maximum supported date (2199-12-31)",
            field="t",
        ) from exc
    # Roll to next business day if the landed date is a holiday/weekend.
    # Following is used (not ModifiedFollowing or Preceding) because option
    # expiries must never land earlier than the contractual date; rolling
    # backward over a holiday would shorten the option's life.
    expiry = calendar.adjust(expiry, ql.Following)
    if expiry.year() > 2199:
        raise InvalidInputError(
            f"Expiry date ({expiry}) exceeds QuantLib maximum supported date (2199-12-31)",
            field="t",
        )
    # Compute and log the actual year fraction discrepancy caused by rounding
    # and business-day adjustment.
    day_count = default_day_count()
    effective_t = day_count.yearFraction(valuation_date, expiry)
    if t > 0:
        discrepancy = abs(effective_t - t) / t
        if discrepancy > _MAX_EXPIRY_T_DISCREPANCY:
            logging.getLogger("deskpricer").warning(
                "expiry_from_t discrepancy %.1f%%: input t=%.6f, effective t=%.6f, "
                "n_cal_days=%d, rolled_expiry=%s",
                discrepancy * 100,
                t,
                effective_t,
                n_cal_days,
                expiry,
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

    Returns **at least 1** so that a same-day repricing still reflects one
    full business day of theta decay.  This means ``theta_pnl`` is never
    zero even when ``start == end``; callers who want zero theta on a
    non-trading day must handle that logic themselves.
    """
    count = 0
    d = start
    while d < end:
        if calendar.isBusinessDay(d):
            count += 1
        d += 1
    return max(count, 1)
