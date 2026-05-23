"""Pure-Python Black-Scholes-Merton pricing for European options."""

import math
from datetime import date

from scipy.stats import norm

from deskpricer.errors import InvalidInputError
from deskpricer.pricing.constants import MIN_T_YEARS
from deskpricer.pricing.conventions import (
    DEFAULT_CALENDAR,
    CalendarLiteral,
    default_day_count,
    expiry_from_t,
    get_calendar,
    ql_date_from_iso,
)
from deskpricer.schemas import GreeksOutput


def _effective_t(
    valuation_date: date,
    t: float,
    calendar_name: CalendarLiteral,
) -> tuple[float, float | None]:
    """Return ACT/365 year fraction to expiry and optional T after one calendar day."""
    ql_date = ql_date_from_iso(valuation_date)
    calendar = get_calendar(calendar_name)
    expiry_date = expiry_from_t(ql_date, t, calendar)
    day_count = default_day_count()
    effective = day_count.yearFraction(ql_date, expiry_date)
    if t <= MIN_T_YEARS:
        return effective, None
    expiry_t1 = expiry_date - 1
    effective_t1 = day_count.yearFraction(ql_date, expiry_t1)
    return effective, effective_t1


def _d1_d2(s: float, k: float, t: float, r: float, q_eff: float, v: float) -> tuple[float, float]:
    sqrt_t = math.sqrt(t)
    d1 = (math.log(s / k) + (r - q_eff + 0.5 * v * v) * t) / (v * sqrt_t)
    d2 = d1 - v * sqrt_t
    return d1, d2


def _npv(s: float, k: float, t: float, r: float, q_eff: float, v: float, option_type: str) -> float:
    d1, d2 = _d1_d2(s, k, t, r, q_eff, v)
    if option_type == "call":
        return s * math.exp(-q_eff * t) * norm.cdf(d1) - k * math.exp(-r * t) * norm.cdf(d2)
    return k * math.exp(-r * t) * norm.cdf(-d2) - s * math.exp(-q_eff * t) * norm.cdf(-d1)


def _delta(s: float, k: float, t: float, r: float, q_eff: float, v: float, option_type: str) -> float:
    d1, _ = _d1_d2(s, k, t, r, q_eff, v)
    scale = math.exp(-q_eff * t)
    if option_type == "call":
        return scale * norm.cdf(d1)
    return scale * (norm.cdf(d1) - 1.0)


def _gamma(s: float, k: float, t: float, r: float, q_eff: float, v: float) -> float:
    d1, _ = _d1_d2(s, k, t, r, q_eff, v)
    return math.exp(-q_eff * t) * norm.pdf(d1) / (s * v * math.sqrt(t))


def _vega(s: float, k: float, t: float, r: float, q_eff: float, v: float) -> float:
    d1, _ = _d1_d2(s, k, t, r, q_eff, v)
    return s * math.exp(-q_eff * t) * norm.pdf(d1) * math.sqrt(t) / 100.0


def _rho(s: float, k: float, t: float, r: float, q_eff: float, v: float, option_type: str) -> float:
    _, d2 = _d1_d2(s, k, t, r, q_eff, v)
    if option_type == "call":
        return k * t * math.exp(-r * t) * norm.cdf(d2) / 100.0
    return -k * t * math.exp(-r * t) * norm.cdf(-d2) / 100.0


def price_european_bsm(
    s: float,
    k: float,
    t: float,
    r: float,
    q: float,
    v: float,
    option_type: str,
    valuation_date: date,
    b: float = 0.0,
    calendar_name: CalendarLiteral = DEFAULT_CALENDAR,
) -> GreeksOutput:
    """Price a European option with closed-form BSM and calendar-day theta/charm."""
    if s <= 0:
        raise InvalidInputError("spot price must be positive", field="s")
    if k <= 0:
        raise InvalidInputError("strike must be positive", field="k")
    if v <= 0:
        raise InvalidInputError("volatility must be positive", field="v")

    q_eff = q + b
    effective_t, effective_t1 = _effective_t(valuation_date, t, calendar_name)

    price = _npv(s, k, effective_t, r, q_eff, v, option_type)
    delta = _delta(s, k, effective_t, r, q_eff, v, option_type)
    gamma = _gamma(s, k, effective_t, r, q_eff, v)
    vega = _vega(s, k, effective_t, r, q_eff, v)
    rho = _rho(s, k, effective_t, r, q_eff, v, option_type)

    if t <= MIN_T_YEARS:
        intrinsic = max(s - k, 0.0) if option_type == "call" else max(k - s, 0.0)
        theta = intrinsic - price
        charm = 0.0
    else:
        assert effective_t1 is not None
        price_t1 = _npv(s, k, effective_t1, r, q_eff, v, option_type)
        delta_t1 = _delta(s, k, effective_t1, r, q_eff, v, option_type)
        theta = price_t1 - price
        charm = delta_t1 - delta

    return GreeksOutput(
        price=price,
        delta=delta,
        gamma=gamma,
        vega=vega,
        theta=theta,
        rho=rho,
        charm=charm,
    )
