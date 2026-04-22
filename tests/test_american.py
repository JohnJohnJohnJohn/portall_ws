"""American option tests vs published binomial results."""

from deskpricer.pricing.conventions import DEFAULT_STEPS
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
                "steps": DEFAULT_STEPS,
                "valuation_date": "2026-04-20",
            },
            headers={"Accept": "application/json"},
        )
        assert resp.status_code == 200
        price = resp.json()["greeks"]["outputs"]["price"]
        # QuantLib CRR DEFAULT_STEPS-step converges to ~4.283 for these params
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
        resp_am = client.get(
            "/v1/greeks",
            params={**params, "style": "american", "steps": DEFAULT_STEPS},
            headers={"Accept": "application/json"},
        )
        resp_eu = client.get(
            "/v1/greeks",
            params={**params, "style": "european"},
            headers={"Accept": "application/json"},
        )
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
        resp_am = client.get(
            "/v1/greeks",
            params={**params, "style": "american", "steps": 400},
            headers={"Accept": "application/json"},
        )
        resp_eu = client.get(
            "/v1/greeks",
            params={**params, "style": "european"},
            headers={"Accept": "application/json"},
        )
        p_am = resp_am.json()["greeks"]["outputs"]["price"]
        p_eu = resp_eu.json()["greeks"]["outputs"]["price"]
        assert abs(p_am - p_eu) < 0.01

    def test_american_min_steps(self, client: TestClient):
        """American option with minimum steps (10) should price successfully."""
        resp = client.get(
            "/v1/greeks?s=100&k=100&t=0.25&r=0.05&q=0&v=0.20&type=put&style=american&steps=10",
            headers={"Accept": "application/json"},
        )
        assert resp.status_code == 200
        assert resp.json()["greeks"]["outputs"]["price"] > 0

    def test_american_max_steps(self, client: TestClient):
        """American option with maximum steps (5000) should price successfully."""
        resp = client.get(
            "/v1/greeks?s=100&k=100&t=0.25&r=0.05&q=0&v=0.20&type=put&style=american&steps=5000",
            headers={"Accept": "application/json"},
        )
        assert resp.status_code == 200
        assert resp.json()["greeks"]["outputs"]["price"] > 0


class TestPricingLayerNaNInf:
    def test_nan_inf_inputs_raise_structured_error(self):
        """price_vanilla must reject NaN/Inf for all inputs, not leak QuantLib crashes."""
        from datetime import date

        import pytest
        from deskpricer.errors import UnsupportedCombinationError
        from deskpricer.pricing.engine import price_vanilla

        base = {
            "s": 100.0,
            "k": 100.0,
            "t": 0.25,
            "r": 0.05,
            "q": 0.0,
            "v": 0.20,
            "option_type": "call",
            "style": "european",
            "engine": "analytic",
            "valuation_date": date(2026, 4, 20),
        }
        for field in ("s", "k", "v", "r", "q", "t"):
            for bad_val in (float("nan"), float("inf"), -float("inf")):
                params = {**base, field: bad_val}
                with pytest.raises(UnsupportedCombinationError):
                    price_vanilla(**params)
