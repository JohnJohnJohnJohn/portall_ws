"""European option pricing via AnalyticEuropeanEngine."""

from datetime import date

import QuantLib as ql

from deskpricer.errors import InvalidInputError
from deskpricer.pricing.conventions import (
    default_calendar,
    default_day_count,
    expiry_from_t,
    ql_date_from_iso,
)
from deskpricer.schemas import GreeksOutput


def price_european(
    s: float,
    k: float,
    t: float,
    r: float,
    q: float,
    v: float,
    option_type: str,
    valuation_date: date,
) -> GreeksOutput:
    if s <= 0:
        raise InvalidInputError("spot price must be positive", field="s")
    if k <= 0:
        raise InvalidInputError("strike must be positive", field="k")
    if v <= 0:
        raise InvalidInputError("volatility must be positive", field="v")

    ql_date = ql_date_from_iso(valuation_date)
    expiry_date = expiry_from_t(ql_date, t)
    calendar = default_calendar()
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

    # QuantLib Greeks conventions:
    # theta() is per year; we convert to per calendar day
    # vega() and rho() are mathematical derivatives (per 1.00 unit);
    # we divide by 100 to report standard market convention (per 1%)
    try:
        price = float(option.NPV())
        delta = float(option.delta())
        gamma = float(option.gamma())
        vega = float(option.vega()) / 100.0
        theta = float(option.theta()) / 365.0
        rho = float(option.rho()) / 100.0
    except RuntimeError as exc:
        raise InvalidInputError("Pricing failed for the given inputs") from exc

    # Charm: ∂delta/∂t per calendar day (forward difference, 1 day)
    # When the option has <= 1 day left, QuantLib returns delta=0 for the expired
    # option, which would give charm = -delta (wrong). Fallback to 0.
    try:
        one_day_forward = ql_date + 1
    except RuntimeError:
        charm = 0.0
    else:
        if expiry_date <= one_day_forward:
            charm = 0.0
        else:
            try:
                ql.Settings.instance().evaluationDate = one_day_forward
                div_ts_t1 = ql.YieldTermStructureHandle(
                    ql.FlatForward(one_day_forward, q, day_count)
                )
                rf_ts_t1 = ql.YieldTermStructureHandle(
                    ql.FlatForward(one_day_forward, r, day_count)
                )
                vol_ts_t1 = ql.BlackVolTermStructureHandle(
                    ql.BlackConstantVol(one_day_forward, calendar, v, day_count)
                )
                process_t1 = ql.BlackScholesMertonProcess(
                    spot_handle, div_ts_t1, rf_ts_t1, vol_ts_t1
                )
                option_t1 = ql.VanillaOption(payoff, exercise)
                option_t1.setPricingEngine(ql.AnalyticEuropeanEngine(process_t1))
                delta_t1 = float(option_t1.delta())
                charm = delta_t1 - delta
            except RuntimeError as exc:
                raise InvalidInputError("Charm calculation failed for the given inputs") from exc
            finally:
                ql.Settings.instance().evaluationDate = ql_date

    return GreeksOutput(
        price=price,
        delta=delta,
        gamma=gamma,
        vega=vega,
        theta=theta,
        rho=rho,
        charm=charm,
    )
