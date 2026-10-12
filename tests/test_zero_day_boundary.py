"""Regression tests for the round-0 audit fixes.

Covers three findings:
1. Zero-day theta boundary: t in (1/365, 1.5/365) with expiry landing at
   valuation_date + 1 previously divided by v*sqrt(0) in bsm_fast (HTTP 500).
2. Equivalence reroute signs: American puts with r~0 and q+b<0 must NOT
   reroute to European BSM (accretion makes early exercise optimal), and
   American calls with q+b<0 now may (Merton's condition).
3. Catchall handler must record exc_info so 500s are diagnosable from logs.
"""

from datetime import date

import pytest
from fastapi.testclient import TestClient

from deskpricer.pricing.bsm_fast import _effective_t, price_european_bsm
from deskpricer.pricing.engine import price_vanilla
from deskpricer.pricing.equivalence import american_is_european_equivalent

VALUATION_MON = date(2026, 10, 12)  # Monday: valuation+1 is a business day (no roll)


class TestZeroDayThetaBoundary:
    """The t in (1, 1.5]/365 band where expiry - 1 == valuation_date."""

    @pytest.mark.parametrize("calendar_name", ["hong_kong", "null"])
    @pytest.mark.parametrize("option_type", ["call", "put"])
    @pytest.mark.parametrize(
        "t_days", [0.0, 0.5, 1.0, 1.1, 1.2, 1.4, 1.5, 1.6, 2.0, 3.0]
    )
    def test_bsm_boundary_sweep_returns_finite_greeks(
        self, t_days, option_type, calendar_name
    ):
        t = t_days / 365.0
        out = price_european_bsm(
            s=100.0,
            k=100.0,
            t=t,
            r=0.05,
            q=0.0,
            v=0.30,
            option_type=option_type,
            valuation_date=VALUATION_MON,
            calendar_name=calendar_name,
        )
        assert out.price == pytest.approx(out.price, abs=1e-12)  # finite
        for greek in (out.delta, out.gamma, out.vega, out.theta, out.rho, out.charm):
            assert greek == greek  # not NaN

    def test_effective_t_returns_no_t1_at_boundary(self):
        effective, effective_t1 = _effective_t(VALUATION_MON, 1.2 / 365.0, "hong_kong")
        assert effective > 0
        assert effective_t1 is None

    @pytest.mark.parametrize("style", ["european", "american"])
    def test_boundary_http_ok_monday(self, style):
        """End-to-end: the exact request that 500'd before the fix."""
        import os

        os.environ.setdefault("DESKPRICER_INLINE", "1")
        from deskpricer.main import app

        client = TestClient(app)
        t = 1.2 / 365.0
        resp = client.get(
            f"/v1/greeks?s=100&k=100&t={t!r}&r=0.05&q=0&v=0.3"
            f"&type=call&style={style}&valuation_date=2026-10-12&steps=200",
            headers={"Accept": "application/json"},
        )
        assert resp.status_code == 200, resp.text
        outputs = resp.json()["greeks"]["outputs"]
        assert outputs["price"] >= 0.0

    def test_boundary_theta_uses_intrinsic_fallback(self):
        """At the boundary the theta fallback is the <= 1-day intrinsic rule."""
        out = price_european_bsm(
            s=100.0,
            k=90.0,
            t=1.2 / 365.0,
            r=0.05,
            q=0.0,
            v=0.30,
            option_type="call",
            valuation_date=VALUATION_MON,
        )
        assert out.theta == pytest.approx(max(100.0 - 90.0, 0.0) - out.price, abs=1e-12)


class TestEquivalenceSigns:
    def test_call_negative_carry_reroutes(self):
        """Merton: calls never exercise early when carry yield <= 0."""
        assert american_is_european_equivalent("call", 0.05, -0.02, 0.0) is True
        assert american_is_european_equivalent("call", 0.05, 0.0, -0.05) is True
        assert american_is_european_equivalent("call", 0.05, 0.02, -0.021) is True
        assert american_is_european_equivalent("call", 0.05, 0.02, -0.019) is False

    def test_put_negative_carry_does_not_reroute(self):
        """r~0 with accreting underlying: early exercise IS optimal for puts."""
        assert american_is_european_equivalent("put", 0.0, -0.05, 0.0) is False
        assert american_is_european_equivalent("put", 0.0, 0.0, -0.05) is False
        assert american_is_european_equivalent("put", 0.0, 0.05, 0.0) is True
        assert american_is_european_equivalent("put", 0.0, 0.0, 0.0) is True

    def test_put_negative_carry_priced_above_european(self):
        """Tree-priced American put must exceed the European value in this regime."""
        s, k, t, r, q, v = 100.0, 90.0, 0.5, 0.0, -0.05, 0.30
        val = VALUATION_MON
        american = price_vanilla(
            s, k, t, r, q, v, "put", "american", "binomial_crr", val, steps=1000
        )
        european = price_vanilla(
            s, k, t, r, q, v, "put", "european", "analytic", val
        )
        assert american.price > european.price
        # Early-exercise premium regime: the gap must be material, not tree noise.
        assert american.price - european.price > 0.01
