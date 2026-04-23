"""API contract tests: XML/JSON toggling, error codes, schema validation."""

import datetime
import math
import xml.etree.ElementTree as ET

import pytest
import QuantLib as ql
from fastapi.testclient import TestClient

from deskpricer import __version__ as SERVICE_VERSION


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
        assert root.find("service").text == SERVICE_VERSION
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
        assert root.find("meta/service_version").text == SERVICE_VERSION
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
        assert resp.status_code == 422
        root = ET.fromstring(resp.text)
        assert root.find("code").text == "INVALID_INPUT"
        assert root.find("field") is not None

    def test_greeks_validation_error_formatting(self, client: TestClient):
        """Validation errors should be concise, not full Pydantic tracebacks."""
        resp = client.get(
            "/v1/greeks?s=bad&k=100&t=0.5&r=0.05&q=0&v=0.20&type=call&style=european",
            headers={"Accept": "application/json"},
        )
        assert resp.status_code == 422
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
        assert resp.status_code == 422
        # ET.fromstring will raise ParseError if XML contains illegal chars
        root = ET.fromstring(resp.text)
        assert root.find("code").text == "INVALID_INPUT"

    def test_xml_sanitizer_strips_control_chars(self):
        """Unit test for _sanitize_for_xml with actual control characters."""
        from deskpricer.responses import _sanitize_for_xml

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
        assert resp.status_code == 422
        root = ET.fromstring(resp.text)
        assert root.find("code").text == "INVALID_INPUT"
        assert root.find("field").text == "v"

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
        resp_call = client.get(
            "/v1/greeks", params={**base, "type": "call"}, headers={"Accept": "application/json"}
        )
        resp_put = client.get(
            "/v1/greeks", params={**base, "type": "put"}, headers={"Accept": "application/json"}
        )
        assert resp_call.status_code == 200
        assert resp_put.status_code == 200
        c = resp_call.json()["greeks"]["outputs"]["price"]
        p = resp_put.json()["greeks"]["outputs"]["price"]
        # C - P = S*exp(-qT) - K*exp(-rT) using actual T from trading-day expiry
        lhs = c - p
        today = datetime.date.today()
        ql_today = ql.Date(today.day, today.month, today.year)
        from deskpricer.pricing.conventions import default_day_count, expiry_from_t, get_calendar

        expiry = expiry_from_t(ql_today, 0.5, get_calendar())
        t_actual = default_day_count().yearFraction(ql_today, expiry)
        rhs = 100 * math.exp(-0.02 * t_actual) - 100 * math.exp(-0.05 * t_actual)
        assert abs(lhs - rhs) < 1e-6

    def test_greeks_decay_convention_flips_charm_sign(self, client: TestClient):
        """When theta_convention='decay', charm sign is flipped like theta."""
        base = {
            "s": 100,
            "k": 100,
            "t": 0.25,
            "r": 0.05,
            "q": 0,
            "v": 0.20,
            "type": "call",
            "style": "european",
        }
        resp_pnl = client.get("/v1/greeks", params=base, headers={"Accept": "application/json"})
        resp_decay = client.get(
            "/v1/greeks",
            params={**base, "theta_convention": "decay"},
            headers={"Accept": "application/json"},
        )
        assert resp_pnl.status_code == 200
        assert resp_decay.status_code == 200
        pnl = resp_pnl.json()["greeks"]["outputs"]
        decay = resp_decay.json()["greeks"]["outputs"]
        assert decay["theta"] == pytest.approx(-pnl["theta"], abs=1e-10)
        assert decay["charm"] == pytest.approx(-pnl["charm"], abs=1e-10)


class TestImpliedVol:
    def test_impliedvol_european_roundtrip(self, client: TestClient):
        """Price at known vol → IV should recover vol within tolerance."""
        base = {
            "s": 100,
            "k": 100,
            "t": 0.5,
            "r": 0.05,
            "q": 0.02,
            "v": 0.20,
            "type": "call",
            "style": "european",
        }
        resp_price = client.get("/v1/greeks", params=base, headers={"Accept": "application/json"})
        assert resp_price.status_code == 200
        price = resp_price.json()["greeks"]["outputs"]["price"]

        iv_params = {k: v for k, v in base.items() if k != "v"}
        iv_params["price"] = price
        resp_iv = client.get(
            "/v1/impliedvol", params=iv_params, headers={"Accept": "application/json"}
        )
        assert resp_iv.status_code == 200
        data = resp_iv.json()["impliedvol"]
        assert data["meta"]["engine"] == "analytic"
        iv = data["outputs"]["implied_vol"]
        assert abs(iv - 0.20) < 1e-4
        npv_check = data["outputs"]["npv_at_iv"]
        assert abs(npv_check - price) < 1e-3

    def test_impliedvol_american_roundtrip(self, client: TestClient):
        base = {
            "s": 100,
            "k": 100,
            "t": 0.5,
            "r": 0.05,
            "q": 0.02,
            "v": 0.25,
            "type": "put",
            "style": "american",
            "engine": "binomial_crr",
        }
        resp_price = client.get("/v1/greeks", params=base, headers={"Accept": "application/json"})
        assert resp_price.status_code == 200
        price = resp_price.json()["greeks"]["outputs"]["price"]

        iv_params = {k: v for k, v in base.items() if k != "v"}
        iv_params["price"] = price
        resp_iv = client.get(
            "/v1/impliedvol", params=iv_params, headers={"Accept": "application/json"}
        )
        assert resp_iv.status_code == 200
        iv = resp_iv.json()["impliedvol"]["outputs"]["implied_vol"]
        assert abs(iv - 0.25) < 1e-3  # Binomial has wider tolerance

    def test_impliedvol_xml_default(self, client: TestClient):
        resp = client.get(
            "/v1/impliedvol?s=100&k=100&t=0.25&r=0.05&q=0&price=6.5&type=call&style=european"
        )
        assert resp.status_code == 200
        assert "xml" in resp.headers["content-type"]
        root = ET.fromstring(resp.text)
        assert root.find("meta/service_version").text == SERVICE_VERSION
        assert float(root.find("outputs/implied_vol").text) > 0

    def test_impliedvol_price_out_of_bounds(self, client: TestClient):
        resp = client.get(
            "/v1/impliedvol?s=100&k=100&t=0.25&r=0.05&q=0&price=0.01&type=call&style=european",
            headers={"Accept": "application/json"},
        )
        assert resp.status_code == 400
        data = resp.json()["error"]
        assert data["code"] == "INVALID_INPUT"
        assert data["field"] == "price"

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

    def test_impliedvol_unsupported_american_analytic(self, client: TestClient):
        resp = client.get(
            "/v1/impliedvol?s=100&k=100&t=0.25&r=0.05&q=0&price=6.5&type=call&style=american&engine=analytic",
            headers={"Accept": "application/json"},
        )
        assert resp.status_code == 422
        data = resp.json()["error"]
        assert data["code"] == "UNSUPPORTED_COMBINATION"

    def test_impliedvol_missing_param(self, client: TestClient):
        resp = client.get("/v1/impliedvol?s=100&k=100")
        assert resp.status_code == 422
        root = ET.fromstring(resp.text)
        assert root.find("code").text == "INVALID_INPUT"
        assert root.find("field") is not None

    def test_impliedvol_retries_on_root_not_bracketed(self, client: TestClient, caplog):
        """On 'root not bracketed', solver retries with [1e-8, 10.0] before failing."""
        import logging

        import QuantLib as ql
        import deskpricer.pricing.implied_vol as iv_mod

        calls = []

        def _fake_implied_vol(self, target, process, accuracy, max_iter, min_vol, max_vol):
            calls.append((min_vol, max_vol))
            if min_vol == 1e-6:
                raise RuntimeError("root not bracketed")
            # Return a dummy IV on the retry
            return 0.5

        def _fake_npv(self):
            return 5.0

        monkeypatch = __import__("pytest").MonkeyPatch()
        monkeypatch.setattr(ql.VanillaOption, "impliedVolatility", _fake_implied_vol)
        monkeypatch.setattr(ql.VanillaOption, "NPV", _fake_npv)
        try:
            with caplog.at_level(logging.WARNING, logger="deskpricer"):
                result = iv_mod.compute_implied_vol(
                    s=100,
                    k=100,
                    t=0.25,
                    r=0.05,
                    q=0,
                    target_price=5.0,
                    option_type="call",
                    style="european",
                    engine="analytic",
                    valuation_date=__import__("datetime").date(2026, 4, 20),
                )
            assert result.implied_vol == 0.5
            assert len(calls) == 2
            assert calls[0] == (1e-6, 5.0)
            assert calls[1] == (1e-8, 10.0)
            assert "retrying with [1e-8, 10.0]" in caplog.text
        finally:
            monkeypatch.undo()

    def test_impliedvol_fails_after_retry(self, client: TestClient):
        """If widened bounds also fail, return 400 INVALID_INPUT."""
        import QuantLib as ql
        import deskpricer.pricing.implied_vol as iv_mod

        calls = []

        def _fake_implied_vol(self, target, process, accuracy, max_iter, min_vol, max_vol):
            calls.append((min_vol, max_vol))
            raise RuntimeError("root not bracketed")

        monkeypatch = __import__("pytest").MonkeyPatch()
        monkeypatch.setattr(ql.VanillaOption, "impliedVolatility", _fake_implied_vol)
        try:
            with __import__("pytest").raises(iv_mod.InvalidInputError) as exc_info:
                iv_mod.compute_implied_vol(
                    s=100,
                    k=100,
                    t=0.25,
                    r=0.05,
                    q=0,
                    target_price=5.0,
                    option_type="call",
                    style="european",
                    engine="analytic",
                    valuation_date=__import__("datetime").date(2026, 4, 20),
                )
            assert "outside solver bounds" in str(exc_info.value)
            assert len(calls) == 2
            assert calls[0] == (1e-6, 5.0)
            assert calls[1] == (1e-8, 10.0)
        finally:
            monkeypatch.undo()

    def test_impliedvol_reprice_tolerance_failure(self, client: TestClient):
        """If solved IV does not reproduce target_price within 10*accuracy, reject."""
        import QuantLib as ql
        import deskpricer.pricing.implied_vol as iv_mod

        def _fake_implied_vol(self, target, process, accuracy, max_iter, min_vol, max_vol):
            # Return a very low vol so repriced NPV is far from target
            return 0.001

        monkeypatch = __import__("pytest").MonkeyPatch()
        monkeypatch.setattr(ql.VanillaOption, "impliedVolatility", _fake_implied_vol)
        try:
            with __import__("pytest").raises(iv_mod.InvalidInputError) as exc_info:
                iv_mod.compute_implied_vol(
                    s=100,
                    k=100,
                    t=0.25,
                    r=0.05,
                    q=0,
                    target_price=5.0,
                    option_type="call",
                    style="european",
                    engine="analytic",
                    valuation_date=__import__("datetime").date(2026, 4, 20),
                )
            assert "deviates from target" in str(exc_info.value)
        finally:
            monkeypatch.undo()

    def test_impliedvol_high_vol_warning(self, client: TestClient, caplog):
        """Solved IV > 200%% should emit a WARNING-level log entry."""
        import logging

        import deskpricer.pricing.implied_vol as iv_mod

        # Deep ITM call with very short expiry forces high IV
        with caplog.at_level(logging.WARNING, logger="deskpricer"):
            result = iv_mod.compute_implied_vol(
                s=100,
                k=200,
                t=0.01,
                r=0.05,
                q=0,
                target_price=0.5,
                option_type="call",
                style="european",
                engine="analytic",
                valuation_date=__import__("datetime").date(2026, 4, 20),
            )
        assert result.implied_vol > 2.0
        assert "exceeds 200%" in caplog.text


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
        resp = client.post(
            "/v1/portfolio/greeks", json=payload, headers={"Accept": "application/json"}
        )
        assert resp.status_code == 200
        data = resp.json()
        assert len(data["portfolio"]["legs"]) == 2
        assert data["portfolio"]["meta"]["valuation_date"] == "2026-04-20"
        for leg in data["portfolio"]["legs"]:
            assert "engine" in leg
        agg = data["portfolio"]["aggregate"]
        assert "delta" in agg

    def test_portfolio_aggregate_math(self, client: TestClient):
        payload = {
            "legs": [
                {
                    "id": "L1",
                    "qty": 2,
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
                    "qty": -1,
                    "s": 100,
                    "k": 95,
                    "t": 0.25,
                    "r": 0.05,
                    "q": 0,
                    "v": 0.20,
                    "type": "put",
                    "style": "european",
                },
            ]
        }
        resp = client.post(
            "/v1/portfolio/greeks", json=payload, headers={"Accept": "application/json"}
        )
        assert resp.status_code == 200
        data = resp.json()
        legs = data["portfolio"]["legs"]
        agg = data["portfolio"]["aggregate"]
        # Aggregate should equal 2*L1 - 1*L2 (including price)
        for greek in ["price", "delta", "gamma", "vega", "theta", "rho", "charm"]:
            expected = 2 * legs[0][greek] - 1 * legs[1][greek]
            assert abs(agg[greek] - expected) < 1e-6

    def test_portfolio_small_vol_rejected(self, client: TestClient):
        """Extremely low vol causes QuantLib to fail; pricing layer returns 400."""
        payload = {
            "legs": [
                {
                    "id": "L1",
                    "qty": 1,
                    "s": 100,
                    "k": 100,
                    "t": 0.25,
                    "r": 0.05,
                    "q": 0,
                    "v": 0.0005,
                    "type": "call",
                    "style": "american",
                },
            ]
        }
        resp = client.post(
            "/v1/portfolio/greeks", json=payload, headers={"Accept": "application/json"}
        )
        assert resp.status_code == 400
        assert resp.json()["error"]["code"] == "INVALID_INPUT"

    def test_portfolio_divergent_spot_warning(self, client: TestClient, caplog):
        """Portfolio legs with divergent spot prices (>5%) are accepted but warned."""
        import logging

        payload = {
            "legs": [
                {
                    "id": "L1",
                    "qty": 1,
                    "s": 100,
                    "k": 100,
                    "t": 0.25,
                    "r": 0.05,
                    "q": 0,
                    "v": 0.20,
                    "type": "call",
                    "style": "european",
                },
                {
                    "id": "L2",
                    "qty": 1,
                    "s": 106,
                    "k": 100,
                    "t": 0.25,
                    "r": 0.05,
                    "q": 0,
                    "v": 0.20,
                    "type": "put",
                    "style": "european",
                },
            ]
        }
        with caplog.at_level(logging.WARNING, logger="deskpricer"):
            resp = client.post(
                "/v1/portfolio/greeks", json=payload, headers={"Accept": "application/json"}
            )
        assert resp.status_code == 200
        assert "divergent spot" in caplog.text.lower()


class TestVersionJSON:
    def test_version_json(self, client: TestClient):
        resp = client.get("/v1/version", headers={"Accept": "application/json"})
        assert resp.status_code == 200
        assert resp.headers["content-type"] == "application/json"
        data = resp.json()["version"]
        assert data["service"] == SERVICE_VERSION
        assert data["quantlib"] is not None
        assert data["python"] is not None


class TestGreeksEdgeCases:
    def test_greeks_custom_bump_rate_abs(self, client: TestClient):
        resp = client.get(
            "/v1/greeks?s=100&k=100&t=0.5&r=0.05&q=0&v=0.20&type=call&style=european&bump_rate_abs=0.005",
            headers={"Accept": "application/json"},
        )
        assert resp.status_code == 200
        assert resp.json()["greeks"]["inputs"]["bump_rate_abs"] == 0.005

    def test_404_not_found(self, client: TestClient):
        resp = client.get("/v1/does_not_exist")
        assert resp.status_code == 404
        root = ET.fromstring(resp.text)
        assert root.find("code").text == "NOT_FOUND"

    def test_american_theta_near_expiry(self, client: TestClient):
        """American option with t floored to 1 day: theta ≈ intrinsic - price."""
        resp = client.get(
            "/v1/greeks?s=50&k=50&t=0&r=0.05&q=0&v=0.40&type=put&style=american&steps=100",
            headers={"Accept": "application/json"},
        )
        assert resp.status_code == 200
        data = resp.json()["greeks"]["outputs"]
        # ATM put intrinsic = 0, so theta ≈ -price (all time value decays overnight)
        assert data["theta"] < 0
        assert abs(data["theta"] + data["price"]) < 0.15

    def test_american_charm_near_expiry(self, client: TestClient):
        """American charm fallback should return 0 when <=1 day remains."""
        resp = client.get(
            "/v1/greeks?s=50&k=50&t=0&r=0.05&q=0&v=0.40&type=put&style=american&steps=100",
            headers={"Accept": "application/json"},
        )
        assert resp.status_code == 200
        assert resp.json()["greeks"]["outputs"]["charm"] == 0.0

    def test_engine_binomial_jr(self, client: TestClient):
        """American put with JR engine should price successfully."""
        resp = client.get(
            "/v1/greeks?s=100&k=100&t=0.25&r=0.05&q=0&v=0.20&type=put&style=american&engine=binomial_jr",
            headers={"Accept": "application/json"},
        )
        assert resp.status_code == 200
        data = resp.json()["greeks"]["outputs"]
        assert data["price"] > 0
        assert data["delta"] < 0  # put delta is negative

    def test_calendar_field_non_default_echoed(self, client: TestClient):
        """calendar=us_nyse should appear in inputs; default hong_kong should not."""
        resp = client.get(
            "/v1/greeks?s=100&k=100&t=0.25&r=0.05&q=0&v=0.20&type=call&style=european&calendar=us_nyse",
            headers={"Accept": "application/json"},
        )
        assert resp.status_code == 200
        inputs = resp.json()["greeks"]["inputs"]
        assert inputs.get("calendar") == "us_nyse"

    def test_calendar_default_not_echoed(self, client: TestClient):
        """Default calendar=hong_kong should not appear in inputs."""
        resp = client.get(
            "/v1/greeks?s=100&k=100&t=0.25&r=0.05&q=0&v=0.20&type=call&style=european",
            headers={"Accept": "application/json"},
        )
        assert resp.status_code == 200
        inputs = resp.json()["greeks"]["inputs"]
        assert "calendar" not in inputs

    @pytest.mark.parametrize("field", ["r", "q"])
    @pytest.mark.parametrize("value", [-1.01, 5.01])
    def test_rate_and_dividend_bounds(self, client: TestClient, field, value):
        """r and q must lie within [-1.0, 5.0] to reject nonsensical inputs."""
        params = {
            "s": 100,
            "k": 100,
            "t": 0.25,
            "r": 0.05,
            "q": 0,
            "v": 0.20,
            "type": "call",
            "style": "european",
            field: value,
        }
        resp = client.get("/v1/greeks", params=params, headers={"Accept": "application/json"})
        assert resp.status_code == 422
        assert resp.json()["error"]["code"] == "INVALID_INPUT"


class TestPortfolioEdgeCases:
    def test_portfolio_empty_rejected(self, client: TestClient):
        resp = client.post(
            "/v1/portfolio/greeks", json={"legs": []}, headers={"Accept": "application/json"}
        )
        assert resp.status_code == 422
        assert resp.json()["error"]["code"] == "INVALID_INPUT"

    def test_portfolio_duplicate_ids_rejected(self, client: TestClient):
        payload = {
            "legs": [
                {
                    "id": "L1",
                    "qty": 1,
                    "s": 100,
                    "k": 100,
                    "t": 0.25,
                    "r": 0.05,
                    "q": 0,
                    "v": 0.20,
                    "type": "call",
                    "style": "european",
                },
                {
                    "id": "L1",
                    "qty": 1,
                    "s": 100,
                    "k": 100,
                    "t": 0.25,
                    "r": 0.05,
                    "q": 0,
                    "v": 0.20,
                    "type": "call",
                    "style": "european",
                },
            ]
        }
        resp = client.post(
            "/v1/portfolio/greeks", json=payload, headers={"Accept": "application/json"}
        )
        assert resp.status_code == 422
        assert "unique" in resp.json()["error"]["message"].lower()

    def test_portfolio_xml_default(self, client: TestClient):
        payload = {
            "legs": [
                {
                    "id": "L1",
                    "qty": 1,
                    "s": 100,
                    "k": 100,
                    "t": 0.25,
                    "r": 0.05,
                    "q": 0,
                    "v": 0.20,
                    "type": "call",
                    "style": "european",
                },
            ]
        }
        resp = client.post("/v1/portfolio/greeks", json=payload)
        assert resp.status_code == 200
        assert "xml" in resp.headers["content-type"]
        root = ET.fromstring(resp.text)
        assert root.find("meta/service_version").text == SERVICE_VERSION
        assert float(root.find("legs/leg/price").text) > 0
        assert root.find("aggregate/delta") is not None


class TestDateBoundaries:
    def test_valuation_date_before_1901_rejected(self, client: TestClient):
        resp = client.get(
            "/v1/greeks?s=100&k=100&t=0.25&r=0.05&q=0&v=0.20&type=call&style=european&valuation_date=1900-01-01"
        )
        assert resp.status_code == 400
        assert "INVALID_INPUT" in resp.text

    def test_valuation_date_after_2199_rejected(self, client: TestClient):
        resp = client.get(
            "/v1/greeks?s=100&k=100&t=0.25&r=0.05&q=0&v=0.20&type=call&style=european&valuation_date=2200-01-01"
        )
        assert resp.status_code == 400
        assert "INVALID_INPUT" in resp.text

    def test_expiry_from_t_year_boundary(self):
        """expiry_from_t must correctly advance from Dec 31 into the next year."""
        import QuantLib as ql

        from deskpricer.pricing.conventions import MIN_T_YEARS, expiry_from_t

        dec_31 = ql.Date(31, 12, 2026)
        expiry = expiry_from_t(dec_31, MIN_T_YEARS, ql.NullCalendar())
        assert expiry.dayOfMonth() == 1
        assert expiry.month() == 1
        assert expiry.year() == 2027

    def test_expiry_from_t_logs_warning_on_large_discrepancy(self, caplog):
        """A 1.5-day input rounded to 2 days produces >20% discrepancy and should warn."""
        import logging

        import QuantLib as ql

        from deskpricer.pricing.conventions import expiry_from_t

        today = ql.Date(20, 4, 2026)
        t = 1.5 / 365.0  # 1.5 calendar days → rounds to 2 days = 33% error
        with caplog.at_level(logging.WARNING, logger="deskpricer"):
            expiry_from_t(today, t, ql.NullCalendar())
        assert any("discrepancy" in r.message for r in caplog.records)


class TestCatchallHandler:
    def test_catchall_500_handler(self, monkeypatch):
        """A generic Exception inside price_vanilla must hit the catchall handler and return 500."""
        from fastapi.testclient import TestClient

        import deskpricer.services.pricing_service as svc
        from deskpricer.app import create_app

        def _boom(*args, **kwargs):
            raise Exception("simulated internal explosion")

        monkeypatch.setattr(svc, "_price_vanilla", _boom)

        app = create_app()
        client = TestClient(app, raise_server_exceptions=False)

        resp = client.get(
            "/v1/greeks?s=100&k=100&t=0.25&r=0.05&q=0&v=0.20&type=call&style=european",
            headers={"Accept": "application/json"},
        )
        assert resp.status_code == 500
        data = resp.json()
        assert data["error"]["code"] == "PRICING_FAILURE"
        assert "internal error" in data["error"]["message"].lower()


class TestPortfolioQtyZero:
    def test_portfolio_qty_zero_leg(self, client: TestClient):
        """A leg with qty=0 should be priced but contribute zero to aggregate Greeks."""
        payload = {
            "legs": [
                {
                    "id": "L1",
                    "qty": 2,
                    "s": 100,
                    "k": 100,
                    "t": 0.25,
                    "r": 0.05,
                    "q": 0,
                    "v": 0.20,
                    "type": "call",
                    "style": "european",
                },
                {
                    "id": "L2",
                    "qty": 0,
                    "s": 100,
                    "k": 100,
                    "t": 0.25,
                    "r": 0.05,
                    "q": 0,
                    "v": 0.20,
                    "type": "put",
                    "style": "european",
                },
            ]
        }
        resp = client.post(
            "/v1/portfolio/greeks", json=payload, headers={"Accept": "application/json"}
        )
        assert resp.status_code == 200
        data = resp.json()
        legs = data["portfolio"]["legs"]
        agg = data["portfolio"]["aggregate"]
        for greek in ["delta", "gamma", "vega", "theta", "rho", "charm"]:
            assert abs(agg[greek] - 2 * legs[0][greek]) < 1e-6
            assert isinstance(legs[1][greek], float)
