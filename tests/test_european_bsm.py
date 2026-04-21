"""European option tests against textbook and direct BSM values."""

import math

import pytest
from fastapi.testclient import TestClient
from scipy.stats import norm


def bsm_price(s, k, t, r, q, v, option_type):
    """Direct Black-Scholes-Merton price for verification."""
    d1 = (math.log(s / k) + (r - q + 0.5 * v ** 2) * t) / (v * math.sqrt(t))
    d2 = d1 - v * math.sqrt(t)
    if option_type == "call":
        return s * math.exp(-q * t) * norm.cdf(d1) - k * math.exp(-r * t) * norm.cdf(d2)
    else:
        return k * math.exp(-r * t) * norm.cdf(-d2) - s * math.exp(-q * t) * norm.cdf(-d1)


class TestHullReference:
    def test_hull_example_european_call(self, client: TestClient):
        """Hull 8e Example 15.6: S=42, K=40, r=0.10, q=0, sigma=0.20, T=0.5.
        Because QuantLib uses calendar dates, the exact year fraction will
        differ slightly from 0.5. We compare against the BSM price using the
        same rounded days (182) => T=182/365.
        """
        s, k, r, q, v = 42.0, 40.0, 0.10, 0.0, 0.20
        t_input = 0.5
        # Our conventions use round-half-up, not banker's rounding
        days = math.floor(t_input * 365 + 0.5)
        t_actual = days / 365.0
        expected = bsm_price(s, k, t_actual, r, q, v, "call")

        resp = client.get(
            "/v1/greeks",
            params={
                "s": s,
                "k": k,
                "t": t_input,
                "r": r,
                "q": q,
                "v": v,
                "type": "call",
                "style": "european",
                "valuation_date": "2026-04-20",
            },
            headers={"Accept": "application/json"},
        )
        assert resp.status_code == 200
        price = resp.json()["greeks"]["outputs"]["price"]
        assert abs(price - expected) < 1e-6


class TestEuropeanProperties:
    def test_call_price_increases_with_spot(self, client: TestClient):
        resp1 = client.get("/v1/greeks", params={"s": 90, "k": 100, "t": 0.5, "r": 0.05, "q": 0, "v": 0.20, "type": "call", "style": "european"}, headers={"Accept": "application/json"})
        resp2 = client.get("/v1/greeks", params={"s": 100, "k": 100, "t": 0.5, "r": 0.05, "q": 0, "v": 0.20, "type": "call", "style": "european"}, headers={"Accept": "application/json"})
        p1 = resp1.json()["greeks"]["outputs"]["price"]
        p2 = resp2.json()["greeks"]["outputs"]["price"]
        assert p2 > p1

    def test_put_price_increases_with_strike(self, client: TestClient):
        resp1 = client.get("/v1/greeks", params={"s": 100, "k": 90, "t": 0.5, "r": 0.05, "q": 0, "v": 0.20, "type": "put", "style": "european"}, headers={"Accept": "application/json"})
        resp2 = client.get("/v1/greeks", params={"s": 100, "k": 100, "t": 0.5, "r": 0.05, "q": 0, "v": 0.20, "type": "put", "style": "european"}, headers={"Accept": "application/json"})
        p1 = resp1.json()["greeks"]["outputs"]["price"]
        p2 = resp2.json()["greeks"]["outputs"]["price"]
        assert p2 > p1
