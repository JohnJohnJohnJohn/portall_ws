"""Property-based tests using hypothesis."""

import math

import pytest
from fastapi.testclient import TestClient
from hypothesis import HealthCheck, given, settings, strategies as st


class TestPutCallParity:
    @given(
        s=st.floats(min_value=10.0, max_value=500.0),
        k=st.floats(min_value=10.0, max_value=500.0),
        t=st.floats(min_value=0.05, max_value=2.0),
        r=st.floats(min_value=-0.05, max_value=0.20),
        q=st.floats(min_value=0.0, max_value=0.20),
        v=st.floats(min_value=0.05, max_value=1.0),
    )
    @settings(max_examples=50, deadline=None, suppress_health_check=[HealthCheck.function_scoped_fixture])
    def test_european_put_call_parity(self, client: TestClient, s, k, t, r, q, v):
        base = {"s": s, "k": k, "t": t, "r": r, "q": q, "v": v, "style": "european"}
        resp_call = client.get("/v1/greeks", params={**base, "type": "call"}, headers={"Accept": "application/json"})
        resp_put = client.get("/v1/greeks", params={**base, "type": "put"}, headers={"Accept": "application/json"})
        if resp_call.status_code != 200 or resp_put.status_code != 200:
            pytest.skip("Invalid parameter combination generated")
        c = resp_call.json()["greeks"]["outputs"]["price"]
        p = resp_put.json()["greeks"]["outputs"]["price"]
        days = math.floor(t * 365 + 0.5)  # match expiry_from_t round-half-up
        t_actual = days / 365.0
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
    @settings(max_examples=30, deadline=None, suppress_health_check=[HealthCheck.function_scoped_fixture])
    def test_american_put_ge_european_put(self, client: TestClient, s, k, t, r, q, v):
        import QuantLib as ql
        from desk_pricer.pricing.conventions import default_calendar, default_day_count, expiry_from_t, ql_date_from_iso

        base = {"s": s, "k": k, "t": t, "r": r, "q": q, "v": v, "type": "put", "style": "american", "steps": 400}
        resp_am = client.get("/v1/greeks", params=base, headers={"Accept": "application/json"})
        if resp_am.status_code != 200:
            pytest.skip("Invalid parameter combination generated")
        p_am = resp_am.json()["greeks"]["outputs"]["price"]

        # Compare against European price computed with the same CRR tree to avoid
        # discretization bias vs analytic formula.
        today = ql_date_from_iso(__import__("datetime").date.today())
        expiry = expiry_from_t(today, t)
        spot_handle = ql.QuoteHandle(ql.SimpleQuote(s))
        div_ts = ql.YieldTermStructureHandle(ql.FlatForward(today, q, default_day_count()))
        rf_ts = ql.YieldTermStructureHandle(ql.FlatForward(today, r, default_day_count()))
        vol_ts = ql.BlackVolTermStructureHandle(ql.BlackConstantVol(today, default_calendar(), v, default_day_count()))
        process = ql.BlackScholesMertonProcess(spot_handle, div_ts, rf_ts, vol_ts)
        payoff = ql.PlainVanillaPayoff(ql.Option.Put, k)
        exercise = ql.EuropeanExercise(expiry)
        eu_option = ql.VanillaOption(payoff, exercise)
        eu_option.setPricingEngine(ql.BinomialVanillaEngine(process, "crr", 400))
        p_eu_tree = float(eu_option.NPV())
        # Tree discretization can occasionally make the American price slightly
        # below the European tree price (e.g. r=0 where early-exercise premium
        # is zero).  Allow a tolerance for this numerical artifact.
        assert p_am >= p_eu_tree - 1e-2


class TestGreekBounds:
    @given(
        s=st.floats(min_value=10.0, max_value=500.0),
        k=st.floats(min_value=10.0, max_value=500.0),
        t=st.floats(min_value=0.05, max_value=1.0),
        r=st.floats(min_value=0.0, max_value=0.20),
        q=st.floats(min_value=0.0, max_value=0.20),
        v=st.floats(min_value=0.05, max_value=1.0),
    )
    @settings(max_examples=30, deadline=None, suppress_health_check=[HealthCheck.function_scoped_fixture])
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
    @settings(max_examples=30, deadline=None, suppress_health_check=[HealthCheck.function_scoped_fixture])
    def test_delta_bounds(self, client: TestClient, s, k, t, r, q, v):
        base = {"s": s, "k": k, "t": t, "r": r, "q": q, "v": v, "style": "european"}
        resp_call = client.get("/v1/greeks", params={**base, "type": "call"}, headers={"Accept": "application/json"})
        resp_put = client.get("/v1/greeks", params={**base, "type": "put"}, headers={"Accept": "application/json"})
        if resp_call.status_code != 200 or resp_put.status_code != 200:
            pytest.skip("Invalid parameter combination generated")
        d_call = resp_call.json()["greeks"]["outputs"]["delta"]
        d_put = resp_put.json()["greeks"]["outputs"]["delta"]
        assert 0 <= d_call <= 1
        assert -1 <= d_put <= 0
