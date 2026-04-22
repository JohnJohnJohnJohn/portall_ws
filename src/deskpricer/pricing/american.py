"""American option pricing via BinomialVanillaEngine with bump-and-revalue Greeks."""

from datetime import date

import logging
import math

import QuantLib as ql

from deskpricer.errors import InvalidInputError
from deskpricer.pricing.conventions import (
    DEFAULT_BUMP_RATE_ABS,
    DEFAULT_BUMP_SPOT_REL,
    DEFAULT_BUMP_VOL_ABS,
)
from deskpricer.pricing.conventions import (
    default_calendar,
    default_day_count,
    expiry_from_t,
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
) -> float:
    if steps < 1:
        raise InvalidInputError("steps must be positive", field="steps")

    calendar = default_calendar()
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
) -> GreeksOutput:
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
    expiry_date = expiry_from_t(ql_date, t)

    price = _npv(s, k, r, q, v, option_type, ql_date, expiry_date, steps, engine_type)

    # Delta & Gamma via central differences on spot
    h_s = bump_spot_rel * s
    if h_s <= 0.0 or not math.isfinite(h_s):
        raise InvalidInputError(
            "Spot bump underflowed to zero; use larger spot or bump_spot_rel",
            field="bump_spot_rel",
        )
    price_up_s = _npv(s + h_s, k, r, q, v, option_type, ql_date, expiry_date, steps, engine_type)
    price_down_s = _npv(s - h_s, k, r, q, v, option_type, ql_date, expiry_date, steps, engine_type)
    delta = (price_up_s - price_down_s) / (2.0 * h_s)
    gamma = (price_up_s - 2.0 * price + price_down_s) / (h_s * h_s)

    # Vega via central difference on vol
    # Divide by 100 to report standard market convention (per 1%)
    h_v = min(bump_vol_abs, v * 0.5)
    if h_v <= 0.0 or not math.isfinite(h_v):
        raise InvalidInputError(
            "Vol bump underflowed to zero; use larger vol or bump_vol_abs",
            field="bump_vol_abs",
        )
    price_up_v = _npv(s, k, r, q, v + h_v, option_type, ql_date, expiry_date, steps, engine_type)
    price_down_v = _npv(s, k, r, q, v - h_v, option_type, ql_date, expiry_date, steps, engine_type)
    vega = (price_up_v - price_down_v) / (2.0 * h_v) / 100.0

    # Rho via central difference on rate
    # Divide by 100 to report standard market convention (per 1%)
    h_r = bump_rate_abs
    price_up_r = _npv(s, k, r + h_r, q, v, option_type, ql_date, expiry_date, steps, engine_type)
    price_down_r = _npv(s, k, r - h_r, q, v, option_type, ql_date, expiry_date, steps, engine_type)
    rho = (price_up_r - price_down_r) / (2.0 * h_r) / 100.0

    # Theta via one-day-forward revalue
    # When the option has <= 1 day left, forward revalue hits expiry;
    # fallback to intrinsic value for the overnight price
    try:
        tomorrow = ql_date + 1
    except RuntimeError as exc:
        raise InvalidInputError("Valuation date too close to maximum supported date") from exc
    if expiry_date > tomorrow:
        price_tomorrow = _npv(s, k, r, q, v, option_type, tomorrow, expiry_date, steps, engine_type)
    else:
        # At expiry the option is worth its intrinsic value
        price_tomorrow = max(s - k, 0.0) if option_type == "call" else max(k - s, 0.0)
    theta = price_tomorrow - price

    # Charm: ∂delta/∂t per calendar day (forward difference)
    if expiry_date > tomorrow:
        price_up_s_t1 = _npv(
            s + h_s, k, r, q, v, option_type, tomorrow, expiry_date, steps, engine_type
        )
        price_down_s_t1 = _npv(
            s - h_s, k, r, q, v, option_type, tomorrow, expiry_date, steps, engine_type
        )
        delta_t1 = (price_up_s_t1 - price_down_s_t1) / (2.0 * h_s)
        charm = delta_t1 - delta
    else:
        charm = 0.0

    return GreeksOutput(
        price=price,
        delta=delta,
        gamma=gamma,
        vega=vega,
        theta=theta,
        rho=rho,
        charm=charm,
    )
