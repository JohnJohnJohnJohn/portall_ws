"""Vanna and volga calculator via uniform finite differences."""

from datetime import date

from desk_pricer.errors import InvalidInputError
from desk_pricer.pricing.engine import price_vanilla


def compute_cross_greeks(
    base_price: float,
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
    steps: int,
    bump_spot_rel: float,
    bump_vol_abs: float,
    bump_rate_abs: float,
) -> tuple[float, float]:
    """Compute vanna and volga for a single market state.

    Vanna  = ∂²V/∂S∂σ   (per $1 per 1% vol point)
    Volga  = ∂²V/∂σ²    (per (1%)²)

    Both are calculated via central finite differences using the
    existing bump_spot_rel and bump_vol_abs conventions.
    """
    if s <= 0:
        raise InvalidInputError("spot price must be positive", field="s")
    if v <= bump_vol_abs:
        raise InvalidInputError(
            "volatility must be greater than bump_vol_abs for cross-greeks computation",
            field="v",
        )
    if bump_spot_rel <= 0:
        raise InvalidInputError("bump_spot_rel must be positive", field="bump_spot_rel")
    if bump_vol_abs <= 0:
        raise InvalidInputError("bump_vol_abs must be positive", field="bump_vol_abs")

    ds = s * bump_spot_rel
    dv_points = bump_vol_abs * 100.0

    # --- Volga: V(S,σ+Δσ) - 2V(S,σ) + V(S,σ-Δσ) over (Δσ)² ---
    # 2 extra pricing calls
    result_v_up = price_vanilla(
        s=s, k=k, t=t, r=r, q=q, v=v + bump_vol_abs,
        option_type=option_type, style=style, engine=engine,
        valuation_date=valuation_date, steps=steps,
        bump_spot_rel=bump_spot_rel, bump_vol_abs=bump_vol_abs,
        bump_rate_abs=bump_rate_abs,
    )
    result_v_down = price_vanilla(
        s=s, k=k, t=t, r=r, q=q, v=v - bump_vol_abs,
        option_type=option_type, style=style, engine=engine,
        valuation_date=valuation_date, steps=steps,
        bump_spot_rel=bump_spot_rel, bump_vol_abs=bump_vol_abs,
        bump_rate_abs=bump_rate_abs,
    )
    volga = (result_v_up.price - 2.0 * base_price + result_v_down.price) / (dv_points ** 2)

    # --- Vanna: 4-point cross difference ---
    # 4 extra pricing calls
    result_pp = price_vanilla(
        s=s + ds, k=k, t=t, r=r, q=q, v=v + bump_vol_abs,
        option_type=option_type, style=style, engine=engine,
        valuation_date=valuation_date, steps=steps,
        bump_spot_rel=bump_spot_rel, bump_vol_abs=bump_vol_abs,
        bump_rate_abs=bump_rate_abs,
    )
    result_pm = price_vanilla(
        s=s + ds, k=k, t=t, r=r, q=q, v=v - bump_vol_abs,
        option_type=option_type, style=style, engine=engine,
        valuation_date=valuation_date, steps=steps,
        bump_spot_rel=bump_spot_rel, bump_vol_abs=bump_vol_abs,
        bump_rate_abs=bump_rate_abs,
    )
    result_mp = price_vanilla(
        s=s - ds, k=k, t=t, r=r, q=q, v=v + bump_vol_abs,
        option_type=option_type, style=style, engine=engine,
        valuation_date=valuation_date, steps=steps,
        bump_spot_rel=bump_spot_rel, bump_vol_abs=bump_vol_abs,
        bump_rate_abs=bump_rate_abs,
    )
    result_mm = price_vanilla(
        s=s - ds, k=k, t=t, r=r, q=q, v=v - bump_vol_abs,
        option_type=option_type, style=style, engine=engine,
        valuation_date=valuation_date, steps=steps,
        bump_spot_rel=bump_spot_rel, bump_vol_abs=bump_vol_abs,
        bump_rate_abs=bump_rate_abs,
    )
    vanna = (
        result_pp.price - result_pm.price - result_mp.price + result_mm.price
    ) / (4.0 * ds * dv_points)

    return vanna, volga
