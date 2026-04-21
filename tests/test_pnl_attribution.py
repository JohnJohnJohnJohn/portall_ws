"""Tests for GET /v1/pnl_attribution."""

import xml.etree.ElementTree as ET

import pytest
from fastapi.testclient import TestClient


class TestPnLAttribution:
    def _get(self, client: TestClient, params, json_format=False):
        headers = {"Accept": "application/json"} if json_format else {}
        return client.get("/v1/pnl_attribution", params=params, headers=headers)

    def _base_params(self, **overrides):
        defaults = {
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
            "valuation_date_t_minus_1": "2026-04-19",
            "valuation_date_t": "2026-04-20",
            "method": "backward",
        }
        defaults.update(overrides)
        return defaults

    def test_delta_pnl_only(self, client: TestClient):
        """Spot moves +2, nothing else changes. Delta PnL should dominate."""
        params = self._base_params(s_t=102)
        resp = self._get(client, params, json_format=True)
        assert resp.status_code == 200
        data = resp.json()["pnl_attribution"]

        assert data["delta_pnl"] > 0
        assert data["gamma_pnl"] >= 0
        assert data["vega_pnl"] == pytest.approx(0, abs=1e-10)
        assert data["rho_pnl"] == pytest.approx(0, abs=1e-10)
        assert abs(data["delta_pnl"]) > abs(data["gamma_pnl"])

    def test_gamma_pnl_large_move(self, client: TestClient):
        """Large spot move: without gamma, delta alone would miss actual PnL."""
        params = self._base_params(s_t=110)
        resp = self._get(client, params, json_format=True)
        assert resp.status_code == 200
        data = resp.json()["pnl_attribution"]

        delta_only = data["delta_pnl"]
        actual = data["actual_pnl"]
        assert actual > delta_only  # gamma is positive for long call

        explained = data["explained_pnl"]
        assert abs(actual - explained) < abs(actual - delta_only)

    def test_vega_pnl(self, client: TestClient):
        """Vol rises 2 points, spot unchanged. Vega PnL should be positive."""
        params = self._base_params(v_t=0.22)
        resp = self._get(client, params, json_format=True)
        assert resp.status_code == 200
        data = resp.json()["pnl_attribution"]

        assert data["vega_pnl"] > 0
        assert data["delta_pnl"] == pytest.approx(0, abs=1e-10)
        assert data["gamma_pnl"] == pytest.approx(0, abs=1e-10)
        assert abs(data["vega_pnl"]) > abs(data["theta_pnl"])

    def test_theta_pnl_one_day(self, client: TestClient):
        """One calendar day passes, all market data identical.
        Actual PnL should be approximately theta * 1 day."""
        params = self._base_params(
            t_t=0.25 - 1 / 365,
        )
        resp = self._get(client, params, json_format=True)
        assert resp.status_code == 200
        data = resp.json()["pnl_attribution"]

        assert data["delta_pnl"] == pytest.approx(0, abs=1e-10)
        assert data["gamma_pnl"] == pytest.approx(0, abs=1e-10)
        assert data["vega_pnl"] == pytest.approx(0, abs=1e-10)
        assert data["rho_pnl"] == pytest.approx(0, abs=1e-10)

        assert data["theta_pnl"] < 0
        assert data["actual_pnl"] == pytest.approx(data["theta_pnl"], abs=1e-3)
        assert data["residual_pnl"] == pytest.approx(0, abs=1e-3)

    def test_method_average_vega(self, client: TestClient):
        """Average vega should differ from backward vega when vol and spot both move."""
        base = self._base_params(s_t=102, v_t=0.22)
        backward = {**base, "method": "backward"}
        average = {**base, "method": "average"}

        resp_b = self._get(client, backward, json_format=True)
        resp_a = self._get(client, average, json_format=True)
        assert resp_b.status_code == 200
        assert resp_a.status_code == 200

        data_b = resp_b.json()["pnl_attribution"]
        data_a = resp_a.json()["pnl_attribution"]

        assert data_a["delta_pnl"] == data_b["delta_pnl"]
        assert data_a["gamma_pnl"] == data_b["gamma_pnl"]
        assert data_a["theta_pnl"] == data_b["theta_pnl"]
        assert data_a["vega_pnl"] != data_b["vega_pnl"]

    def test_qty_scaling(self, client: TestClient):
        """Qty=10 should scale all PnL buckets by 10x."""
        params_single = self._base_params(s_t=102, qty=1)
        params_ten = self._base_params(s_t=102, qty=10)

        resp_1 = self._get(client, params_single, json_format=True)
        resp_10 = self._get(client, params_ten, json_format=True)
        assert resp_1.status_code == 200
        assert resp_10.status_code == 200

        data_1 = resp_1.json()["pnl_attribution"]
        data_10 = resp_10.json()["pnl_attribution"]

        for bucket in ["actual_pnl", "delta_pnl", "gamma_pnl", "vega_pnl", "theta_pnl", "rho_pnl"]:
            assert data_10[bucket] == pytest.approx(10 * data_1[bucket], abs=1e-7)

    def test_short_position_negative_qty(self, client: TestClient):
        """Short position flips the sign of all PnL buckets."""
        params = self._base_params(s_t=102, qty=-1)
        resp = self._get(client, params, json_format=True)
        assert resp.status_code == 200
        data = resp.json()["pnl_attribution"]

        assert data["actual_pnl"] < 0
        assert data["delta_pnl"] < 0
        assert data["theta_pnl"] > 0  # short call collects time decay

    def test_xml_response(self, client: TestClient):
        """Default response should be valid XML."""
        params = self._base_params(s_t=102)
        resp = self._get(client, params, json_format=False)
        assert resp.status_code == 200
        assert resp.headers["content-type"] == "application/xml; charset=utf-8"
        root = ET.fromstring(resp.text)
        assert root.tag == "pnl_attribution"
        assert root.find("meta/method").text == "backward"
        assert root.find("delta_pnl") is not None
        assert root.find("price_t_minus_1") is not None

    def test_default_dates(self, client: TestClient):
        """Omitting valuation dates should default to today and today-1."""
        params = self._base_params()
        del params["valuation_date_t_minus_1"]
        del params["valuation_date_t"]
        resp = self._get(client, params, json_format=True)
        assert resp.status_code == 200
        meta = resp.json()["pnl_attribution"]["meta"]
        assert "valuation_date_t_minus_1" in meta
        assert "valuation_date_t" in meta

    def test_invalid_date_order(self, client: TestClient):
        """t_minus_1 after t should fail validation."""
        params = self._base_params(
            valuation_date_t_minus_1="2026-04-21",
            valuation_date_t="2026-04-20",
        )
        resp = self._get(client, params, json_format=True)
        assert resp.status_code == 400
        assert resp.json()["error"]["code"] == "INVALID_INPUT"

    def test_missing_param(self, client: TestClient):
        """Missing required param should fail validation."""
        params = {"s_t_minus_1": 100, "s_t": 102, "k": 100}
        resp = self._get(client, params, json_format=True)
        assert resp.status_code == 400
        assert resp.json()["error"]["code"] == "INVALID_INPUT"
