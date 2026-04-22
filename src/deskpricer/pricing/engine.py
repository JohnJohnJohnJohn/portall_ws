"""Pricing dispatch function."""

import math
from datetime import date

from deskpricer.errors import UnsupportedCombinationError
from deskpricer.pricing.american import price_american
from deskpricer.pricing.european import price_european
from deskpricer.schemas import GreeksOutput

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
    engine: str,
    valuation_date: date,
    steps: int = 400,
    bump_spot_rel: float = 0.01,
    bump_vol_abs: float = 0.001,
    bump_rate_abs: float = 0.001,
) -> GreeksOutput:
    if option_type not in ("call", "put"):
        raise UnsupportedCombinationError(
            f"option_type must be 'call' or 'put'; got {option_type}",
            field="type",
        )
    for field_name, field_val in (
        ("s", s),
        ("k", k),
        ("r", r),
        ("q", q),
        ("v", v),
    ):
        if not math.isfinite(field_val):
            raise UnsupportedCombinationError(
                f"{field_name} must be a finite number", field=field_name
            )
    if not math.isfinite(t):
        raise UnsupportedCombinationError("time to expiry must be a finite number", field="t")
    if t < 0:
        raise UnsupportedCombinationError("time to expiry must be non-negative", field="t")
    # Floor t to 1 day to avoid QuantLib zero-day collapse
    effective_t = max(t, 1.0 / 365.0)
    if style == "european":
        if engine != "analytic":
            raise UnsupportedCombinationError(
                f"European style only supports analytic engine; got {engine}",
                field="engine",
            )
        return price_european(s, k, effective_t, r, q, v, option_type, valuation_date)

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
        )

    raise UnsupportedCombinationError(f"Unknown style: {style}", field="style")
