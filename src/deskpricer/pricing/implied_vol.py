"""Implied volatility solver via QuantLib."""

import logging
import math
from datetime import date

import QuantLib as ql

from deskpricer.errors import InvalidInputError, UnsupportedCombinationError
from deskpricer.pricing.constants import (
    IV_HIGH_VOL_WARNING_THRESHOLD,
    IV_LOW_VEGA_WARNING_THRESHOLD,
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
from deskpricer.pricing.constants import DEFAULT_STEPS, MIN_T_YEARS
from deskpricer.pricing.conventions import (
    DEFAULT_CALENDAR,
    CalendarLiteral,
    default_day_count,
    expiry_from_t,
    get_calendar,
    ql_date_from_iso,
)
from deskpricer.pricing.engine import ENGINE_MAP, resolve_effective_steps
from deskpricer.schemas import EngineLiteral, ImpliedVolOutput

_INV_SQRT_2PI = 1.0 / math.sqrt(2.0 * math.pi)

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
    b: float = 0.0,
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
    div_ts = ql.YieldTermStructureHandle(ql.FlatForward(ql_date, q + b, day_count))
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
        # For the IV solver, use at least 500 binomial steps regardless of the
        # adaptive default.  The IV solver needs sufficient lattice resolution
        # to converge cleanly (binomial price is non-smooth in vol at low step
        # counts — saw-tooth — which causes Brent to land on local solutions
        # that don't satisfy the verify tolerance).  When the caller explicitly
        # requests fewer than 500 steps, honour it but expect noisier IV.
        effective_steps = max(steps, 500) if steps != DEFAULT_STEPS else max(
            resolve_effective_steps("american", effective_t, IV_SEED_VOL, steps), 500
        )
        option.setPricingEngine(ql.BinomialVanillaEngine(process, ql_engine, effective_steps))

    # Pre-check no-arbitrage bounds before invoking the solver.  Europeans:
    # discounted asset/strike bounds.  Americans: the holder can exercise
    # immediately, so the lower bound is the undiscounted intrinsic and the
    # upper bound the undiscounted asset/strike.  Discount factors use the
    # same whole-day-grid T the solver prices at — using the raw input t
    # instead lets deep-ITM targets pass here and fail later in the solver
    # with the generic bounds message (half a day of discounting can exceed
    # such an option's entire time value).
    eff_t_grid = day_count.yearFraction(ql_date, expiry_date)
    df_r = math.exp(-r * eff_t_grid)
    df_qb = math.exp(-(q + b) * eff_t_grid)
    is_american = style == "american"
    if option_type == "call":
        lower_bound = max(0.0, s - k) if is_american else max(0.0, s * df_qb - k * df_r)
        upper_bound = s if is_american else s * df_qb
    else:
        lower_bound = max(0.0, k - s) if is_american else max(0.0, k * df_r - s * df_qb)
        upper_bound = k if is_american else k * df_r

    if target_price < lower_bound:
        raise InvalidInputError(
            f"Target price {target_price:.6f} is below the no-arbitrage lower bound "
            f"{lower_bound:.6f} (S={s}, K={k}, r={r}, q={q}, b={b}, T={effective_t})",
            field="price",
        )
    if target_price > upper_bound:
        raise InvalidInputError(
            f"Target price {target_price:.6f} is above the no-arbitrage upper bound "
            f"{upper_bound:.6f} (S={s}, K={k}, r={r}, q={q}, b={b}, T={effective_t})",
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
                    f"Target price implies volatility outside solver bounds "
                    f"[{IV_SOLVER_VOL_LO}, {IV_SOLVER_VOL_HI}]",
                    field="price",
                ) from exc2
        else:
            # Let unexpected QuantLib failures propagate as 500s
            raise

    # Re-price at solved vol to provide a sanity-check NPV and verify the
    # solver actually converged.  Always computed (the response includes
    # npv_at_iv) but the tolerance check below is gated on verify_reprice.
    # For European analytic the reprice is cheap; for American binomial it
    # doubles the tree-build cost, but QuantLib's binomial IV has known
    # saw-tooth convergence that makes the verify essential for catching
    # non-converged solutions.
    try:
        vol_ts_iv = ql.BlackVolTermStructureHandle(
            ql.BlackConstantVol(ql_date, calendar, implied_vol, day_count)
        )
        process_iv = ql.BlackScholesMertonProcess(spot_handle, div_ts, rf_ts, vol_ts_iv)

        option_iv = ql.VanillaOption(payoff, exercise)
        if engine_cls is not None:
            option_iv.setPricingEngine(engine_cls(process_iv))
        else:
            option_iv.setPricingEngine(
                ql.BinomialVanillaEngine(process_iv, ql_engine, effective_steps)
            )

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

    # Conditioning flag: the inversion error scales as 1/vega, so a tiny vega
    # at the solved vol means small price noise maps to huge IV errors
    # (measured: 1 cent of price error > 1 vol-point once vega/1% < 0.01).
    # Exact for Europeans, approximate (but adequate for a flag) for trees.
    d1_iv = (math.log(s / k) + (r - (q + b) + 0.5 * implied_vol * implied_vol) * eff_t_grid) / (
        implied_vol * math.sqrt(eff_t_grid)
    )
    vega_est = (
        s
        * math.exp(-(q + b) * eff_t_grid)
        * _INV_SQRT_2PI
        * math.exp(-0.5 * d1_iv * d1_iv)
        * math.sqrt(eff_t_grid)
        / 100.0
    )
    if vega_est < IV_LOW_VEGA_WARNING_THRESHOLD:
        logging.getLogger("deskpricer").warning(
            "Solved IV is ill-conditioned: estimated vega %.5f per 1 vol-point is below "
            "%.2f, so ~0.01 of price noise maps to >1 vol-point of IV error. "
            "Target price=%.4f, s=%.2f, k=%.2f, t=%.6f, iv=%.4f. "
            "Deep-ITM/OTM IVs carry no vol information; exclude from calibration.",
            vega_est,
            IV_LOW_VEGA_WARNING_THRESHOLD,
            target_price,
            s,
            k,
            t,
            implied_vol,
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
