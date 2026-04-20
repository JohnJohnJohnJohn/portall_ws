"""American option tests vs published binomial results."""

import pytest
from fastapi.testclient import TestClient


class TestAmericanPut:
    def test_haug_american_put(self, client: TestClient):
        """Haug Table benchmark: S=50, K=50, r=0.10, sigma=0.40, T=0.4167.
        Haug reference ~4.49 for American put (approximate due to tree discretization).
        """
        resp = client.get(
            "/v1/greeks",
            params={
                "s": 50,
                "k": 50,
                "t": 0.4167,
                "r": 0.10,
                "q": 0,
                "v": 0.40,
                "type": "put",
                "style": "american",
                "steps": 400,
                "valuation_date": "2026-04-20",
            },
            headers={"Accept": "application/json"},
        )
        assert resp.status_code == 200
        price = resp.json()["greeks"]["outputs"]["price"]
        # QuantLib CRR 400-step converges to ~4.283 for these params
        assert abs(price - 4.283) < 0.01

    def test_american_put_ge_european_put(self, client: TestClient):
        """American put price should be >= European put price with same params."""
        params = {
            "s": 100,
            "k": 100,
            "t": 0.5,
            "r": 0.05,
            "q": 0.02,
            "v": 0.25,
            "type": "put",
        }
        resp_am = client.get("/v1/greeks", params={**params, "style": "american", "steps": 400}, headers={"Accept": "application/json"})
        resp_eu = client.get("/v1/greeks", params={**params, "style": "european"}, headers={"Accept": "application/json"})
        assert resp_am.status_code == 200
        assert resp_eu.status_code == 200
        p_am = resp_am.json()["greeks"]["outputs"]["price"]
        p_eu = resp_eu.json()["greeks"]["outputs"]["price"]
        assert p_am >= p_eu

    def test_american_call_no_div_ge_european(self, client: TestClient):
        """American call without dividends should equal European call."""
        params = {
            "s": 100,
            "k": 100,
            "t": 0.5,
            "r": 0.05,
            "q": 0,
            "v": 0.25,
            "type": "call",
        }
        resp_am = client.get("/v1/greeks", params={**params, "style": "american", "steps": 400}, headers={"Accept": "application/json"})
        resp_eu = client.get("/v1/greeks", params={**params, "style": "european"}, headers={"Accept": "application/json"})
        p_am = resp_am.json()["greeks"]["outputs"]["price"]
        p_eu = resp_eu.json()["greeks"]["outputs"]["price"]
        assert abs(p_am - p_eu) < 0.01
