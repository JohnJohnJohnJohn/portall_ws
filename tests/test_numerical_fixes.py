"""Regression tests for the numerical-analysis fixes.

Covers:
1. IV no-arb pre-check uses the solver's whole-day-grid T (deep-ITM targets
   now fail with the informative lower-bound message, not the generic
   solver-bounds one).
2. American lower bound is the undiscounted intrinsic (HKEX settlement case
   family).
3. Low-vega ill-conditioning warning on deep-ITM IV solves.
4. American cross-greeks low-steps lattice-noise warning.
5. Deep-ITM closed-form precision: with the day-grid T matched, prices sit on
   the discounted lower bound to ~1e-10 (the CDF saturates exactly; the
   historical "-1e-3 below bound" observation was a probe T mismatch, not
   cancellation).
"""

import logging
import math
import os
from datetime import date

import pytest
from fastapi.testclient import TestClient

os.environ.setdefault("DESKPRICER_INLINE", "1")


VAL = date(2026, 10, 12)
J = {"Accept": "application/json"}


def _get(client, path, params):
    q = "&".join(f"{k}={v}" for k, v in params.items())
    return client.get(f"{path}?{q}", headers=J)


class TestPreCheckDayGridT:
    def test_deep_itm_target_below_daygrid_floor_informative_error(self, client: TestClient):
        """Target between the raw-t floor and the day-grid floor must say 'lower bound'."""
        # s=100, k=100/1.5, t=0.5: day-grid expiry is 183 days, whose floor is
        # ~0.0013 above the raw-t floor; 33.8275 sits in that gap.
        resp = _get(client, "/v1/impliedvol", dict(
            s=100, k=66.66666666666667, t=0.5, r=0.03, q=0.01, price=33.8275,
            type="call", style="european", valuation_date="2026-10-12",
        ))
        assert resp.status_code == 400
        msg = resp.json()["error"]["message"]
        assert "below the no-arbitrage lower bound" in msg
        assert "33.828" in msg  # the day-grid floor value

    def test_valid_deep_itm_target_still_solves(self, client: TestClient):
        resp = _get(client, "/v1/impliedvol", dict(
            s=100, k=66.66666666666667, t=0.5, r=0.03, q=0.01, price=33.90,
            type="call", style="european", valuation_date="2026-10-12",
        ))
        assert resp.status_code == 200, resp.text
        assert resp.json()["impliedvol"]["outputs"]["implied_vol"] > 0


class TestAmericanIntrinsicBound:
    def test_hkex_settlement_case_names_intrinsic(self, client: TestClient):
        """The real-world case: 22.71 vs K-S = 23.20 must say 'lower bound 23.200000'."""
        resp = _get(client, "/v1/impliedvol", dict(
            s=56.8, k=80, t=0.224657534246575, r=0.0328571, q=0, price=22.71,
            type="put", style="american", valuation_date="2026-10-09",
        ))
        assert resp.status_code == 400
        msg = resp.json()["error"]["message"]
        assert "below the no-arbitrage lower bound 23.200000" in msg

    def test_american_price_above_intrinsic_solves(self, client: TestClient):
        resp = _get(client, "/v1/impliedvol", dict(
            s=100, k=110, t=0.25, r=0.03, q=0.01, price=10.5,
            type="put", style="american", valuation_date="2026-10-12",
            steps=300, verify_reprice="false",
        ))
        assert resp.status_code == 200, resp.text

    def test_european_bound_unchanged_for_european_style(self, client: TestClient):
        """European requests keep the discounted bound (below intrinsic can solve)."""
        resp = _get(client, "/v1/impliedvol", dict(
            s=100, k=110, t=0.25, r=0.03, q=0.01, price=9.6,
            type="put", style="european", valuation_date="2026-10-12",
        ))
        assert resp.status_code == 200, resp.text


class TestLowVegaWarning:
    def test_deep_itm_low_vol_solve_warns(self, client: TestClient, caplog):
        with caplog.at_level(logging.WARNING, logger="deskpricer"):
            resp = _get(client, "/v1/impliedvol", dict(
                s=100, k=145, t=0.25, r=0.03, q=0.01, price=44.20,
                type="put", style="european", valuation_date="2026-10-12",
            ))
        assert resp.status_code == 200
        assert any("ill-conditioned" in r.message for r in caplog.records)

    def test_atm_solve_does_not_warn(self, client: TestClient, caplog):
        with caplog.at_level(logging.WARNING, logger="deskpricer"):
            resp = _get(client, "/v1/impliedvol", dict(
                s=100, k=100, t=0.25, r=0.03, q=0.01, price=6.0,
                type="call", style="european", valuation_date="2026-10-12",
            ))
        assert resp.status_code == 200
        assert not any("ill-conditioned" in r.message for r in caplog.records)


class TestCrossGreeksStepWarning:
    BASE = dict(
        s_t_minus_1=100, s_t=101, k=100, t_t_minus_1=1.0,
        t_t=0.9972602739726027, r_t_minus_1=0.03, r_t=0.03,
        q_t_minus_1=0.01, q_t=0.01, v_t_minus_1=0.25, v_t=0.26,
        type="put", style="american",
        valuation_date_t_minus_1="2026-10-12", valuation_date_t="2026-10-13",
        cross_greeks="true",
    )

    def test_low_steps_warns(self, client: TestClient, caplog):
        with caplog.at_level(logging.WARNING, logger="deskpricer"):
            resp = _get(client, "/v1/pnl_attribution", dict(self.BASE, steps=500))
        assert resp.status_code == 200
        assert any("lattice-noise" in r.message for r in caplog.records)

    def test_high_steps_does_not_warn(self, client: TestClient, caplog):
        with caplog.at_level(logging.WARNING, logger="deskpricer"):
            resp = _get(client, "/v1/pnl_attribution", dict(self.BASE, steps=2500))
        assert resp.status_code == 200
        assert not any("lattice-noise" in r.message for r in caplog.records)


class TestDeepItmClosedFormPrecision:
    @pytest.mark.parametrize("k", [90.0, 70.0, 50.0, 25.0, 10.0])
    def test_deep_itm_price_on_daygrid_floor(self, k):
        """At matched day-grid T the deep-ITM price sits on the discounted
        lower bound to 1e-10 (double-precision CDF saturation is exact; the
        previously reported -1e-3 deviation was a T-grid artifact)."""

        from deskpricer.pricing.bsm_fast import price_european_bsm
        from deskpricer.pricing.conventions import (
            default_day_count,
            expiry_from_t,
            get_calendar,
            ql_date_from_iso,
        )

        s, r, q, v, t = 100.0, 0.03, 0.01, 0.2, 0.5
        qd = ql_date_from_iso(VAL)
        exp = expiry_from_t(qd, t, get_calendar("null"))
        teff = default_day_count().yearFraction(qd, exp)
        price = price_european_bsm(s, k, t, r, q, v, "call", VAL, calendar_name="null").price
        floor = s * math.exp(-q * teff) - k * math.exp(-r * teff)
        # Never below the discounted floor (the historical misreading).
        assert price - floor >= -1e-10, f"price below floor by {floor - price:+.2e}"
        # In the CDF-saturation region (d1 >= ~10) time value is dust.
        d1 = (math.log(s / k) + (r - q + 0.5 * v * v) * teff) / (v * math.sqrt(teff))
        if d1 >= 10.0:
            assert price - floor <= 1e-6, f"unexpected time value {price - floor:+.2e} at d1={d1:.1f}"
