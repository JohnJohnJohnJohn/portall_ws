"""Shared BSM reference helpers and QuantLib eval-date sync for tests.

Centralises the closed-form Black-Scholes-Merton formulas reimplemented
across multiple test files, plus a context manager that aligns the global
QuantLib evaluation date for direct (non-pool) engine calls.
"""

import math
from contextlib import contextmanager
from datetime import date

import QuantLib as ql
from scipy.stats import norm

from deskpricer.pricing.conventions import ql_date_from_iso


# ── BSM closed-form reference ───────────────────────────────────────────────


def bs_d1(s: float, k: float, t: float, r: float, q: float, v: float) -> float:
    return (math.log(s / k) + (r - q + v * v / 2) * t) / (v * math.sqrt(t))


def bs_d2(s: float, k: float, t: float, r: float, q: float, v: float) -> float:
    return bs_d1(s, k, t, r, q, v) - v * math.sqrt(t)


def bs_call(s: float, k: float, t: float, r: float, q: float, v: float) -> float:
    d1 = bs_d1(s, k, t, r, q, v)
    d2 = bs_d2(s, k, t, r, q, v)
    return s * math.exp(-q * t) * norm.cdf(d1) - k * math.exp(-r * t) * norm.cdf(d2)


def bs_put(s: float, k: float, t: float, r: float, q: float, v: float) -> float:
    d1 = bs_d1(s, k, t, r, q, v)
    d2 = bs_d2(s, k, t, r, q, v)
    return k * math.exp(-r * t) * norm.cdf(-d2) - s * math.exp(-q * t) * norm.cdf(-d1)


def bs_price(s, k, t, r, q, v, option_type: str) -> float:
    return bs_call(s, k, t, r, q, v) if option_type == "call" else bs_put(s, k, t, r, q, v)


def bs_delta_call(s, k, t, r, q, v) -> float:
    return math.exp(-q * t) * norm.cdf(bs_d1(s, k, t, r, q, v))


def bs_vega_raw(s, k, t, r, q, v) -> float:
    """BSM vega per 1.00 (absolute) vol."""
    return s * math.exp(-q * t) * norm.pdf(bs_d1(s, k, t, r, q, v)) * math.sqrt(t)


def bs_vega_per_point(s, k, t, r, q, v) -> float:
    """BSM vega per 1 vol-point (1% absolute)."""
    return bs_vega_raw(s, k, t, r, q, v) / 100.0


def bs_rho_call_raw(s, k, t, r, q, v) -> float:
    """BSM call rho per 1.00 (absolute) rate."""
    return k * t * math.exp(-r * t) * norm.cdf(bs_d2(s, k, t, r, q, v))


def bs_rho_call_per_point(s, k, t, r, q, v) -> float:
    """BSM call rho per 1 rate-point (1% absolute)."""
    return bs_rho_call_raw(s, k, t, r, q, v) / 100.0


def bs_gamma(s, k, t, r, q, v) -> float:
    """BSM gamma (∂²V/∂S²)."""
    return math.exp(-q * t) * norm.pdf(bs_d1(s, k, t, r, q, v)) / (s * v * math.sqrt(t))


def bs_vanna_per_dollar_per_point(s, k, t, r, q, v) -> float:
    """BSM vanna per $1 spot per 1 vol-point. Equals ∂²V/∂S∂σ × 0.01."""
    d1 = bs_d1(s, k, t, r, q, v)
    d2 = bs_d2(s, k, t, r, q, v)
    return -math.exp(-q * t) * norm.pdf(d1) * d2 / v * 0.01


def bs_volga_per_point_sq(s, k, t, r, q, v) -> float:
    """BSM volga per (1 vol-point)². Equals ∂²V/∂σ² × 0.0001."""
    d1 = bs_d1(s, k, t, r, q, v)
    d2 = bs_d2(s, k, t, r, q, v)
    return s * math.exp(-q * t) * norm.pdf(d1) * math.sqrt(t) * d1 * d2 / v * 0.0001


# ── QuantLib eval-date sync ─────────────────────────────────────────────────


@contextmanager
def sync_eval_date(valuation_date: date):
    """Temporarily set the global QuantLib evaluation date.

    Direct (non-pool) calls to the QuantLib-backed pricing engines read
    ``ql.Settings.instance().evaluationDate``; tests that exercise those
    engines directly must align it to avoid stale-state pricing.
    """
    old_eval = ql.Settings.instance().evaluationDate
    ql.Settings.instance().evaluationDate = ql_date_from_iso(valuation_date)
    try:
        yield
    finally:
        ql.Settings.instance().evaluationDate = old_eval
