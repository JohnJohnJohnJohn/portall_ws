"""American option pricing via BinomialVanillaEngine with bump-and-revalue Greeks."""

from datetime import date

import QuantLib as ql

from desk_pricer.pricing.conventions import (
    default_calendar,
    default_day_count,
    expiry_from_t,
    ql_date_from_iso,
)
from desk_pricer.schemas import GreeksOutput


def _create_option(
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
) -> ql.VanillaOption:
    calendar = default_calendar()
    day_count = default_day_count()

    spot_handle = ql.QuoteHandle(ql.SimpleQuote(s))
    div_ts = ql.YieldTermStructureHandle(ql.FlatForward(valuation_date, q, day_count))
    rf_ts = ql.YieldTermStructureHandle(ql.FlatForward(valuation_date, r, day_count))
    vol_ts = ql.BlackVolTermStructureHandle(
        ql.BlackConstantVol(valuation_date, calendar, v, day_count)
    )

    process = ql.BlackScholesMertonProcess(spot_handle, div_ts, rf_ts, vol_ts)
    payoff = ql.PlainVanillaPayoff(
        ql.Option.Call if option_type == "call" else ql.Option.Put, k
    )
    exercise = ql.AmericanExercise(valuation_date, expiry_date)
    option = ql.VanillaOption(payoff, exercise)
    option.setPricingEngine(ql.BinomialVanillaEngine(process, engine_type, steps))
    return option


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
    option = _create_option(s, k, r, q, v, option_type, valuation_date, expiry_date, steps, engine_type)
    return float(option.NPV())


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
    bump_spot_rel: float = 0.01,
    bump_vol_abs: float = 0.0001,
    bump_rate_abs: float = 0.0001,
) -> GreeksOutput:
    ql_date = ql_date_from_iso(valuation_date)
    expiry_date = expiry_from_t(ql_date, t)

    price = _npv(s, k, r, q, v, option_type, ql_date, expiry_date, steps, engine_type)

    # Delta & Gamma via central differences on spot
    h_s = bump_spot_rel * s
    price_up_s = _npv(s + h_s, k, r, q, v, option_type, ql_date, expiry_date, steps, engine_type)
    price_down_s = _npv(s - h_s, k, r, q, v, option_type, ql_date, expiry_date, steps, engine_type)
    delta = (price_up_s - price_down_s) / (2.0 * h_s)
    gamma = (price_up_s - 2.0 * price + price_down_s) / (h_s * h_s)

    # Vega via central difference on vol
    # Divide by 100 to report standard market convention (per 1%)
    h_v = bump_vol_abs
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
    if expiry_date > ql_date + 1:
        price_tomorrow = _npv(
            s, k, r, q, v, option_type, ql_date + 1, expiry_date, steps, engine_type
        )
    else:
        if option_type == "call":
            price_tomorrow = max(s - k, 0.0)
        else:
            price_tomorrow = max(k - s, 0.0)
    theta = price - price_tomorrow

    # Charm: ∂delta/∂t per calendar day (forward difference)
    if expiry_date > ql_date + 1:
        price_up_s_t1 = _npv(s + h_s, k, r, q, v, option_type, ql_date + 1, expiry_date, steps, engine_type)
        price_down_s_t1 = _npv(s - h_s, k, r, q, v, option_type, ql_date + 1, expiry_date, steps, engine_type)
        delta_t1 = (price_up_s_t1 - price_down_s_t1) / (2.0 * h_s)
        charm = delta - delta_t1
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
