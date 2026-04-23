"""Pricing dispatch function."""

import math
from datetime import date

from deskpricer.errors import UnsupportedCombinationError
from deskpricer.pricing.american import price_american
from deskpricer.pricing.conventions import (
    DEFAULT_BUMP_RATE_ABS,
    DEFAULT_BUMP_SPOT_REL,
    DEFAULT_BUMP_VOL_ABS,
    DEFAULT_CALENDAR,
    DEFAULT_STEPS,
    MIN_T_YEARS,
    CalendarLiteral,
)
from deskpricer.pricing.european import price_european
from deskpricer.schemas import EngineLiteral, GreeksOutput

ENGINE_MAP = {
    "binomial_crr": "crr",
    "binomial_jr": "jr",
}


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
    for field_name, field_val in (
        ("s", s),
        ("k", k),
        ("t", t),
        ("r", r),
        ("q", q),
        ("v", v),
    ):
        if not math.isfinite(field_val):
            raise UnsupportedCombinationError(
                f"{field_name} must be a finite number", field=field_name
            )
    if t < 0:
        raise UnsupportedCombinationError("time to expiry must be non-negative", field="t")
    # Floor t to 1 day to avoid QuantLib zero-day collapse
    effective_t = max(t, MIN_T_YEARS)
    if style == "european":
        if engine != "analytic":
            raise UnsupportedCombinationError(
                f"European style only supports analytic engine; got {engine}",
                field="engine",
            )
        return price_european(s, k, effective_t, r, q, v, option_type, valuation_date, calendar_name=calendar_name)

    if style == "american":
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
        return price_american(
            s,
            k,
            effective_t,
            r,
            q,
            v,
            option_type,
            valuation_date,
            steps,
            ql_engine,
            bump_spot_rel=bump_spot_rel,
            bump_vol_abs=bump_vol_abs,
            bump_rate_abs=bump_rate_abs,
            calendar_name=calendar_name,
        )

    raise UnsupportedCombinationError(f"Unknown style: {style}", field="style")
