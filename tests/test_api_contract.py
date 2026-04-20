"""API contract tests: XML/JSON toggling, error codes, schema validation."""

import xml.etree.ElementTree as ET

import pytest
from fastapi.testclient import TestClient


class TestHealth:
    def test_health_xml_default(self, client: TestClient):
        resp = client.get("/v1/health")
        assert resp.status_code == 200
        assert "xml" in resp.headers["content-type"]
        root = ET.fromstring(resp.text)
        assert root.find("status").text == "UP"
        assert float(root.find("uptime_seconds").text) >= 0

    def test_health_json_via_accept(self, client: TestClient):
        resp = client.get("/v1/health", headers={"Accept": "application/json"})
        assert resp.status_code == 200
        assert resp.headers["content-type"] == "application/json"
        data = resp.json()
        assert data["health"]["status"] == "UP"

    def test_health_json_via_query(self, client: TestClient):
        resp = client.get("/v1/health?format=json")
        assert resp.status_code == 200
        assert resp.headers["content-type"] == "application/json"


class TestVersion:
    def test_version_xml(self, client: TestClient):
        resp = client.get("/v1/version")
        assert resp.status_code == 200
        root = ET.fromstring(resp.text)
        assert root.find("service").text == "1.0.0"
        assert root.find("quantlib").text is not None
        assert root.find("python").text is not None


class TestGreeks:
    def test_greeks_european_xml(self, client: TestClient):
        resp = client.get(
            "/v1/greeks?s=100&k=105&t=0.25&r=0.05&q=0.02&v=0.20&type=call&style=european"
        )
        assert resp.status_code == 200
        assert "xml" in resp.headers["content-type"]
        root = ET.fromstring(resp.text)
        assert root.find("meta/service_version").text == "1.0.0"
        assert float(root.find("outputs/price").text) > 0

    def test_greeks_european_json(self, client: TestClient):
        resp = client.get(
            "/v1/greeks?s=100&k=105&t=0.25&r=0.05&q=0.02&v=0.20&type=call&style=european",
            headers={"Accept": "application/json"},
        )
        assert resp.status_code == 200
        assert resp.headers["content-type"] == "application/json"
        data = resp.json()
        assert data["greeks"]["meta"]["engine"] == "analytic"
        assert data["greeks"]["outputs"]["price"] > 0

    def test_greeks_missing_param(self, client: TestClient):
        resp = client.get("/v1/greeks?s=100&k=105")
        assert resp.status_code == 400
        root = ET.fromstring(resp.text)
        assert root.find("code").text == "INVALID_INPUT"

    def test_greeks_unsupported_american_analytic(self, client: TestClient):
        resp = client.get(
            "/v1/greeks?s=100&k=100&t=0.25&r=0.05&q=0&v=0.20&type=put&style=american&engine=analytic"
        )
        assert resp.status_code == 422
        root = ET.fromstring(resp.text)
        assert root.find("code").text == "UNSUPPORTED_COMBINATION"

    def test_greeks_invalid_volatility(self, client: TestClient):
        resp = client.get(
            "/v1/greeks?s=100&k=100&t=0.25&r=0.05&q=0&v=-0.1&type=call&style=european"
        )
        assert resp.status_code == 400
        root = ET.fromstring(resp.text)
        assert root.find("code").text == "INVALID_INPUT"

    def test_greeks_put_call_parity(self, client: TestClient):
        """European call/put with same params should satisfy parity."""
        base = {"s": 100, "k": 100, "t": 0.5, "r": 0.05, "q": 0.02, "v": 0.20, "style": "european"}
        resp_call = client.get("/v1/greeks", params={**base, "type": "call"}, headers={"Accept": "application/json"})
        resp_put = client.get("/v1/greeks", params={**base, "type": "put"}, headers={"Accept": "application/json"})
        assert resp_call.status_code == 200
        assert resp_put.status_code == 200
        c = resp_call.json()["greeks"]["outputs"]["price"]
        p = resp_put.json()["greeks"]["outputs"]["price"]
        # C - P = S*exp(-qT) - K*exp(-rT) using actual T from rounded days
        import math
        lhs = c - p
        days = round(0.5 * 365)
        t_actual = days / 365.0
        rhs = 100 * math.exp(-0.02 * t_actual) - 100 * math.exp(-0.05 * t_actual)
        assert abs(lhs - rhs) < 1e-6


class TestPortfolio:
    def test_portfolio_json_default(self, client: TestClient):
        payload = {
            "valuation_date": "2026-04-20",
            "legs": [
                {
                    "id": "L1",
                    "qty": 10,
                    "s": 100,
                    "k": 105,
                    "t": 0.25,
                    "r": 0.045,
                    "q": 0.012,
                    "v": 0.22,
                    "type": "call",
                    "style": "european",
                },
                {
                    "id": "L2",
                    "qty": -5,
                    "s": 100,
                    "k": 95,
                    "t": 0.25,
                    "r": 0.045,
                    "q": 0.012,
                    "v": 0.24,
                    "type": "put",
                    "style": "american",
                },
            ],
        }
        resp = client.post("/v1/portfolio/greeks", json=payload, headers={"Accept": "application/json"})
        assert resp.status_code == 200
        data = resp.json()
        assert len(data["portfolio"]["legs"]["leg"]) == 2
        agg = data["portfolio"]["aggregate"]
        assert "delta" in agg

    def test_portfolio_aggregate_math(self, client: TestClient):
        payload = {
            "legs": [
                {"id": "L1", "qty": 2, "s": 100, "k": 100, "t": 0.25, "r": 0.05, "q": 0, "v": 0.20, "type": "call", "style": "european"},
                {"id": "L2", "qty": -1, "s": 100, "k": 100, "t": 0.25, "r": 0.05, "q": 0, "v": 0.20, "type": "call", "style": "european"},
            ]
        }
        resp = client.post("/v1/portfolio/greeks", json=payload, headers={"Accept": "application/json"})
        assert resp.status_code == 200
        data = resp.json()
        legs = data["portfolio"]["legs"]["leg"]
        agg = data["portfolio"]["aggregate"]
        # Aggregate should equal 2*L1 - 1*L2
        for greek in ["delta", "gamma", "vega", "theta", "rho", "charm"]:
            expected = 2 * legs[0][greek] - 1 * legs[1][greek]
            assert abs(agg[greek] - expected) < 1e-6
