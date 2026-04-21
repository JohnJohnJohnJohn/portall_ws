"""API contract tests: XML/JSON toggling, error codes, schema validation."""

import math
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

    def test_health_xml_with_misleading_accept(self, client: TestClient):
        """Accept: application/something-json should NOT trigger JSON."""
        resp = client.get("/v1/health", headers={"Accept": "application/something-json"})
        assert resp.status_code == 200
        assert "xml" in resp.headers["content-type"]


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

    def test_greeks_validation_error_formatting(self, client: TestClient):
        """Validation errors should be concise, not full Pydantic tracebacks."""
        resp = client.get(
            "/v1/greeks?s=bad&k=100&t=0.5&r=0.05&q=0&v=0.20&type=call&style=european",
            headers={"Accept": "application/json"},
        )
        assert resp.status_code == 400
        msg = resp.json()["error"]["message"]
        # Should be a short message like "Input should be a valid number..."
        assert "pydantic.dev" not in msg.lower()
        assert len(msg) < 200

    def test_greeks_xml_with_control_chars(self, client: TestClient):
        """Error messages with control chars should still produce valid XML."""
        # Pass an invalid value that will end up in the error message
        resp = client.get(
            "/v1/greeks?s=100&k=100&t=0.5&r=0.05&q=0&v=0.20&type=call&style=european&bump_vol_abs=999",
        )
        assert resp.status_code == 400
        # ET.fromstring will raise ParseError if XML contains illegal chars
        root = ET.fromstring(resp.text)
        assert root.find("code").text == "INVALID_INPUT"

    def test_xml_sanitizer_strips_control_chars(self):
        """Unit test for _sanitize_for_xml with actual control characters."""
        from desk_pricer.responses import _sanitize_for_xml

        dirty = "Error: \x00\x01\x02\x03\x0b\x0c\x1f\x7f\x84\x86\x9f"
        clean = _sanitize_for_xml(dirty)
        assert clean == "Error: "
        # Verify the result is safe for xmltodict
        import xmltodict
        payload = {"error": {"message": clean}}
        xml = xmltodict.unparse(payload, pretty=True, full_document=False)
        assert "Error: " in xml

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

    def test_greeks_t_zero_floored_to_one_day(self, client: TestClient):
        """t=0 should be floored to 1 day, returning sensible Greeks rather than collapsing to zero."""
        resp = client.get(
            "/v1/greeks?s=100&k=100&t=0&r=0.05&q=0&v=0.20&type=call&style=european",
            headers={"Accept": "application/json"},
        )
        assert resp.status_code == 200
        data = resp.json()["greeks"]["outputs"]
        assert data["price"] > 0
        assert 0 < data["delta"] < 1
        assert data["gamma"] > 0
        assert data["theta"] < 0

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
        lhs = c - p
        days = math.floor(0.5 * 365 + 0.5)  # match expiry_from_t round-half-up
        t_actual = days / 365.0
        rhs = 100 * math.exp(-0.02 * t_actual) - 100 * math.exp(-0.05 * t_actual)
        assert abs(lhs - rhs) < 1e-6


class TestImpliedVol:
    def test_impliedvol_european_roundtrip(self, client: TestClient):
        """Price at known vol → IV should recover vol within tolerance."""
        base = {"s": 100, "k": 100, "t": 0.5, "r": 0.05, "q": 0.02, "v": 0.20, "type": "call", "style": "european"}
        resp_price = client.get("/v1/greeks", params=base, headers={"Accept": "application/json"})
        assert resp_price.status_code == 200
        price = resp_price.json()["greeks"]["outputs"]["price"]

        iv_params = {k: v for k, v in base.items() if k != "v"}
        iv_params["price"] = price
        resp_iv = client.get("/v1/impliedvol", params=iv_params, headers={"Accept": "application/json"})
        assert resp_iv.status_code == 200
        data = resp_iv.json()["impliedvol"]
        assert data["meta"]["engine"] == "analytic"
        iv = data["outputs"]["implied_vol"]
        assert abs(iv - 0.20) < 1e-4
        npv_check = data["outputs"]["npv_at_iv"]
        assert abs(npv_check - price) < 1e-3

    def test_impliedvol_american_roundtrip(self, client: TestClient):
        base = {"s": 100, "k": 100, "t": 0.5, "r": 0.05, "q": 0.02, "v": 0.25, "type": "put", "style": "american", "engine": "binomial_crr"}
        resp_price = client.get("/v1/greeks", params=base, headers={"Accept": "application/json"})
        assert resp_price.status_code == 200
        price = resp_price.json()["greeks"]["outputs"]["price"]

        iv_params = {k: v for k, v in base.items() if k != "v"}
        iv_params["price"] = price
        resp_iv = client.get("/v1/impliedvol", params=iv_params, headers={"Accept": "application/json"})
        assert resp_iv.status_code == 200
        iv = resp_iv.json()["impliedvol"]["outputs"]["implied_vol"]
        assert abs(iv - 0.25) < 1e-3  # Binomial has wider tolerance

    def test_impliedvol_xml_default(self, client: TestClient):
        resp = client.get("/v1/impliedvol?s=100&k=100&t=0.25&r=0.05&q=0&price=6.5&type=call&style=european")
        assert resp.status_code == 200
        assert "xml" in resp.headers["content-type"]
        root = ET.fromstring(resp.text)
        assert root.find("meta/service_version").text == "1.0.0"
        assert float(root.find("outputs/implied_vol").text) > 0

    def test_impliedvol_price_out_of_bounds(self, client: TestClient):
        resp = client.get(
            "/v1/impliedvol?s=100&k=100&t=0.25&r=0.05&q=0&price=0.01&type=call&style=european",
            headers={"Accept": "application/json"},
        )
        assert resp.status_code == 400
        assert resp.json()["error"]["code"] == "INVALID_INPUT"

    def test_impliedvol_t_zero_floored(self, client: TestClient):
        # Price at 20% vol with t floored to 1 day, then back out IV
        resp_price = client.get(
            "/v1/greeks?s=100&k=100&t=0&r=0.05&q=0&v=0.20&type=call&style=european",
            headers={"Accept": "application/json"},
        )
        assert resp_price.status_code == 200
        price = resp_price.json()["greeks"]["outputs"]["price"]

        resp_iv = client.get(
            f"/v1/impliedvol?s=100&k=100&t=0&r=0.05&q=0&price={price}&type=call&style=european",
            headers={"Accept": "application/json"},
        )
        assert resp_iv.status_code == 200
        iv = resp_iv.json()["impliedvol"]["outputs"]["implied_vol"]
        assert abs(iv - 0.20) < 1e-3

    def test_impliedvol_missing_param(self, client: TestClient):
        resp = client.get("/v1/impliedvol?s=100&k=100")
        assert resp.status_code == 400
        root = ET.fromstring(resp.text)
        assert root.find("code").text == "INVALID_INPUT"


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
        assert len(data["portfolio"]["legs"]) == 2
        assert data["portfolio"]["meta"]["valuation_date"] == "2026-04-20"
        agg = data["portfolio"]["aggregate"]
        assert "delta" in agg

    def test_portfolio_aggregate_math(self, client: TestClient):
        payload = {
            "legs": [
                {"id": "L1", "qty": 2, "s": 100, "k": 105, "t": 0.25, "r": 0.05, "q": 0, "v": 0.20, "type": "call", "style": "european"},
                {"id": "L2", "qty": -1, "s": 100, "k": 95, "t": 0.25, "r": 0.05, "q": 0, "v": 0.20, "type": "put", "style": "european"},
            ]
        }
        resp = client.post("/v1/portfolio/greeks", json=payload, headers={"Accept": "application/json"})
        assert resp.status_code == 200
        data = resp.json()
        legs = data["portfolio"]["legs"]
        agg = data["portfolio"]["aggregate"]
        # Aggregate should equal 2*L1 - 1*L2
        for greek in ["delta", "gamma", "vega", "theta", "rho", "charm"]:
            expected = 2 * legs[0][greek] - 1 * legs[1][greek]
            assert abs(agg[greek] - expected) < 1e-6
