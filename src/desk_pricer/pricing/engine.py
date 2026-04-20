"""Pricing dispatch function."""

from datetime import date

from desk_pricer.errors import InvalidInputError, UnsupportedCombinationError
from desk_pricer.pricing.american import price_american
from desk_pricer.pricing.european import price_european
from desk_pricer.schemas import GreeksOutput


ENGINE_MAP = {
    "binomial_crr": "crr",
    "binomial_jr": "jr",
    "fd": "fd",
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
    bump_vol_abs: float = 0.0001,
    bump_rate_abs: float = 0.0001,
) -> GreeksOutput:
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
        if engine == "fd":
            raise UnsupportedCombinationError(
                "FD engine not yet implemented in v1.0",
                field="engine",
            )
        ql_engine = ENGINE_MAP.get(engine)
        if ql_engine is None:
            raise UnsupportedCombinationError(
                f"Unknown engine {engine} for american style",
                field="engine",
            )
        return price_american(
            s, k, effective_t, r, q, v, option_type, valuation_date, steps, ql_engine,
            bump_spot_rel=bump_spot_rel,
            bump_vol_abs=bump_vol_abs,
            bump_rate_abs=bump_rate_abs,
        )

    raise UnsupportedCombinationError(f"Unknown style: {style}", field="style")
