"""American option pricing via BinomialVanillaEngine with bump-and-revalue Greeks."""

import logging
import math
from datetime import date

import QuantLib as ql

from deskpricer.errors import InvalidInputError
from deskpricer.pricing.conventions import (
    DEFAULT_BUMP_RATE_ABS,
    DEFAULT_BUMP_SPOT_REL,
    DEFAULT_BUMP_VOL_ABS,
    DEFAULT_CALENDAR,
    MIN_T_YEARS,
    CalendarLiteral,
    default_day_count,
    expiry_from_t,
    get_calendar,
    next_business_day,
    ql_date_from_iso,
)
from deskpricer.schemas import GreeksOutput


def _npv(
    s: float,
    k: float,
    r: float,
    q: float,
    v: float,
    option_type: str,
    valuation_date: ql.Date,
    expiry_date: ql.Date,
    steps: int,
    engine_type: str,
    calendar: ql.Calendar,
) -> float:
    """Return the NPV of an American option.

    ``valuation_date`` is used as the earliest exercise date
    (``ql.AmericanExercise(valuation_date, expiry_date)``), matching the
    standard listed-equity convention of immediate exercise.  Callers who
    need a T+1 earliest exercise date (e.g. options on futures) should pass
    ``valuation_date + 1`` as the start parameter.
    """
    if steps < 1:
        raise InvalidInputError("steps must be positive", field="steps")

    day_count = default_day_count()

    spot_handle = ql.QuoteHandle(ql.SimpleQuote(s))
    div_ts = ql.YieldTermStructureHandle(ql.FlatForward(valuation_date, q, day_count))
    rf_ts = ql.YieldTermStructureHandle(ql.FlatForward(valuation_date, r, day_count))
    vol_ts = ql.BlackVolTermStructureHandle(
        ql.BlackConstantVol(valuation_date, calendar, v, day_count)
    )

    process = ql.BlackScholesMertonProcess(spot_handle, div_ts, rf_ts, vol_ts)
    payoff = ql.PlainVanillaPayoff(ql.Option.Call if option_type == "call" else ql.Option.Put, k)
    exercise = ql.AmericanExercise(valuation_date, expiry_date)
    option = ql.VanillaOption(payoff, exercise)
    option.setPricingEngine(ql.BinomialVanillaEngine(process, engine_type, steps))

    try:
        return float(option.NPV())
    except RuntimeError as exc:
        logging.getLogger("deskpricer").warning(
            "American pricing failed", extra={"error": str(exc)}
        )
        raise InvalidInputError("Pricing failed for the given inputs") from exc


def price_american(
    s: float,
    k: float,
    t: float,
    r: float,
    q: float,
    v: float,
    option_type: str,
    valuation_date: date,
    steps: int,
    engine_type: str,
    bump_spot_rel: float = DEFAULT_BUMP_SPOT_REL,
    bump_vol_abs: float = DEFAULT_BUMP_VOL_ABS,
    bump_rate_abs: float = DEFAULT_BUMP_RATE_ABS,
    calendar_name: CalendarLiteral = DEFAULT_CALENDAR,
    theta_convention: str = "pnl",
) -> GreeksOutput:
    """Price an American option and return bump-and-revalue Greeks.

    Early exercise is permitted from the valuation date onward
    (``ql.AmericanExercise(valuation_date, expiry_date)``), matching the
    standard listed-equity convention of immediate exercise.  Callers who
    need a T+1 earliest exercise date (e.g. options on futures) should pass
    ``valuation_date + 1`` as the start parameter.
    """
    if s <= 0:
        raise InvalidInputError("spot price must be positive", field="s")
    if k <= 0:
        raise InvalidInputError("strike must be positive", field="k")
    if v <= 0:
        raise InvalidInputError("volatility must be positive", field="v")
    if bump_spot_rel <= 0:
        raise InvalidInputError("bump_spot_rel must be positive", field="bump_spot_rel")
    if bump_vol_abs <= 0:
        raise InvalidInputError("bump_vol_abs must be positive", field="bump_vol_abs")
    if bump_rate_abs <= 0:
        raise InvalidInputError("bump_rate_abs must be positive", field="bump_rate_abs")
    if bump_spot_rel >= 1.0:
        raise InvalidInputError("bump_spot_rel must be < 1.0", field="bump_spot_rel")

    ql_date = ql_date_from_iso(valuation_date)
    effective_t = max(t, MIN_T_YEARS)
    calendar = get_calendar(calendar_name)
    expiry_date = expiry_from_t(ql_date, effective_t, calendar)

    price = _npv(s, k, r, q, v, option_type, ql_date, expiry_date, steps, engine_type, calendar)

    # Delta & Gamma via central differences on spot
    h_s = bump_spot_rel * s
    if h_s <= 0.0 or not math.isfinite(h_s):
        raise InvalidInputError(
            "Spot bump underflowed to zero; use larger spot or bump_spot_rel",
            field="bump_spot_rel",
        )
    _common = (option_type, ql_date, expiry_date, steps, engine_type, calendar)
    price_up_s = _npv(s + h_s, k, r, q, v, *_common)
    price_down_s = _npv(s - h_s, k, r, q, v, *_common)
    delta = (price_up_s - price_down_s) / (2.0 * h_s)
    gamma = (price_up_s - 2.0 * price + price_down_s) / (h_s * h_s)

    # Vega via central difference on vol
    # Divide by 100 to report standard market convention (per 1%)
    # Cap h_v at v*0.5 to prevent negative vol on v - h_v; warn when capped.
    h_v = min(bump_vol_abs, v * 0.5)
    if h_v < bump_vol_abs:
        logging.getLogger("deskpricer").warning(
            "American vol bump auto-capped: bump_vol_abs=%.6f -> effective=%.6f (v=%.6f)",
            bump_vol_abs,
            h_v,
            v,
        )
    if h_v <= 0.0 or not math.isfinite(h_v):
        raise InvalidInputError(
            "Vol bump underflowed to zero; use larger vol or bump_vol_abs",
            field="bump_vol_abs",
        )
    price_up_v = _npv(s, k, r, q, v + h_v, *_common)
    price_down_v = _npv(s, k, r, q, v - h_v, *_common)
    vega = (price_up_v - price_down_v) / (2.0 * h_v) / 100.0

    # Rho via central difference on rate
    # Divide by 100 to report standard market convention (per 1%)
    h_r = bump_rate_abs
    price_up_r = _npv(s, k, r + h_r, q, v, *_common)
    price_down_r = _npv(s, k, r - h_r, q, v, *_common)
    rho = (price_up_r - price_down_r) / (2.0 * h_r) / 100.0

    # Theta: P&L impact of one business day passing (forward-looking, negative for a long option).
    # Revalue at the next business day and subtract today's price.
    # When the option has <= 1 business day left, fallback to intrinsic value.
    try:
        next_bd = next_business_day(ql_date, calendar)
    except RuntimeError as exc:
        raise InvalidInputError("Valuation date too close to maximum supported date") from exc
    if expiry_date <= next_bd:
        price_next_bd = max(s - k, 0.0) if option_type == "call" else max(k - s, 0.0)
        charm = 0.0
    else:
        _common_t1 = (option_type, next_bd, expiry_date, steps, engine_type, calendar)
        price_next_bd = _npv(s, k, r, q, v, *_common_t1)
        price_up_s_t1 = _npv(s + h_s, k, r, q, v, *_common_t1)
        price_down_s_t1 = _npv(s - h_s, k, r, q, v, *_common_t1)
        delta_t1 = (price_up_s_t1 - price_down_s_t1) / (2.0 * h_s)
        charm = delta_t1 - delta
    theta = price_next_bd - price

    if theta_convention == "decay":
        theta = -theta
        charm = -charm

    return GreeksOutput(
        price=price,
        delta=delta,
        gamma=gamma,
        vega=vega,
        theta=theta,
        rho=rho,
        charm=charm,
    )
