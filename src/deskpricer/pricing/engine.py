"""Pricing dispatch function."""

import logging
import math
from datetime import date

from deskpricer.errors import UnsupportedCombinationError
from deskpricer.pricing.american import price_american
from deskpricer.pricing.bsm_fast import price_european_bsm
from deskpricer.pricing.conventions import (
    DEFAULT_BUMP_RATE_ABS,
    DEFAULT_BUMP_SPOT_REL,
    DEFAULT_BUMP_VOL_ABS,
    DEFAULT_CALENDAR,
    DEFAULT_STEPS,
    MIN_T_YEARS,
    CalendarLiteral,
    expiry_from_t,
    get_calendar,
    ql_date_from_iso,
)
from deskpricer.pricing.constants import (
    ADAPTIVE_STEPS_MAX,
    ADAPTIVE_STEPS_MIN,
    ADAPTIVE_STEPS_TARGET,
    INSUFFICIENT_STEPS_WARNING_THRESHOLD,
)
from deskpricer.pricing.equivalence import american_is_european_equivalent
from deskpricer.schemas import EngineLiteral, GreeksOutput

ENGINE_MAP = {
    "binomial_crr": "crr",
    "binomial_jr": "jr",
}


def _adaptive_steps(t: float) -> int:
    """Pick a binomial step count based on time-to-expiry ``t`` (years).

    Long-dated options converge with fewer steps; short-dated options need more
    to resolve the payoff kink near expiry.  The formula targets roughly
    ``ADAPTIVE_STEPS_TARGET`` steps per year of maturity, clamped to
    ``[ADAPTIVE_STEPS_MIN, ADAPTIVE_STEPS_MAX]``.  This is only used when the
    caller did not explicitly override ``steps`` (i.e. left it at the schema
    default ``DEFAULT_STEPS``).
    """
    # Floor t at 0.05 years (~18 days) so the formula doesn't explode for 0-DTE.
    # Shorter options are already at the accuracy ceiling of the binomial model.
    raw = int(ADAPTIVE_STEPS_TARGET / max(t, 0.05))
    return max(ADAPTIVE_STEPS_MIN, min(ADAPTIVE_STEPS_MAX, raw))


# Process-local dedup set for the insufficient-steps warning, so a 500-leg
# portfolio with identical params doesn't spam 500 identical warnings.  Bounded
# to prevent unbounded growth in long-running workers; overflow resets the set.
_WARNED_INSUFFICIENT_STEPS_LIMIT = 256
_warned_insufficient_steps: set[tuple[float, float, int]] = set()


def _maybe_warn_insufficient_steps(t: float, v: float, steps: int) -> None:
    """Log a one-time warning when the step count is likely too low for t/v.

    Fires when steps-per-year is below ``INSUFFICIENT_STEPS_WARNING_THRESHOLD``
    OR when the absolute step count is below ``ADAPTIVE_STEPS_MIN`` (catches
    short-dated options where the per-year formula is misleading).
    """
    key = (round(t, 4), round(v, 4), steps)
    if key in _warned_insufficient_steps:
        return
    if len(_warned_insufficient_steps) >= _WARNED_INSUFFICIENT_STEPS_LIMIT:
        _warned_insufficient_steps.clear()
    recommended = max(
        ADAPTIVE_STEPS_MIN, min(ADAPTIVE_STEPS_MAX, _adaptive_steps(t))
    )
    steps_per_year = steps / max(t, 0.05)
    if steps_per_year < INSUFFICIENT_STEPS_WARNING_THRESHOLD or steps < ADAPTIVE_STEPS_MIN:
        _warned_insufficient_steps.add(key)
        logging.getLogger("deskpricer").warning(
            "steps=%d may be insufficient for t=%.4f, v=%.2f (recommended >= %d); "
            "gamma/theta accuracy may suffer",
            steps, t, v, recommended,
        )


def resolve_effective_steps(
    style: str, t: float, v: float, requested_steps: int
) -> int:
    """Return the step count to actually use for American options.

    When the caller did not override ``steps`` (left it at ``DEFAULT_STEPS``),
    pick an adaptive value based on time-to-expiry.  When the caller supplied
    an explicit value, respect it but warn if it's likely insufficient.
    European options ignore steps entirely (closed-form), so this is only
    meaningful for Americans.
    """
    if style != "american":
        return requested_steps
    if requested_steps == DEFAULT_STEPS:
        return _adaptive_steps(t)
    _maybe_warn_insufficient_steps(t, v, requested_steps)
    return requested_steps


def price_vanilla(
    s: float,
    k: float,
    t: float,
    r: float,
    q: float,
    v: float,
    option_type: str,
    style: str,
    engine: EngineLiteral,
    valuation_date: date,
    b: float = 0.0,
    steps: int = DEFAULT_STEPS,
    bump_spot_rel: float = DEFAULT_BUMP_SPOT_REL,
    bump_vol_abs: float = DEFAULT_BUMP_VOL_ABS,
    bump_rate_abs: float = DEFAULT_BUMP_RATE_ABS,
    calendar_name: CalendarLiteral = DEFAULT_CALENDAR,
) -> GreeksOutput:
    if option_type not in ("call", "put"):
        raise UnsupportedCombinationError(
            f"option_type must be 'call' or 'put'; got {option_type}",
            field="type",
        )
    for name, val in (("s", s), ("k", k), ("t", t), ("r", r), ("q", q), ("b", b), ("v", v)):
        if not math.isfinite(val):
            raise UnsupportedCombinationError(f"{name} must be a finite number", field=name)
    if t < 0:
        raise UnsupportedCombinationError("time to expiry must be non-negative", field="t")
    # Floor t to 1 day to avoid QuantLib singularities at t → 0.
    # 0-DTE is an intentionally supported workflow; callers supply live market
    # data (spot and IV) that already reflects intraday decay, so the floor
    # does not introduce meaningful pricing error.
    effective_t = max(t, MIN_T_YEARS)
    if style == "european":
        if engine != "analytic":
            raise UnsupportedCombinationError(
                f"European style only supports analytic engine; got {engine}",
                field="engine",
            )
        return price_european_bsm(
            s,
            k,
            effective_t,
            r,
            q,
            v,
            option_type,
            valuation_date,
            b=b,
            calendar_name=calendar_name,
        )

    if style == "american":
        if engine == "analytic":
            raise UnsupportedCombinationError(
                "American style does not support analytic engine",
                field="engine",
            )
        if american_is_european_equivalent(option_type, r, q, b):
            return price_european_bsm(
                s,
                k,
                effective_t,
                r,
                q,
                v,
                option_type,
                valuation_date,
                b=b,
                calendar_name=calendar_name,
            )
        ql_engine = ENGINE_MAP.get(engine)
        if ql_engine is None:
            raise UnsupportedCombinationError(
                f"Unknown engine {engine} for american style",
                field="engine",
            )
        effective_steps = resolve_effective_steps("american", effective_t, v, steps)
        return price_american(
            s,
            k,
            effective_t,
            r,
            q,
            v,
            option_type,
            valuation_date,
            effective_steps,
            ql_engine,
            b=b,
            bump_spot_rel=bump_spot_rel,
            bump_vol_abs=bump_vol_abs,
            bump_rate_abs=bump_rate_abs,
            calendar_name=calendar_name,
        )

    raise UnsupportedCombinationError(f"Unknown style: {style}", field="style")


def price_vanilla_npv(
    s: float,
    k: float,
    t: float,
    r: float,
    q: float,
    v: float,
    option_type: str,
    style: str,
    engine: EngineLiteral,
    valuation_date: date,
    b: float = 0.0,
    steps: int = DEFAULT_STEPS,
    calendar_name: CalendarLiteral = DEFAULT_CALENDAR,
) -> float:
    """Price-only fast path: returns just the NPV (no Greeks).

    Used by cross_greeks, which needs only the price at each bumped scenario
    but was previously calling ``price_vanilla`` (computing all 7 Greeks and
    discarding 6 of them).  For Americans this avoids ~10x extra tree builds.
    """
    if option_type not in ("call", "put"):
        raise UnsupportedCombinationError(
            f"option_type must be 'call' or 'put'; got {option_type}",
            field="type",
        )
    for name, val in (("s", s), ("k", k), ("t", t), ("r", r), ("q", q), ("b", b), ("v", v)):
        if not math.isfinite(val):
            raise UnsupportedCombinationError(f"{name} must be a finite number", field=name)
    if t < 0:
        raise UnsupportedCombinationError("time to expiry must be non-negative", field="t")
    effective_t = max(t, MIN_T_YEARS)

    if style == "european":
        if engine != "analytic":
            raise UnsupportedCombinationError(
                f"European style only supports analytic engine; got {engine}",
                field="engine",
            )
        # European NPV is cheap (16µs via erf-based BSM); reuse the full path
        # to guarantee bit-identical results with price_vanilla.
        return price_european_bsm(
            s, k, effective_t, r, q, v, option_type, valuation_date,
            b=b, calendar_name=calendar_name,
        ).price

    if style == "american":
        if engine == "analytic":
            raise UnsupportedCombinationError(
                "American style does not support analytic engine",
                field="engine",
            )
        # For the NPV-only path, American-equivalent reroute uses the same BSM
        # path as the full-Greeks version to guarantee identical pricing.
        if american_is_european_equivalent(option_type, r, q, b):
            return price_european_bsm(
                s, k, effective_t, r, q, v, option_type, valuation_date,
                b=b, calendar_name=calendar_name,
            ).price
        ql_engine = ENGINE_MAP.get(engine)
        if ql_engine is None:
            raise UnsupportedCombinationError(
                f"Unknown engine {engine} for american style",
                field="engine",
            )
        effective_steps = resolve_effective_steps("american", effective_t, v, steps)
        # Use a lean single-NPV call path; we don't need bump-and-revalue here.
        from deskpricer.pricing.american import _npv as american_npv

        ql_date = ql_date_from_iso(valuation_date)
        calendar = get_calendar(calendar_name)
        expiry_date = expiry_from_t(ql_date, effective_t, calendar)
        return american_npv(
            s, k, r, q, v, option_type, ql_date, expiry_date, effective_steps, ql_engine, calendar, b=b
        )

    raise UnsupportedCombinationError(f"Unknown style: {style}", field="style")
