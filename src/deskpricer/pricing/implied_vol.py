"""Implied volatility solver via QuantLib."""

import math
from datetime import date

import QuantLib as ql

from deskpricer.errors import InvalidInputError, UnsupportedCombinationError
from deskpricer.pricing.conventions import (
    DEFAULT_STEPS,
    MIN_T_YEARS,
)
from deskpricer.pricing.conventions import (
    default_calendar,
    default_day_count,
    expiry_from_t,
    ql_date_from_iso,
)
from deskpricer.pricing.engine import ENGINE_MAP
from deskpricer.schemas import EngineLiteral, ImpliedVolOutput


def compute_implied_vol(
    s: float,
    k: float,
    t: float,
    r: float,
    q: float,
    target_price: float,
    option_type: str,
    style: str,
    engine: EngineLiteral,
    valuation_date: date,
    steps: int = DEFAULT_STEPS,
    accuracy: float = 1e-4,
    max_iterations: int = 1000,
) -> ImpliedVolOutput:
    """Solve for implied volatility given an observed market price."""
    if not math.isfinite(t):
        raise InvalidInputError("time to expiry must be a finite number", field="t")
    effective_t = max(t, MIN_T_YEARS)
    ql_date = ql_date_from_iso(valuation_date)
    expiry_date = expiry_from_t(ql_date, effective_t)
    calendar = default_calendar()
    day_count = default_day_count()

    spot_handle = ql.QuoteHandle(ql.SimpleQuote(s))
    div_ts = ql.YieldTermStructureHandle(ql.FlatForward(ql_date, q, day_count))
    rf_ts = ql.YieldTermStructureHandle(ql.FlatForward(ql_date, r, day_count))

    if option_type not in ("call", "put"):
        raise InvalidInputError(
            f"option_type must be 'call' or 'put'; got {option_type}",
            field="type",
        )

    payoff = ql.PlainVanillaPayoff(ql.Option.Call if option_type == "call" else ql.Option.Put, k)

    # Seed vol surface for the solver
    seed_vol = 0.20
    vol_ts = ql.BlackVolTermStructureHandle(
        ql.BlackConstantVol(ql_date, calendar, seed_vol, day_count)
    )
    process = ql.BlackScholesMertonProcess(spot_handle, div_ts, rf_ts, vol_ts)

    if style == "european":
        if engine != "analytic":
            raise UnsupportedCombinationError(
                f"European implied vol only supports analytic engine; got {engine}",
                field="engine",
            )
        exercise = ql.EuropeanExercise(expiry_date)
        engine_cls = ql.AnalyticEuropeanEngine
        ql_engine = None

    elif style == "american":
        if engine == "analytic":
            raise UnsupportedCombinationError(
                "American style does not support analytic engine",
                field="engine",
            )
        ql_engine = ENGINE_MAP.get(engine)
        if ql_engine is None:
            raise UnsupportedCombinationError(
                f"Unknown engine {engine} for american style",
                field="engine",
            )
        exercise = ql.AmericanExercise(ql_date, expiry_date)
        engine_cls = None

    else:
        raise UnsupportedCombinationError(f"Unknown style: {style}", field="style")

    option = ql.VanillaOption(payoff, exercise)
    if engine_cls is not None:
        option.setPricingEngine(engine_cls(process))
    else:
        option.setPricingEngine(ql.BinomialVanillaEngine(process, ql_engine, steps))

    try:
        implied_vol = option.impliedVolatility(
            target_price, process, accuracy, max_iterations, 1e-6, 5.0
        )
    except RuntimeError as exc:
        msg = str(exc)
        if "root not bracketed" in msg.lower():
            raise InvalidInputError(
                "Target price implies volatility outside solver bounds [1e-6, 5.0] or is outside arbitrage bounds",
                field="price",
            ) from exc
        # Let unexpected QuantLib failures propagate as 500s
        raise

    # Re-price at solved vol to provide a sanity-check NPV
    try:
        vol_ts_iv = ql.BlackVolTermStructureHandle(
            ql.BlackConstantVol(ql_date, calendar, implied_vol, day_count)
        )
        process_iv = ql.BlackScholesMertonProcess(spot_handle, div_ts, rf_ts, vol_ts_iv)

        option_iv = ql.VanillaOption(payoff, exercise)
        if style == "european":
            option_iv.setPricingEngine(ql.AnalyticEuropeanEngine(process_iv))
        else:
            option_iv.setPricingEngine(ql.BinomialVanillaEngine(process_iv, ql_engine, steps))

        npv_at_iv = float(option_iv.NPV())
    except RuntimeError as exc:
        raise InvalidInputError(
            "Pricing failed at solved implied volatility", field="price"
        ) from exc

    if not math.isfinite(implied_vol) or not math.isfinite(npv_at_iv):
        raise InvalidInputError("Solver returned non-finite implied volatility", field="price")

    return ImpliedVolOutput(implied_vol=float(implied_vol), npv_at_iv=npv_at_iv)
