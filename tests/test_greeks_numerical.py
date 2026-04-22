"""Bump-and-revalue consistency tests for Greeks."""

from deskpricer.pricing.conventions import DEFAULT_STEPS
from fastapi.testclient import TestClient


def fetch_greeks(client, **kwargs):
    resp = client.get("/v1/greeks", params=kwargs, headers={"Accept": "application/json"})
    assert resp.status_code == 200
    return resp.json()["greeks"]["outputs"]


class TestEuropeanGreeks:
    def test_delta_call_positive(self, client: TestClient):
        g = fetch_greeks(
            client, s=100, k=100, t=0.5, r=0.05, q=0, v=0.20, type="call", style="european"
        )
        assert 0 < g["delta"] < 1

    def test_delta_put_negative(self, client: TestClient):
        g = fetch_greeks(
            client, s=100, k=100, t=0.5, r=0.05, q=0, v=0.20, type="put", style="european"
        )
        assert -1 < g["delta"] < 0

    def test_gamma_positive(self, client: TestClient):
        g = fetch_greeks(
            client, s=100, k=100, t=0.5, r=0.05, q=0, v=0.20, type="call", style="european"
        )
        assert g["gamma"] > 0

    def test_vega_positive(self, client: TestClient):
        g = fetch_greeks(
            client, s=100, k=100, t=0.5, r=0.05, q=0, v=0.20, type="call", style="european"
        )
        assert g["vega"] > 0

    def test_theta_call_negative(self, client: TestClient):
        g = fetch_greeks(
            client, s=100, k=100, t=0.5, r=0.05, q=0, v=0.20, type="call", style="european"
        )
        assert g["theta"] < 0

    def test_rho_call_positive(self, client: TestClient):
        g = fetch_greeks(
            client, s=100, k=100, t=0.5, r=0.05, q=0, v=0.20, type="call", style="european"
        )
        assert g["rho"] > 0

    def test_charm_small_and_finite(self, client: TestClient):
        g = fetch_greeks(
            client, s=100, k=100, t=0.5, r=0.05, q=0, v=0.20, type="call", style="european"
        )
        assert abs(g["charm"]) < 0.01


class TestAmericanBumpConsistency:
    def test_american_delta_bump_consistent(self, client: TestClient):
        """American delta computed via bump should be roughly consistent with price changes."""
        base = {
            "s": 100,
            "k": 100,
            "t": 0.5,
            "r": 0.05,
            "q": 0,
            "v": 0.25,
            "type": "put",
            "style": "american",
            "steps": DEFAULT_STEPS,
        }
        g = fetch_greeks(client, **base)
        p_base = g["price"]
        delta = g["delta"]
        # Bump spot by +1%
        p_up = fetch_greeks(client, **{**base, "s": 101})["price"]
        expected_change = delta * 1.0  # delta is per 1 unit change in S
        actual_change = p_up - p_base
        # Loose tolerance because binomial tree introduces noise
        assert abs(actual_change - expected_change) < 0.08
