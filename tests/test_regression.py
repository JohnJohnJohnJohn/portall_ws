"""Regression tests against legacy VBA golden fixture.

The 50-option golden fixture is provided separately by the user.
When available, place it in tests/fixtures/golden_fixture.csv and
uncomment the test below.
"""

import csv
from pathlib import Path

import pytest
from fastapi.testclient import TestClient


GOLDEN_PATH = Path(__file__).parent / "fixtures" / "golden_fixture.csv"


@pytest.mark.skipif(not GOLDEN_PATH.exists(), reason="Golden fixture not provided")
def test_golden_fixture_vs_legacy_vba(client: TestClient):
    """Compare Python Greeks against legacy VBA on 50-option fixture.
    Tolerance: 1e-4 absolute, 1e-3 relative.
    """
    with open(GOLDEN_PATH, newline="") as f:
        reader = csv.DictReader(f)
        for row in reader:
            resp = client.get(
                "/v1/greeks",
                params={
                    "s": row["s"],
                    "k": row["k"],
                    "t": row["t"],
                    "r": row["r"],
                    "q": row["q"],
                    "v": row["v"],
                    "type": row["type"],
                    "style": row["style"],
                },
                headers={"Accept": "application/json"},
            )
            assert resp.status_code == 200
            out = resp.json()["greeks"]["outputs"]
            for greek in ["price", "delta", "gamma", "vega", "theta", "rho"]:
                py_val = float(out[greek])
                vba_val = float(row[greek])
                abs_tol = 1e-4
                rel_tol = 1e-3
                assert abs(py_val - vba_val) <= max(abs_tol, rel_tol * abs(vba_val)), (
                    f"Mismatch on {greek} for {row}: Python={py_val}, VBA={vba_val}"
                )
