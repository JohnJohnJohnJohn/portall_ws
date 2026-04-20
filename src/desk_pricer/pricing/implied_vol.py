"""Implied volatility solver via QuantLib."""

from datetime import date

import QuantLib as ql

from desk_pricer.errors import InvalidInputError
from desk_pricer.pricing.conventions import (
    default_calendar,
    default_day_count,
    expiry_from_t,
    ql_date_from_iso,
)
from desk_pricer.schemas import ImpliedVolOutput


def compute_implied_vol(
    s: float,
    k: float,
    t: float,
    r: float,
    q: float,
    target_price: float,
    option_type: str,
    style: str,
    engine: str,
    valuation_date: date,
    steps: int = 400,
    accuracy: float = 1e-4,
    max_iterations: int = 1000,
) -> ImpliedVolOutput:
    """Solve for implied volatility given an observed market price."""
    ql_date = ql_date_from_iso(valuation_date)
    expiry_date = expiry_from_t(ql_date, t)
    calendar = default_calendar()
    day_count = default_day_count()

    spot_handle = ql.QuoteHandle(ql.SimpleQuote(s))
    div_ts = ql.YieldTermStructureHandle(ql.FlatForward(ql_date, q, day_count))
    rf_ts = ql.YieldTermStructureHandle(ql.FlatForward(ql_date, r, day_count))

    payoff = ql.PlainVanillaPayoff(
        ql.Option.Call if option_type == "call" else ql.Option.Put, k
    )

    if style == "european":
        if engine != "analytic":
            raise InvalidInputError(
                f"European implied vol only supports analytic engine; got {engine}",
                field="engine",
            )
        exercise = ql.EuropeanExercise(expiry_date)
        option = ql.VanillaOption(payoff, exercise)

        # Seed vol surface for the solver
        seed_vol = 0.20
        vol_ts = ql.BlackVolTermStructureHandle(
            ql.BlackConstantVol(ql_date, calendar, seed_vol, day_count)
        )
        process = ql.BlackScholesMertonProcess(spot_handle, div_ts, rf_ts, vol_ts)
        option.setPricingEngine(ql.AnalyticEuropeanEngine(process))

    elif style == "american":
        if engine == "analytic":
            raise InvalidInputError(
                "American style does not support analytic engine",
                field="engine",
            )
        if engine == "fd":
            raise InvalidInputError(
                "FD engine not yet implemented in v1.0",
                field="engine",
            )
        ql_engine_map = {"binomial_crr": "crr", "binomial_jr": "jr"}
        ql_engine = ql_engine_map.get(engine)
        if ql_engine is None:
            raise InvalidInputError(
                f"Unknown engine {engine} for american style",
                field="engine",
            )
        exercise = ql.AmericanExercise(ql_date, expiry_date)
        option = ql.VanillaOption(payoff, exercise)

        seed_vol = 0.20
        vol_ts = ql.BlackVolTermStructureHandle(
            ql.BlackConstantVol(ql_date, calendar, seed_vol, day_count)
        )
        process = ql.BlackScholesMertonProcess(spot_handle, div_ts, rf_ts, vol_ts)
        option.setPricingEngine(ql.BinomialVanillaEngine(process, ql_engine, steps))

    else:
        raise InvalidInputError(f"Unknown style: {style}", field="style")

    try:
        implied_vol = option.impliedVolatility(
            target_price, process, accuracy, max_iterations, 0.001, 2.0
        )
    except RuntimeError as exc:
        msg = str(exc)
        if "root not bracketed" in msg.lower():
            raise InvalidInputError(
                "Target price is outside arbitrage bounds for the given inputs",
                field="price",
            ) from exc
        raise InvalidInputError(f"Implied vol convergence failed: {msg}") from exc

    # Re-price at solved vol to provide a sanity-check NPV
    vol_ts_iv = ql.BlackVolTermStructureHandle(
        ql.BlackConstantVol(ql_date, calendar, implied_vol, day_count)
    )
    process_iv = ql.BlackScholesMertonProcess(spot_handle, div_ts, rf_ts, vol_ts_iv)

    if style == "european":
        option_iv = ql.VanillaOption(payoff, exercise)
        option_iv.setPricingEngine(ql.AnalyticEuropeanEngine(process_iv))
    else:
        option_iv = ql.VanillaOption(payoff, exercise)
        option_iv.setPricingEngine(ql.BinomialVanillaEngine(process_iv, ql_engine, steps))

    npv_at_iv = float(option_iv.NPV())

    return ImpliedVolOutput(implied_vol=float(implied_vol), npv_at_iv=npv_at_iv)
