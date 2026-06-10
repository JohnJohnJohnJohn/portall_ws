"""Regression tests for American gamma sub-tick bump fix.

Prior to the fix, deep-OTM American calls priced with binomial_crr and the
default bump_spot_rel=0.01 would return gamma values near zero (e.g. 3.75e-07)
because the three spot reprices used in the second-difference formula landed
on the same locally-linear segment of the piecewise-linear CRR lattice.

The fix widens the gamma bump to span at least GAMMA_MIN_TICKS CRR lattice
ticks, ensuring the second difference captures real curvature.

Two real-world cases are tested:
  - 'bad': S=29.74, K=47  (was returning gamma ≈ 3.75e-07)
  - 'control': S=26.52, K=42  (was already working; must remain correct)

Gamma is validated against the Black-Scholes analytic value with a relative
tolerance of 50%.  A wide tolerance is intentional: binomial gamma is noisy
and the goal is simply to confirm the result is in a sensible order of
magnitude rather than matching BSM to high precision.
"""

import math
from datetime import date

import pytest

from deskpricer.pricing.american import price_american


# ── BSM analytic gamma reference ────────────────────────────────────────────

def _bsm_gamma(s: float, k: float, t: float, r: float, q: float, v: float) -> float:
    """Black-Scholes-Merton gamma (European = American for this call OTM case)."""
    phi = lambda x: math.exp(-0.5 * x * x) / math.sqrt(2 * math.pi)
    d1 = (math.log(s / k) + (r - q + 0.5 * v * v) * t) / (v * math.sqrt(t))
    return math.exp(-q * t) * phi(d1) / (s * v * math.sqrt(t))


# ── Test cases ───────────────────────────────────────────────────────────────

BAD_CASE = dict(
    s=29.74, k=47.0, t=0.556164383561644,
    r=0.03102028, q=0.01538865, v=0.4696272,
    option_type="call",
)

CONTROL_CASE = dict(
    s=26.52, k=42.0, t=0.556164383561644,
    r=0.03102028, q=0.04067940, v=0.4621498,
    option_type="call",
)

VALUATION_DATE = date(2026, 6, 10)
GAMMA_REL_TOL = 0.50  # 50% relative tolerance vs BSM — intentionally wide
GAMMA_NOISE_FLOOR = 1e-4  # gamma below this is considered numerical noise


@pytest.mark.parametrize("case,label", [
    (BAD_CASE, "bad_deep_otm_crr"),
    (CONTROL_CASE, "control_crr"),
])
def test_american_gamma_not_noise_crr(case, label):
    """CRR engine must return a gamma above the noise floor and within 50% of BSM."""
    result = price_american(
        **case,
        valuation_date=VALUATION_DATE,
        steps=500,
        engine_type="crr",
    )
    bsm_ref = _bsm_gamma(
        case["s"], case["k"], case["t"], case["r"], case["q"], case["v"]
    )
    assert result.gamma > GAMMA_NOISE_FLOOR, (
        f"[{label}] gamma={result.gamma:.2e} is below noise floor {GAMMA_NOISE_FLOOR}; "
        f"BSM reference={bsm_ref:.6f}"
    )
    rel_err = abs(result.gamma - bsm_ref) / bsm_ref
    assert rel_err < GAMMA_REL_TOL, (
        f"[{label}] gamma={result.gamma:.6f} deviates {rel_err*100:.1f}% from "
        f"BSM reference={bsm_ref:.6f} (tolerance={GAMMA_REL_TOL*100:.0f}%)"
    )


@pytest.mark.parametrize("case,label", [
    (BAD_CASE, "bad_deep_otm_jr"),
    (CONTROL_CASE, "control_jr"),
])
def test_american_gamma_not_noise_jr(case, label):
    """JR engine must also return a gamma above the noise floor and within 50% of BSM."""
    result = price_american(
        **case,
        valuation_date=VALUATION_DATE,
        steps=500,
        engine_type="jr",
    )
    bsm_ref = _bsm_gamma(
        case["s"], case["k"], case["t"], case["r"], case["q"], case["v"]
    )
    assert result.gamma > GAMMA_NOISE_FLOOR, (
        f"[{label}] gamma={result.gamma:.2e} is below noise floor {GAMMA_NOISE_FLOOR}; "
        f"BSM reference={bsm_ref:.6f}"
    )
    rel_err = abs(result.gamma - bsm_ref) / bsm_ref
    assert rel_err < GAMMA_REL_TOL, (
        f"[{label}] gamma={result.gamma:.6f} deviates {rel_err*100:.1f}% from "
        f"BSM reference={bsm_ref:.6f} (tolerance={GAMMA_REL_TOL*100:.0f}%)"
    )


def test_atm_gamma_unaffected_by_fix():
    """ATM option: gamma bump widening must not be triggered; result must remain close to BSM."""
    s, k = 30.0, 30.0
    t, r, q, v = 0.5, 0.03, 0.01, 0.30
    result = price_american(
        s=s, k=k, t=t, r=r, q=q, v=v,
        option_type="call",
        valuation_date=VALUATION_DATE,
        steps=500,
        engine_type="crr",
    )
    bsm_ref = _bsm_gamma(s, k, t, r, q, v)
    rel_err = abs(result.gamma - bsm_ref) / bsm_ref
    assert rel_err < 0.10, (
        f"ATM gamma={result.gamma:.6f} deviates {rel_err*100:.1f}% from BSM={bsm_ref:.6f}; "
        "ATM should not be affected by the sub-tick fix"
    )
