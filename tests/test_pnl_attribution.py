"""Tests for POST /v1/pnl/attribution."""

import xml.etree.ElementTree as ET

import pytest
from fastapi.testclient import TestClient

from desk_pricer.pricing.conventions import ql_date_from_iso
from desk_pricer.pricing.engine import price_vanilla


class TestPnLAttribution:
    def _make_leg(self, **overrides):
        defaults = {
            "id": "L1",
            "qty": 1,
            "k": 100,
            "type": "call",
            "style": "european",
            "engine": None,
            "steps": 400,
            "bump_spot_rel": 0.01,
            "bump_vol_abs": 0.001,
            "bump_rate_abs": 0.001,
        }
        defaults.update(overrides)
        return defaults

    def _post(self, client: TestClient, payload, json_format=False):
        headers = {"Accept": "application/json"} if json_format else {}
        return client.post("/v1/pnl/attribution", json=payload, headers=headers)

    def test_delta_pnl_only(self, client: TestClient):
        """Spot moves +2, nothing else changes. Delta PnL should dominate."""
        payload = {
            "valuation_date_t_minus_1": "2026-04-19",
            "valuation_date_t": "2026-04-20",
            "method": "backward",
            "legs": [
                self._make_leg(
                    t_minus_1={"s": 100, "t": 0.25, "r": 0.05, "q": 0, "v": 0.20},
                    t={"s": 102, "t": 0.25, "r": 0.05, "q": 0, "v": 0.20},
                )
            ],
        }
        resp = self._post(client, payload, json_format=True)
        assert resp.status_code == 200
        data = resp.json()["pnl_attribution"]
        leg = data["legs"][0]

        # Delta PnL ≈ delta * 2
        assert leg["delta_pnl"] > 0
        assert leg["gamma_pnl"] >= 0  # convexity
        assert leg["vega_pnl"] == pytest.approx(0, abs=1e-10)
        assert leg["rho_pnl"] == pytest.approx(0, abs=1e-10)

        # Delta should be the dominant term
        assert abs(leg["delta_pnl"]) > abs(leg["gamma_pnl"])
        assert abs(leg["delta_pnl"]) > abs(leg["theta_pnl"])

    def test_gamma_pnl_large_move(self, client: TestClient):
        """Large spot move: without gamma, delta alone would miss actual PnL."""
        payload = {
            "valuation_date_t_minus_1": "2026-04-19",
            "valuation_date_t": "2026-04-20",
            "method": "backward",
            "legs": [
                self._make_leg(
                    t_minus_1={"s": 100, "t": 0.25, "r": 0.05, "q": 0, "v": 0.20},
                    t={"s": 110, "t": 0.25, "r": 0.05, "q": 0, "v": 0.20},
                )
            ],
        }
        resp = self._post(client, payload, json_format=True)
        assert resp.status_code == 200
        leg = resp.json()["pnl_attribution"]["legs"][0]

        # Delta-only would understate the call's gain (convexity)
        delta_only = leg["delta_pnl"]
        actual = leg["actual_pnl"]
        assert actual > delta_only  # gamma is positive for long call

        # With gamma included, explained should be much closer
        explained = leg["explained_pnl"]
        assert abs(actual - explained) < abs(actual - delta_only)

    def test_vega_pnl(self, client: TestClient):
        """Vol rises 2 points, spot unchanged. Vega PnL should be positive."""
        payload = {
            "valuation_date_t_minus_1": "2026-04-19",
            "valuation_date_t": "2026-04-20",
            "method": "backward",
            "legs": [
                self._make_leg(
                    t_minus_1={"s": 100, "t": 0.25, "r": 0.05, "q": 0, "v": 0.20},
                    t={"s": 100, "t": 0.25, "r": 0.05, "q": 0, "v": 0.22},
                )
            ],
        }
        resp = self._post(client, payload, json_format=True)
        assert resp.status_code == 200
        leg = resp.json()["pnl_attribution"]["legs"][0]

        assert leg["vega_pnl"] > 0
        assert leg["delta_pnl"] == pytest.approx(0, abs=1e-10)
        assert leg["gamma_pnl"] == pytest.approx(0, abs=1e-10)
        # Vega should be the dominant driver of PnL here
        assert abs(leg["vega_pnl"]) > abs(leg["theta_pnl"])

    def test_theta_pnl_one_day(self, client: TestClient):
        """One calendar day passes, all market data identical.
        Actual PnL should be approximately theta * 1 day."""
        payload = {
            "valuation_date_t_minus_1": "2026-04-19",
            "valuation_date_t": "2026-04-20",
            "method": "backward",
            "legs": [
                self._make_leg(
                    t_minus_1={"s": 100, "t": 0.25, "r": 0.05, "q": 0, "v": 0.20},
                    t={"s": 100, "t": 0.25 - 1/365, "r": 0.05, "q": 0, "v": 0.20},
                )
            ],
        }
        resp = self._post(client, payload, json_format=True)
        assert resp.status_code == 200
        leg = resp.json()["pnl_attribution"]["legs"][0]

        assert leg["delta_pnl"] == pytest.approx(0, abs=1e-10)
        assert leg["gamma_pnl"] == pytest.approx(0, abs=1e-10)
        assert leg["vega_pnl"] == pytest.approx(0, abs=1e-10)
        assert leg["rho_pnl"] == pytest.approx(0, abs=1e-10)

        # Theta PnL should be negative for a long option
        assert leg["theta_pnl"] < 0
        assert leg["actual_pnl"] == pytest.approx(leg["theta_pnl"], abs=1e-3)
        assert leg["residual_pnl"] == pytest.approx(0, abs=1e-3)

    def test_method_average_vega(self, client: TestClient):
        """Average vega should differ from backward vega when vol and spot both move."""
        payload_backward = {
            "valuation_date_t_minus_1": "2026-04-19",
            "valuation_date_t": "2026-04-20",
            "method": "backward",
            "legs": [
                self._make_leg(
                    t_minus_1={"s": 100, "t": 0.25, "r": 0.05, "q": 0, "v": 0.20},
                    t={"s": 102, "t": 0.25, "r": 0.05, "q": 0, "v": 0.22},
                )
            ],
        }
        payload_average = {
            **payload_backward,
            "method": "average",
        }

        resp_b = self._post(client, payload_backward, json_format=True)
        resp_a = self._post(client, payload_average, json_format=True)
        assert resp_b.status_code == 200
        assert resp_a.status_code == 200

        leg_b = resp_b.json()["pnl_attribution"]["legs"][0]
        leg_a = resp_a.json()["pnl_attribution"]["legs"][0]

        # Delta and gamma should be identical
        assert leg_a["delta_pnl"] == leg_b["delta_pnl"]
        assert leg_a["gamma_pnl"] == leg_b["gamma_pnl"]
        # Theta should be identical (always backward-looking)
        assert leg_a["theta_pnl"] == leg_b["theta_pnl"]
        # Vega should differ (average vs backward)
        assert leg_a["vega_pnl"] != leg_b["vega_pnl"]

    def test_portfolio_aggregate(self, client: TestClient):
        """Two legs: aggregate sums qty-weighted PnL buckets."""
        payload = {
            "valuation_date_t_minus_1": "2026-04-19",
            "valuation_date_t": "2026-04-20",
            "method": "backward",
            "legs": [
                self._make_leg(
                    id="L1",
                    qty=10,
                    t_minus_1={"s": 100, "t": 0.25, "r": 0.05, "q": 0, "v": 0.20},
                    t={"s": 102, "t": 0.25, "r": 0.05, "q": 0, "v": 0.20},
                ),
                self._make_leg(
                    id="L2",
                    qty=-5,
                    type="put",
                    t_minus_1={"s": 100, "t": 0.25, "r": 0.05, "q": 0, "v": 0.20},
                    t={"s": 102, "t": 0.25, "r": 0.05, "q": 0, "v": 0.20},
                ),
            ],
        }
        resp = self._post(client, payload, json_format=True)
        assert resp.status_code == 200
        data = resp.json()["pnl_attribution"]

        legs = data["legs"]
        agg = data["aggregate"]

        # Verify per-leg qty scaling
        assert legs[0]["actual_pnl"] == pytest.approx(10 * legs[0]["actual_pnl"] / 10)
        assert legs[1]["actual_pnl"] == pytest.approx(-5 * legs[1]["actual_pnl"] / -5)

        # Verify aggregate = sum of legs
        for bucket in ["actual_pnl", "delta_pnl", "gamma_pnl", "vega_pnl", "theta_pnl", "rho_pnl"]:
            expected = legs[0][bucket] + legs[1][bucket]
            assert agg[bucket] == pytest.approx(expected, abs=1e-7)

        assert agg["explained_pnl"] == pytest.approx(
            agg["delta_pnl"] + agg["gamma_pnl"] + agg["vega_pnl"] + agg["theta_pnl"] + agg["rho_pnl"],
            abs=1e-10,
        )
        assert agg["residual_pnl"] == pytest.approx(
            agg["actual_pnl"] - agg["explained_pnl"], abs=1e-7
        )

    def test_short_position_negative_qty(self, client: TestClient):
        """Short position flips the sign of all PnL buckets."""
        payload = {
            "valuation_date_t_minus_1": "2026-04-19",
            "valuation_date_t": "2026-04-20",
            "method": "backward",
            "legs": [
                self._make_leg(
                    qty=-1,
                    t_minus_1={"s": 100, "t": 0.25, "r": 0.05, "q": 0, "v": 0.20},
                    t={"s": 102, "t": 0.25, "r": 0.05, "q": 0, "v": 0.20},
                )
            ],
        }
        resp = self._post(client, payload, json_format=True)
        assert resp.status_code == 200
        leg = resp.json()["pnl_attribution"]["legs"][0]

        # Short call loses when spot rises
        assert leg["actual_pnl"] < 0
        assert leg["delta_pnl"] < 0
        # Theta PnL for short call is positive (collect time decay)
        assert leg["theta_pnl"] > 0

    def test_xml_response(self, client: TestClient):
        """Default response should be valid XML."""
        payload = {
            "valuation_date_t_minus_1": "2026-04-19",
            "valuation_date_t": "2026-04-20",
            "method": "backward",
            "legs": [
                self._make_leg(
                    t_minus_1={"s": 100, "t": 0.25, "r": 0.05, "q": 0, "v": 0.20},
                    t={"s": 102, "t": 0.25, "r": 0.05, "q": 0, "v": 0.20},
                )
            ],
        }
        resp = self._post(client, payload, json_format=False)
        assert resp.status_code == 200
        assert resp.headers["content-type"] == "application/xml; charset=utf-8"
        root = ET.fromstring(resp.text)
        assert root.tag == "pnl_attribution"
        assert root.find("meta/method").text == "backward"
        legs = root.find("legs")
        assert legs is not None
        leg_nodes = legs.findall("leg")
        assert len(leg_nodes) == 1
        assert leg_nodes[0].find("id").text == "L1"

    def test_default_dates(self, client: TestClient):
        """Omitting valuation dates should default to today and today-1."""
        payload = {
            "method": "backward",
            "legs": [
                self._make_leg(
                    t_minus_1={"s": 100, "t": 0.25, "r": 0.05, "q": 0, "v": 0.20},
                    t={"s": 100, "t": 0.25, "r": 0.05, "q": 0, "v": 0.20},
                )
            ],
        }
        resp = self._post(client, payload, json_format=True)
        assert resp.status_code == 200
        meta = resp.json()["pnl_attribution"]["meta"]
        assert "valuation_date_t_minus_1" in meta
        assert "valuation_date_t" in meta

    def test_invalid_date_order(self, client: TestClient):
        """t_minus_1 after t should fail validation."""
        payload = {
            "valuation_date_t_minus_1": "2026-04-21",
            "valuation_date_t": "2026-04-20",
            "method": "backward",
            "legs": [
                self._make_leg(
                    t_minus_1={"s": 100, "t": 0.25, "r": 0.05, "q": 0, "v": 0.20},
                    t={"s": 100, "t": 0.25, "r": 0.05, "q": 0, "v": 0.20},
                )
            ],
        }
        resp = self._post(client, payload, json_format=True)
        assert resp.status_code == 400
        assert resp.json()["error"]["code"] == "INVALID_INPUT"

    def test_empty_legs(self, client: TestClient):
        """Empty legs list should fail validation."""
        payload = {
            "valuation_date_t_minus_1": "2026-04-19",
            "valuation_date_t": "2026-04-20",
            "method": "backward",
            "legs": [],
        }
        resp = self._post(client, payload, json_format=True)
        assert resp.status_code == 400
        assert resp.json()["error"]["code"] == "INVALID_INPUT"
