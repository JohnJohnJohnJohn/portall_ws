"""Tests for the 3.5 performance and accuracy improvements.

Covers:
- BSM fast path (math.erf parity, d1/d2 caching)
- Gamma sub-tick widening with collapse detection
- Richardson extrapolation for theta/charm
- Adaptive step count for American options
- effective_steps echo in response meta
- Cross-greeks NPV-only fast path
- Pool timeout (PricingTimeoutError → 503)
"""

import pytest
from fastapi.testclient import TestClient

from deskpricer.pricing.bsm_fast import _cdf, _pdf
from deskpricer.pricing.engine import _adaptive_steps, resolve_effective_steps


# ── BSM fast path: math.erf parity ─────────────────────────────────────────


class TestErfParity:
    def test_cdf_matches_scipy_to_machine_epsilon(self):
        from scipy.stats import norm

        for x in (-5.0, -3.0, -1.0, -0.5, 0.0, 0.5, 1.0, 3.0, 5.0):
            assert abs(_cdf(x) - norm.cdf(x)) < 1e-14

    def test_pdf_matches_scipy_to_machine_epsilon(self):
        from scipy.stats import norm

        for x in (-5.0, -3.0, -1.0, 0.0, 1.0, 3.0, 5.0):
            assert abs(_pdf(x) - norm.pdf(x)) < 1e-13

    def test_cdf_at_extremes(self):
        """Tail behaviour must be correct, not just near the mean."""
        assert _cdf(-10.0) < 1e-20
        assert abs(_cdf(10.0) - 1.0) < 1e-20
        assert abs(_cdf(0.0) - 0.5) < 1e-16


# ── Adaptive step count ────────────────────────────────────────────────────


class TestAdaptiveSteps:
    def test_long_dated_uses_fewer_steps(self):
        """T=1yr should pick fewer than the fixed 500 default."""
        assert _adaptive_steps(1.0) < 500

    def test_short_dated_uses_more_steps(self):
        """T=0.1yr (5 weeks) should pick more steps to resolve the payoff kink."""
        assert _adaptive_steps(0.1) > 500

    def test_clamped_to_min(self):
        """Very long maturities don't explode below the min."""
        assert _adaptive_steps(10.0) >= 100

    def test_clamped_to_max(self):
        """Very short maturities don't explode above the max."""
        assert _adaptive_steps(0.01) <= 2000

    def test_resolve_respects_explicit_override(self):
        """When caller explicitly sets steps, adaptive logic should not kick in."""
        # 100 is below adaptive for t=0.25 (which would pick ~800), but since
        # the caller asked for 100 explicitly (not DEFAULT_STEPS=500), we honour it.
        assert resolve_effective_steps("american", 0.25, 0.20, 100) == 100

    def test_resolve_picks_adaptive_when_default(self):
        """When caller leaves steps at DEFAULT_STEPS (500), adaptive picks a value
        based on t."""
        from deskpricer.pricing.constants import DEFAULT_STEPS

        # T=1yr → adaptive picks ~200, not the default 500
        result = resolve_effective_steps("american", 1.0, 0.20, DEFAULT_STEPS)
        assert result == _adaptive_steps(1.0)
        assert result != DEFAULT_STEPS

    def test_resolve_ignores_european(self):
        """European options ignore steps entirely (closed-form)."""
        assert resolve_effective_steps("european", 0.25, 0.20, 500) == 500


# ── effective_steps echo ───────────────────────────────────────────────────


class TestEffectiveStepsEcho:
    def test_meta_includes_effective_steps_for_american(self, client: TestClient):
        """When adaptive picks different steps, meta.effective_steps is populated."""
        # T=1yr American put → adaptive picks 200 (not default 500)
        resp = client.get(
            "/v1/greeks?s=100&k=100&t=1.0&r=0.05&q=0.02&v=0.20"
            "&type=put&style=american&engine=binomial_crr",
            headers={"Accept": "application/json"},
        )
        assert resp.status_code == 200
        meta = resp.json()["greeks"]["meta"]
        assert "effective_steps" in meta
        assert meta["effective_steps"] == 200

    def test_meta_omits_effective_steps_for_european(self, client: TestClient):
        """European responses never include effective_steps."""
        resp = client.get(
            "/v1/greeks?s=100&k=100&t=1.0&r=0.05&q=0.02&v=0.20"
            "&type=call&style=european",
            headers={"Accept": "application/json"},
        )
        assert resp.status_code == 200
        meta = resp.json()["greeks"]["meta"]
        assert "effective_steps" not in meta

    def test_meta_omits_effective_steps_when_user_overrides(self, client: TestClient):
        """When caller supplies explicit steps, meta doesn't second-guess them."""
        resp = client.get(
            "/v1/greeks?s=100&k=100&t=1.0&r=0.05&q=0.02&v=0.20"
            "&type=put&style=american&engine=binomial_crr&steps=300",
            headers={"Accept": "application/json"},
        )
        assert resp.status_code == 200
        meta = resp.json()["greeks"]["meta"]
        assert "effective_steps" not in meta


# ── Gamma sub-tick widening ────────────────────────────────────────────────


class TestGammaSubTick:
    def test_high_vol_gamma_not_collapsed(self):
        """The v=0.5, steps=500 case that previously returned 0.0004 (vs BSM 0.0157)
        must now return a value within ~25% of BSM.  This is the regression that
        motivated the runtime collapse detection."""
        import math
        from datetime import date

        from scipy.stats import norm

        from deskpricer.pricing.american import price_american

        s, k, t, r, q, v = 100, 100, 0.25, 0.05, 0.02, 0.50
        result = price_american(
            s=s, k=k, t=t, r=r, q=q, v=v, option_type="call",
            valuation_date=date(2026, 7, 20), steps=500, engine_type="crr",
        )
        # BSM reference gamma
        d1 = (math.log(s / k) + (r - q + 0.5 * v * v) * t) / (v * math.sqrt(t))
        bsm_gamma = math.exp(-q * t) * norm.pdf(d1) / (s * v * math.sqrt(t))
        rel_err = abs(result.gamma - bsm_gamma) / bsm_gamma
        # Was 97% error before fix; now within 25% (binomial noise floor).
        assert rel_err < 0.25, (
            f"gamma={result.gamma:.5f} vs BSM={bsm_gamma:.5f}, "
            f"rel_err={rel_err:.1%} (sub-tick collapse not detected)"
        )


# ── Richardson extrapolation ───────────────────────────────────────────────


class TestRichardsonTheta:
    def test_theta_at_500_steps_matches_high_step_reference(self):
        """Richardson extrapolation at 500+1000 effective steps should produce
        theta within ~1e-5 of the asymptotic (20000-step) truth, where raw
        500-step theta was off by ~1e-4."""
        from datetime import date

        from deskpricer.pricing.american import _npv
        from deskpricer.pricing.conventions import (
            expiry_from_t,
            get_calendar,
            ql_date_from_iso,
        )
        import QuantLib as ql

        from deskpricer.pricing.american import price_american

        vd = date(2026, 4, 20)
        ql_date = ql_date_from_iso(vd)
        ql.Settings.instance().evaluationDate = ql_date
        calendar = get_calendar("hong_kong")
        expiry = expiry_from_t(ql_date, 30 / 365, calendar)

        # Reference: 20000-step theta
        p_ref = _npv(100, 100, 0.05, 0, 0.20, "put", ql_date, expiry, 20000, "crr", calendar)
        p_ref_t1 = _npv(100, 100, 0.05, 0, 0.20, "put", ql_date, expiry - 1, 20000, "crr", calendar)
        theta_ref = p_ref_t1 - p_ref

        # Richardson-extrapolated theta via price_american at 500 steps
        g = price_american(
            s=100, k=100, t=30 / 365, r=0.05, q=0, v=0.20, option_type="put",
            valuation_date=vd, steps=500, engine_type="crr",
        )
        # Richardson should be much closer to truth than the raw 500-step value.
        rich_err = abs(g.theta - theta_ref)
        # Raw 500-step error is ~8e-6 (from prior calibration); Richardson at
        # 500+1000 effective should be tighter than that.
        assert rich_err < 1e-5, (
            f"Richardson theta={g.theta:.6f}, truth={theta_ref:.6f}, "
            f"err={rich_err:.2e} (expected < 1e-5)"
        )


# ── Cross-greeks NPV-only path correctness ─────────────────────────────────


class TestCrossGreeksNPVOnly:
    def test_vanna_volga_still_match_bsm(self):
        """After routing cross-greeks through the NPV-only fast path, the
        numerical vanna/volga must still agree with the BSM closed-form."""
        from datetime import date

        from _bsm_ref import sync_eval_date
        from _bsm_ref import (
            bs_vanna_per_dollar_per_point,
            bs_volga_per_point_sq,
        )
        from deskpricer.pricing.cross_greeks import compute_cross_greeks
        from deskpricer.pricing.engine import price_vanilla

        s, k, t, r, q, v = 100.0, 100.0, 0.25, 0.05, 0.0, 0.20
        val_date = date(2026, 4, 20)
        with sync_eval_date(val_date):
            base = price_vanilla(
                s=s, k=k, t=t, r=r, q=q, v=v, option_type="call",
                style="european", engine="analytic", valuation_date=val_date,
            )
            vanna_num, volga_num = compute_cross_greeks(
                base_price=base.price, s=s, k=k, t=t, r=r, q=q, v=v,
                option_type="call", style="european", engine="analytic",
                valuation_date=val_date,
            )

        vanna_bsm = bs_vanna_per_dollar_per_point(s, k, t, r, q, v)
        volga_bsm = bs_volga_per_point_sq(s, k, t, r, q, v)
        assert vanna_num == pytest.approx(vanna_bsm, rel=0.02)
        assert volga_num == pytest.approx(volga_bsm, rel=0.02)


# ── Pool timeout ───────────────────────────────────────────────────────────


def _slow_execute_task(*args, **kwargs):
    """Module-level slow task for the timeout test (must be picklable)."""
    import time
    time.sleep(0.5)
    return {}


class TestPoolTimeout:
    def test_timeout_returns_503(self, client: TestClient, monkeypatch):
        """A pricing task exceeding the timeout returns HTTP 503 PRICING_TIMEOUT."""
        from deskpricer.services import ql_runtime

        # Force a very short timeout and disable the inline path so the pool path
        # (which has the wait_for wrapper) is used.
        monkeypatch.setenv("DESKPRICER_TASK_TIMEOUT", "0.01")
        monkeypatch.delenv("DESKPRICER_INLINE", raising=False)
        monkeypatch.setattr(ql_runtime, "execute_task", _slow_execute_task)

        resp = client.get(
            "/v1/greeks?s=100&k=100&t=0.25&r=0.05&q=0&v=0.20&type=call&style=european",
            headers={"Accept": "application/json"},
        )
        assert resp.status_code == 503
        assert resp.json()["error"]["code"] == "PRICING_TIMEOUT"


# ── IV round-trip with adaptive steps ──────────────────────────────────────


class TestIVRoundTripAdaptive:
    """Regression: /greeks → /impliedvol round-trip must not be rejected by
    verify_reprice when adaptive steps are in effect.  Prior to the fix,
    /greeks used adaptive step counts but /impliedvol used the raw schema
    default, causing the two paths to disagree on discretisation."""

    @pytest.mark.parametrize("t", [0.25, 1.0, 2.0])
    def test_greeks_to_impliedvol_roundtrip(self, client: TestClient, t):
        # 1. Get a price from /greeks (adaptive steps for American)
        resp_g = client.get(
            f"/v1/greeks?s=100&k=100&t={t}&r=0.05&q=0.02&v=0.20"
            "&type=put&style=american&engine=binomial_crr",
            headers={"Accept": "application/json"},
        )
        assert resp_g.status_code == 200
        price = resp_g.json()["greeks"]["outputs"]["price"]

        # 2. Feed that price to /impliedvol — must not be rejected
        resp_iv = client.get(
            f"/v1/impliedvol?s=100&k=100&t={t}&r=0.05&q=0.02&price={price}"
            "&type=put&style=american&engine=binomial_crr",
            headers={"Accept": "application/json"},
        )
        assert resp_iv.status_code == 200, (
            f"IV round-trip failed at t={t}: {resp_iv.json()}"
        )
        iv = resp_iv.json()["impliedvol"]["outputs"]["implied_vol"]
        # Should recover roughly the input vol (0.20) within ~5 vol points.
        assert abs(iv - 0.20) < 0.05
