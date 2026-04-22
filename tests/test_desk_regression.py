"""Desk-realistic regression tests using committed JSON fixtures.

To regenerate baselines after intentional model changes:
    python scripts/generate_regression_fixtures.py
"""

import json
from pathlib import Path

import pytest
from fastapi.testclient import TestClient

FIXTURES_DIR = Path(__file__).parent / "fixtures"


def _load_fixture(name: str) -> dict:
    path = FIXTURES_DIR / f"{name}.json"
    return json.loads(path.read_text())


class TestPortfolioFixtures:
    @pytest.mark.parametrize(
        "fixture_name",
        [
            "covered_call",
            "vertical_spread",
            "calendar_spread",
            "risk_reversal",
            "iron_condor",
            "zero_dte_put",
            "american_single_stock_put",
        ],
    )
    def test_fixture_portfolio(self, client: TestClient, fixture_name: str):
        fixture = _load_fixture(fixture_name)
        payload = {
            "valuation_date": "2026-04-20",
            "legs": fixture["legs"],
        }
        resp = client.post(
            "/v1/portfolio/greeks", json=payload, headers={"Accept": "application/json"}
        )
        assert resp.status_code == 200
        data = resp.json()["portfolio"]
        expected = fixture["expected"]

        for idx, leg in enumerate(data["legs"]):
            exp_leg = expected["legs"][idx]
            assert leg["id"] == exp_leg["id"]
            assert leg["engine"] == exp_leg["engine"]
            for greek in ["price", "delta", "gamma", "vega", "theta", "rho", "charm"]:
                assert leg[greek] == pytest.approx(exp_leg[greek], abs=1e-6)

        for greek in ["delta", "gamma", "vega", "theta", "rho", "charm"]:
            assert data["aggregate"][greek] == pytest.approx(expected["aggregate"][greek], abs=1e-6)


class TestPnLAttributionFixture:
    def test_pnl_attribution_baseline(self, client: TestClient):
        fixture = _load_fixture("pnl_attribution_baseline")
        resp = client.get(
            "/v1/pnl_attribution",
            params=fixture["inputs"],
            headers={"Accept": "application/json"},
        )
        assert resp.status_code == 200
        outputs = resp.json()["pnl_attribution"]["outputs"]
        expected = fixture["expected"]

        for key in expected:
            assert outputs[key] == pytest.approx(expected[key], abs=1e-5)
