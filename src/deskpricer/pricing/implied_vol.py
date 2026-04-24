"""Implied volatility solver via QuantLib."""

import logging
import math
from datetime import date

import QuantLib as ql

from deskpricer.errors import InvalidInputError, UnsupportedCombinationError
from deskpricer.pricing.constants import (
    IV_HIGH_VOL_WARNING_THRESHOLD,
    IV_REPRICE_RELATIVE_TOLERANCE,
    IV_SEED_VOL,
    IV_SOLVER_DEFAULT_ACCURACY,
    IV_SOLVER_MAX_ITERATIONS,
    IV_SOLVER_VOL_HI,
    IV_SOLVER_VOL_HI_RETRY,
    IV_SOLVER_VOL_LO,
    IV_SOLVER_VOL_LO_RETRY,
    IV_TOLERANCE_MULTIPLIER_ANALYTIC,
    IV_TOLERANCE_MULTIPLIER_TREE,
)
from deskpricer.pricing.conventions import (
    DEFAULT_CALENDAR,
    DEFAULT_STEPS,
    MIN_T_YEARS,
    CalendarLiteral,
    default_day_count,
    expiry_from_t,
    get_calendar,
    ql_date_from_iso,
)
from deskpricer.pricing.engine import ENGINE_MAP
from deskpricer.schemas import EngineLiteral, ImpliedVolOutput

assert IV_SOLVER_VOL_LO < IV_SOLVER_VOL_HI, "IV solver primary bounds must form a bracket"
assert IV_SOLVER_VOL_LO_RETRY < IV_SOLVER_VOL_HI_RETRY, "IV solver retry bounds must form a bracket"


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
    accuracy: float = IV_SOLVER_DEFAULT_ACCURACY,
    max_iterations: int = IV_SOLVER_MAX_ITERATIONS,
    calendar_name: CalendarLiteral = DEFAULT_CALENDAR,
    verify_reprice: bool = True,
) -> ImpliedVolOutput:
    """Solve for implied volatility given an observed market price."""
    if not math.isfinite(t):
        raise InvalidInputError("time to expiry must be a finite number", field="t")
    effective_t = max(t, MIN_T_YEARS)
    ql_date = ql_date_from_iso(valuation_date)
    calendar = get_calendar(calendar_name)
    expiry_date = expiry_from_t(ql_date, effective_t, calendar)
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
    vol_ts = ql.BlackVolTermStructureHandle(
        ql.BlackConstantVol(ql_date, calendar, IV_SEED_VOL, day_count)
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

    # Pre-check no-arbitrage bounds before invoking solver
    df_r = math.exp(-r * effective_t)
    df_q = math.exp(-q * effective_t)
    if option_type == "call":
        lower_bound = max(0.0, s * df_q - k * df_r)
        upper_bound = s * df_q
    else:
        lower_bound = max(0.0, k * df_r - s * df_q)
        upper_bound = k * df_r

    if target_price < lower_bound:
        raise InvalidInputError(
            f"Target price {target_price:.6f} is below the no-arbitrage lower bound "
            f"{lower_bound:.6f} (S={s}, K={k}, r={r}, q={q}, T={effective_t})",
            field="price",
        )
    if target_price > upper_bound:
        raise InvalidInputError(
            f"Target price {target_price:.6f} is above the no-arbitrage upper bound "
            f"{upper_bound:.6f} (S={s}, K={k}, r={r}, q={q}, T={effective_t})",
            field="price",
        )

    try:
        implied_vol = option.impliedVolatility(
            target_price, process, accuracy, max_iterations, IV_SOLVER_VOL_LO, IV_SOLVER_VOL_HI
        )
    except RuntimeError as exc:
        msg = str(exc)
        if "root not bracketed" in msg.lower():
            logging.getLogger("deskpricer").warning(
                "IV solver root not bracketed with bounds [%.0e, %.1f]; "
                "retrying with [%.0e, %.1f] for target_price=%.6f s=%.2f k=%.2f t=%.6f",
                IV_SOLVER_VOL_LO,
                IV_SOLVER_VOL_HI,
                IV_SOLVER_VOL_LO_RETRY,
                IV_SOLVER_VOL_HI_RETRY,
                target_price,
                s,
                k,
                t,
            )
            try:
                implied_vol = option.impliedVolatility(
                    target_price,
                    process,
                    accuracy,
                    max_iterations,
                    IV_SOLVER_VOL_LO_RETRY,
                    IV_SOLVER_VOL_HI_RETRY,
                )
            except RuntimeError as exc2:
                raise InvalidInputError(
                    f"Target price implies volatility outside solver bounds [{IV_SOLVER_VOL_LO}, {IV_SOLVER_VOL_HI}] "
                    "or is outside arbitrage bounds",
                    field="price",
                ) from exc2
        else:
            # Let unexpected QuantLib failures propagate as 500s
            raise

    # Re-price at solved vol to provide a sanity-check NPV
    try:
        vol_ts_iv = ql.BlackVolTermStructureHandle(
            ql.BlackConstantVol(ql_date, calendar, implied_vol, day_count)
        )
        process_iv = ql.BlackScholesMertonProcess(spot_handle, div_ts, rf_ts, vol_ts_iv)

        option_iv = ql.VanillaOption(payoff, exercise)
        if engine_cls is not None:
            option_iv.setPricingEngine(engine_cls(process_iv))
        else:
            option_iv.setPricingEngine(ql.BinomialVanillaEngine(process_iv, ql_engine, steps))

        npv_at_iv = float(option_iv.NPV())
    except RuntimeError as exc:
        raise InvalidInputError(
            "Pricing failed at solved implied volatility", field="price"
        ) from exc

    if not math.isfinite(implied_vol) or not math.isfinite(npv_at_iv):
        raise InvalidInputError("Solver returned non-finite implied volatility", field="price")

    if implied_vol > IV_HIGH_VOL_WARNING_THRESHOLD:
        logging.getLogger("deskpricer").warning(
            "Solved implied volatility %.2f%% exceeds %.0f%%. "
            "Target price=%.4f, s=%.2f, k=%.2f, t=%.6f. "
            "This usually indicates a data-quality issue.",
            implied_vol * 100,
            IV_HIGH_VOL_WARNING_THRESHOLD * 100,
            target_price,
            s,
            k,
            t,
        )

    is_tree_engine = engine_cls is None
    # Analytic engine: back-check tolerance should be tight.  A multiplier of 10
    # keeps round-trip residuals within bounds while still rejecting genuine
    # solver failures.  Tree engines have genuine discretisation error and need
    # a relaxed tolerance.
    tolerance_multiplier = (
        IV_TOLERANCE_MULTIPLIER_TREE if is_tree_engine else IV_TOLERANCE_MULTIPLIER_ANALYTIC
    )
    # Hybrid tolerance: base accuracy multiplier with a relative scale
    # (0.1% of target price) to prevent over-tight rejection on
    # high-nominal underlyings.
    effective_tolerance = max(
        tolerance_multiplier * accuracy,
        IV_REPRICE_RELATIVE_TOLERANCE * target_price,
    )
    if verify_reprice and abs(npv_at_iv - target_price) > effective_tolerance:
        raise InvalidInputError(
            f"Solved NPV {npv_at_iv:.6f} deviates from target {target_price:.6f} "
            f"by more than tolerance {effective_tolerance:.6f}",
            field="price",
        )

    return ImpliedVolOutput(implied_vol=float(implied_vol), npv_at_iv=npv_at_iv)
