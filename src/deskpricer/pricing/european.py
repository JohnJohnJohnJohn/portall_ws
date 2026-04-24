"""European option pricing via AnalyticEuropeanEngine."""

from datetime import date

import QuantLib as ql

from deskpricer.errors import InvalidInputError
from deskpricer.pricing.conventions import (
    DEFAULT_CALENDAR,
    CalendarLiteral,
    default_day_count,
    expiry_from_t,
    get_calendar,
    ql_date_from_iso,
)
from deskpricer.pricing.constants import MIN_T_YEARS
from deskpricer.schemas import GreeksOutput


def _reprice_with_expiry(
    spot_handle: ql.QuoteHandle,
    payoff: ql.PlainVanillaPayoff,
    valuation_date: ql.Date,
    expiry_date: ql.Date,
    calendar: ql.Calendar,
    r: float,
    q: float,
    v: float,
    day_count: ql.DayCounter,
) -> ql.VanillaOption:
    """Build a European option repriced with a shortened expiry (for theta/charm)."""
    div_ts = ql.YieldTermStructureHandle(ql.FlatForward(valuation_date, q, day_count))
    rf_ts = ql.YieldTermStructureHandle(ql.FlatForward(valuation_date, r, day_count))
    vol_ts = ql.BlackVolTermStructureHandle(
        ql.BlackConstantVol(valuation_date, calendar, v, day_count)
    )
    process = ql.BlackScholesMertonProcess(spot_handle, div_ts, rf_ts, vol_ts)
    exercise = ql.EuropeanExercise(expiry_date)
    option = ql.VanillaOption(payoff, exercise)
    option.setPricingEngine(ql.AnalyticEuropeanEngine(process))
    return option


def price_european(
    s: float,
    k: float,
    t: float,
    r: float,
    q: float,
    v: float,
    option_type: str,
    valuation_date: date,
    calendar_name: CalendarLiteral = DEFAULT_CALENDAR,
) -> GreeksOutput:
    """Price a European option and return Greeks.

    Delta, gamma, vega and rho come from QuantLib's analytic closed-form
    engine.  Theta and charm are computed by shortening time-to-expiry by
    ``1/365`` years (1 calendar day) and revaluing, rather than using
    ``option.theta()``.  This guarantees a per-calendar-day P&L figure that
    is directly usable in attribution and is consistent with the American
    theta convention, rather than a continuous-time annualised sensitivity.
    """
    if s <= 0:
        raise InvalidInputError("spot price must be positive", field="s")
    if k <= 0:
        raise InvalidInputError("strike must be positive", field="k")
    if v <= 0:
        raise InvalidInputError("volatility must be positive", field="v")

    ql_date = ql_date_from_iso(valuation_date)
    calendar = get_calendar(calendar_name)
    expiry_date = expiry_from_t(ql_date, t, calendar)
    day_count = default_day_count()

    spot_handle = ql.QuoteHandle(ql.SimpleQuote(s))
    div_ts = ql.YieldTermStructureHandle(ql.FlatForward(ql_date, q, day_count))
    rf_ts = ql.YieldTermStructureHandle(ql.FlatForward(ql_date, r, day_count))
    vol_ts = ql.BlackVolTermStructureHandle(ql.BlackConstantVol(ql_date, calendar, v, day_count))

    process = ql.BlackScholesMertonProcess(spot_handle, div_ts, rf_ts, vol_ts)
    payoff = ql.PlainVanillaPayoff(ql.Option.Call if option_type == "call" else ql.Option.Put, k)
    exercise = ql.EuropeanExercise(expiry_date)
    option = ql.VanillaOption(payoff, exercise)
    option.setPricingEngine(ql.AnalyticEuropeanEngine(process))

    # vega() and rho() are mathematical derivatives (per 1.00 unit);
    # we divide by 100 to report standard market convention (per 1%)
    try:
        price = float(option.NPV())
        delta = float(option.delta())
        gamma = float(option.gamma())
        vega = float(option.vega()) / 100.0
        rho = float(option.rho()) / 100.0
    except RuntimeError as exc:
        raise InvalidInputError("Pricing failed for the given inputs") from exc

    # Theta & Charm: 1-calendar-day revalue (t - 1/365).
    # theta = price(t - 1/365) - price(t)  (negative for a typical long option).
    # charm = delta(t - 1/365) - delta(today).
    # When the option has <= 1 calendar day left, theta falls back to intrinsic - price
    # and charm falls back to 0.0.
    theta = 0.0
    charm = 0.0
    if t <= MIN_T_YEARS:
        intrinsic = max(s - k, 0.0) if option_type == "call" else max(k - s, 0.0)
        theta = intrinsic - price
    else:
        expiry_t1 = expiry_date - 1
        try:
            option_t1 = _reprice_with_expiry(
                spot_handle, payoff, ql_date, expiry_t1, calendar, r, q, v, day_count
            )
            theta = float(option_t1.NPV()) - price
            charm = float(option_t1.delta()) - delta
        except RuntimeError as exc:
            raise InvalidInputError("Theta/charm calculation failed for the given inputs") from exc

    return GreeksOutput(
        price=price,
        delta=delta,
        gamma=gamma,
        vega=vega,
        theta=theta,
        rho=rho,
        charm=charm,
    )
