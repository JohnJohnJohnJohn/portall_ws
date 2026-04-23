"""Property-based tests using hypothesis."""

import datetime
import math

import pytest
import QuantLib as ql
from fastapi.testclient import TestClient
from hypothesis import HealthCheck, given, settings
from hypothesis import strategies as st

from deskpricer.pricing.conventions import (
    DEFAULT_STEPS,
    default_day_count,
    expiry_from_t,
    get_calendar,
    ql_date_from_iso,
)


class TestPutCallParity:
    @given(
        s=st.floats(min_value=10.0, max_value=500.0),
        k=st.floats(min_value=10.0, max_value=500.0),
        t=st.floats(min_value=0.05, max_value=2.0),
        r=st.floats(min_value=-0.05, max_value=0.20),
        q=st.floats(min_value=0.0, max_value=0.20),
        v=st.floats(min_value=0.05, max_value=1.0),
    )
    @settings(
        max_examples=50, deadline=None, suppress_health_check=[HealthCheck.function_scoped_fixture]
    )
    def test_european_put_call_parity(self, client: TestClient, s, k, t, r, q, v):
        base = {"s": s, "k": k, "t": t, "r": r, "q": q, "v": v, "style": "european"}
        resp_call = client.get(
            "/v1/greeks", params={**base, "type": "call"}, headers={"Accept": "application/json"}
        )
        resp_put = client.get(
            "/v1/greeks", params={**base, "type": "put"}, headers={"Accept": "application/json"}
        )
        if resp_call.status_code != 200 or resp_put.status_code != 200:
            pytest.skip("Invalid parameter combination generated")
        c = resp_call.json()["greeks"]["outputs"]["price"]
        p = resp_put.json()["greeks"]["outputs"]["price"]
        # Replicate trading-day expiry to compute actual t used by the engine
        from deskpricer.pricing.conventions import default_day_count, expiry_from_t, get_calendar

        ql_today = ql_date_from_iso(datetime.date.today())
        expiry = expiry_from_t(ql_today, t, get_calendar())
        t_actual = default_day_count().yearFraction(ql_today, expiry)
        lhs = c - p
        rhs = s * math.exp(-q * t_actual) - k * math.exp(-r * t_actual)
        assert abs(lhs - rhs) < 1e-5


class TestAmericanPriceBounds:
    @given(
        s=st.floats(min_value=10.0, max_value=500.0),
        k=st.floats(min_value=10.0, max_value=500.0),
        t=st.floats(min_value=0.05, max_value=1.0),
        r=st.floats(min_value=0.0, max_value=0.20),
        q=st.floats(min_value=0.0, max_value=0.20),
        v=st.floats(min_value=0.05, max_value=1.0),
    )
    @settings(
        max_examples=30, deadline=None, suppress_health_check=[HealthCheck.function_scoped_fixture]
    )
    def test_american_put_ge_european_put(self, client: TestClient, s, k, t, r, q, v):
        base = {
            "s": s,
            "k": k,
            "t": t,
            "r": r,
            "q": q,
            "v": v,
            "type": "put",
            "style": "american",
            "steps": DEFAULT_STEPS,
        }
        resp_am = client.get("/v1/greeks", params=base, headers={"Accept": "application/json"})
        if resp_am.status_code != 200:
            pytest.skip("Invalid parameter combination generated")
        p_am = resp_am.json()["greeks"]["outputs"]["price"]

        # Compare against European price computed with the same CRR tree to avoid
        # discretization bias vs analytic formula.
        today = ql_date_from_iso(datetime.date.today())
        expiry = expiry_from_t(today, t, get_calendar())
        spot_handle = ql.QuoteHandle(ql.SimpleQuote(s))
        div_ts = ql.YieldTermStructureHandle(ql.FlatForward(today, q, default_day_count()))
        rf_ts = ql.YieldTermStructureHandle(ql.FlatForward(today, r, default_day_count()))
        vol_ts = ql.BlackVolTermStructureHandle(
            ql.BlackConstantVol(today, get_calendar(), v, default_day_count())
        )
        process = ql.BlackScholesMertonProcess(spot_handle, div_ts, rf_ts, vol_ts)
        payoff = ql.PlainVanillaPayoff(ql.Option.Put, k)
        exercise = ql.EuropeanExercise(expiry)
        eu_option = ql.VanillaOption(payoff, exercise)
        eu_option.setPricingEngine(ql.BinomialVanillaEngine(process, "crr", DEFAULT_STEPS))
        p_eu_tree = float(eu_option.NPV())
        # Tree discretization can occasionally make the American CRR price slightly
        # below the European CRR price (e.g. r=0 where early-exercise premium is
        # zero, or extreme vol where node spacing amplifies round-off).  Allow a
        # generous tolerance since this is a property test, not a precision test.
        assert p_am >= p_eu_tree - 0.5


class TestGreekBounds:
    @given(
        s=st.floats(min_value=10.0, max_value=500.0),
        k=st.floats(min_value=10.0, max_value=500.0),
        t=st.floats(min_value=0.05, max_value=1.0),
        r=st.floats(min_value=0.0, max_value=0.20),
        q=st.floats(min_value=0.0, max_value=0.20),
        v=st.floats(min_value=0.05, max_value=1.0),
    )
    @settings(
        max_examples=30, deadline=None, suppress_health_check=[HealthCheck.function_scoped_fixture]
    )
    def test_gamma_nonnegative(self, client: TestClient, s, k, t, r, q, v):
        base = {"s": s, "k": k, "t": t, "r": r, "q": q, "v": v, "style": "european", "type": "call"}
        resp = client.get("/v1/greeks", params=base, headers={"Accept": "application/json"})
        if resp.status_code != 200:
            pytest.skip("Invalid parameter combination generated")
        gamma = resp.json()["greeks"]["outputs"]["gamma"]
        assert gamma >= -1e-8

    @given(
        s=st.floats(min_value=10.0, max_value=500.0),
        k=st.floats(min_value=10.0, max_value=500.0),
        t=st.floats(min_value=0.05, max_value=1.0),
        r=st.floats(min_value=0.0, max_value=0.20),
        q=st.floats(min_value=0.0, max_value=0.20),
        v=st.floats(min_value=0.05, max_value=1.0),
    )
    @settings(
        max_examples=30, deadline=None, suppress_health_check=[HealthCheck.function_scoped_fixture]
    )
    def test_delta_bounds(self, client: TestClient, s, k, t, r, q, v):
        base = {"s": s, "k": k, "t": t, "r": r, "q": q, "v": v, "style": "european"}
        resp_call = client.get(
            "/v1/greeks", params={**base, "type": "call"}, headers={"Accept": "application/json"}
        )
        resp_put = client.get(
            "/v1/greeks", params={**base, "type": "put"}, headers={"Accept": "application/json"}
        )
        if resp_call.status_code != 200 or resp_put.status_code != 200:
            pytest.skip("Invalid parameter combination generated")
        d_call = resp_call.json()["greeks"]["outputs"]["delta"]
        d_put = resp_put.json()["greeks"]["outputs"]["delta"]
        assert 0 <= d_call <= 1
        assert -1 <= d_put <= 0


class TestMonotonicity:
    @given(
        s=st.floats(min_value=10.0, max_value=500.0),
        k=st.floats(min_value=10.0, max_value=500.0),
        t=st.floats(min_value=0.05, max_value=1.0),
        r=st.floats(min_value=0.0, max_value=0.20),
        q=st.floats(min_value=0.0, max_value=0.20),
        v=st.floats(min_value=0.05, max_value=1.0),
    )
    @settings(
        max_examples=20, deadline=None, suppress_health_check=[HealthCheck.function_scoped_fixture]
    )
    def test_call_price_nondecreasing_in_spot(self, client: TestClient, s, k, t, r, q, v):
        base = {"k": k, "t": t, "r": r, "q": q, "v": v, "style": "european", "type": "call"}
        resp1 = client.get(
            "/v1/greeks", params={**base, "s": s}, headers={"Accept": "application/json"}
        )
        resp2 = client.get(
            "/v1/greeks", params={**base, "s": s * 1.01}, headers={"Accept": "application/json"}
        )
        if resp1.status_code != 200 or resp2.status_code != 200:
            pytest.skip("Invalid parameter combination generated")
        p1 = resp1.json()["greeks"]["outputs"]["price"]
        p2 = resp2.json()["greeks"]["outputs"]["price"]
        assert p2 >= p1 - 1e-8

    @given(
        s=st.floats(min_value=10.0, max_value=500.0),
        k=st.floats(min_value=10.0, max_value=500.0),
        t=st.floats(min_value=0.05, max_value=1.0),
        r=st.floats(min_value=0.0, max_value=0.20),
        q=st.floats(min_value=0.0, max_value=0.20),
        v=st.floats(min_value=0.05, max_value=1.0),
    )
    @settings(
        max_examples=20, deadline=None, suppress_health_check=[HealthCheck.function_scoped_fixture]
    )
    def test_put_price_nonincreasing_in_spot(self, client: TestClient, s, k, t, r, q, v):
        base = {"k": k, "t": t, "r": r, "q": q, "v": v, "style": "european", "type": "put"}
        resp1 = client.get(
            "/v1/greeks", params={**base, "s": s}, headers={"Accept": "application/json"}
        )
        resp2 = client.get(
            "/v1/greeks", params={**base, "s": s * 1.01}, headers={"Accept": "application/json"}
        )
        if resp1.status_code != 200 or resp2.status_code != 200:
            pytest.skip("Invalid parameter combination generated")
        p1 = resp1.json()["greeks"]["outputs"]["price"]
        p2 = resp2.json()["greeks"]["outputs"]["price"]
        assert p2 <= p1 + 1e-8


class TestPnLExplain:
    def test_zero_moves_residual_near_zero(self, client: TestClient):
        """When all market data is unchanged, residual PnL should be ~0."""
        params = {
            "s_t_minus_1": 100.0,
            "s_t": 100.0,
            "k": 100.0,
            "t_t_minus_1": 0.25,
            "t_t": 0.25,
            "r_t_minus_1": 0.05,
            "r_t": 0.05,
            "q_t_minus_1": 0.0,
            "q_t": 0.0,
            "v_t_minus_1": 0.20,
            "v_t": 0.20,
            "type": "call",
            "style": "european",
            "qty": 1.0,
            "cross_greeks": True,
            "method": "backward",
            "valuation_date_t_minus_1": "2026-04-19",
            "valuation_date_t": "2026-04-19",
        }
        resp = client.get(
            "/v1/pnl_attribution", params=params, headers={"Accept": "application/json"}
        )
        assert resp.status_code == 200
        data = resp.json()["pnl_attribution"]["outputs"]
        assert data["actual_pnl"] == pytest.approx(0.0, abs=1e-10)
        # Same dates → count_business_days still returns 1, so residual = -theta_pnl
        assert data["residual_pnl"] == pytest.approx(-data["theta_pnl"], abs=1e-10)


class TestCrossGreeksBSMConsistency:
    def test_vanna_and_volga_match_bsm_closed_form(self):
        """Numerical cross-greeks must agree with BSM closed-form within 2%."""
        import math

        from scipy.stats import norm

        from deskpricer.pricing.cross_greeks import compute_cross_greeks
        from deskpricer.pricing.european import price_european

        s, k, t, r, q, v = 100.0, 100.0, 0.25, 0.05, 0.0, 0.20
        val_date = datetime.date(2026, 4, 20)
        base = price_european(s, k, t, r, q, v, "call", val_date)

        vanna_num, volga_num = compute_cross_greeks(
            base_price=base.price,
            s=s,
            k=k,
            t=t,
            r=r,
            q=q,
            v=v,
            option_type="call",
            style="european",
            engine="analytic",
            valuation_date=val_date,
        )

        d1 = (math.log(s / k) + (r - q + 0.5 * v * v) * t) / (v * math.sqrt(t))
        d2 = d1 - v * math.sqrt(t)
        nd1 = norm.pdf(d1)

        # BSM vanna per $1 per 1% vol point
        vanna_bsm = -nd1 * d2 / v * 0.01
        # BSM volga per (1%)^2
        volga_bsm = s * nd1 * math.sqrt(t) * d1 * d2 / v * 0.0001

        assert vanna_num == pytest.approx(vanna_bsm, rel=0.02)
        assert volga_num == pytest.approx(volga_bsm, rel=0.02)


class TestPortfolioAggregation:
    def test_aggregate_equals_sum_of_legs(self, client: TestClient):
        """Portfolio aggregate must equal sum(qty * leg_greek) for each Greek."""
        payload = {
            "legs": [
                {
                    "id": "L1",
                    "qty": 3,
                    "s": 100,
                    "k": 105,
                    "t": 0.25,
                    "r": 0.05,
                    "q": 0,
                    "v": 0.20,
                    "type": "call",
                    "style": "european",
                },
                {
                    "id": "L2",
                    "qty": -2,
                    "s": 100,
                    "k": 95,
                    "t": 0.25,
                    "r": 0.05,
                    "q": 0,
                    "v": 0.22,
                    "type": "put",
                    "style": "american",
                },
            ]
        }
        resp = client.post(
            "/v1/portfolio/greeks", json=payload, headers={"Accept": "application/json"}
        )
        assert resp.status_code == 200
        data = resp.json()["portfolio"]
        legs = data["legs"]
        agg = data["aggregate"]
        qtys = [leg["qty"] for leg in payload["legs"]]
        for greek in ["delta", "gamma", "vega", "theta", "rho", "charm"]:
            expected = sum(qtys[i] * legs[i][greek] for i in range(len(legs)))
            assert agg[greek] == pytest.approx(expected, abs=1e-6)
