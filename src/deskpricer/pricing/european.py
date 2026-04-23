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
    next_business_day,
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
    calendar_name: CalendarLiteral = DEFAULT_CALENDAR,
) -> GreeksOutput:
    if s <= 0:
        raise InvalidInputError("spot price must be positive", field="s")
    if k <= 0:
        raise InvalidInputError("strike must be positive", field="k")
    if v <= 0:
        raise InvalidInputError("volatility must be positive", field="v")

    ql_date = ql_date_from_iso(valuation_date)
    expiry_date = expiry_from_t(ql_date, t)
    calendar = get_calendar(calendar_name)
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

    # Theta: P&L impact of one business day passing (forward-looking, negative for a long option).
    # Revalue at the next business day and subtract today's price.
    # When the option has <= 1 business day left, fallback to intrinsic value.
    try:
        one_bd_forward = next_business_day(ql_date, calendar)
    except RuntimeError:
        theta = 0.0
    else:
        if expiry_date > one_bd_forward:
            try:
                div_ts_t1 = ql.YieldTermStructureHandle(
                    ql.FlatForward(one_bd_forward, q, day_count)
                )
                rf_ts_t1 = ql.YieldTermStructureHandle(
                    ql.FlatForward(one_bd_forward, r, day_count)
                )
                vol_ts_t1 = ql.BlackVolTermStructureHandle(
                    ql.BlackConstantVol(one_bd_forward, calendar, v, day_count)
                )
                process_t1 = ql.BlackScholesMertonProcess(
                    spot_handle, div_ts_t1, rf_ts_t1, vol_ts_t1
                )
                option_t1 = ql.VanillaOption(payoff, exercise)
                option_t1.setPricingEngine(ql.AnalyticEuropeanEngine(process_t1))
                price_t1 = float(option_t1.NPV())
                theta = price_t1 - price
            except RuntimeError as exc:
                raise InvalidInputError("Theta calculation failed for the given inputs") from exc
        else:
            intrinsic = max(s - k, 0.0) if option_type == "call" else max(k - s, 0.0)
            theta = intrinsic - price

    # Charm: ∂delta/∂t per trading day (forward difference, 1 business day)
    # When the option has <= 1 business day left, fall back to charm = 0.
    charm = 0.0
    try:
        one_bd_forward = next_business_day(ql_date, calendar)
    except RuntimeError:
        pass
    else:
        if expiry_date > one_bd_forward:
            try:
                div_ts_t1 = ql.YieldTermStructureHandle(
                    ql.FlatForward(one_bd_forward, q, day_count)
                )
                rf_ts_t1 = ql.YieldTermStructureHandle(
                    ql.FlatForward(one_bd_forward, r, day_count)
                )
                vol_ts_t1 = ql.BlackVolTermStructureHandle(
                    ql.BlackConstantVol(one_bd_forward, calendar, v, day_count)
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

    return GreeksOutput(
        price=price,
        delta=delta,
        gamma=gamma,
        vega=vega,
        theta=theta,
        rho=rho,
        charm=charm,
    )
