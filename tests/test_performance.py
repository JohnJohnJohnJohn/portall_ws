"""Performance tests."""

import time

from fastapi.testclient import TestClient


class TestPerformance:
    def test_1000_european_calls_under_10s(self, client: TestClient):
        """1000 sequential European calls must complete in < 10 s."""
        params = {
            "s": 100,
            "k": 100,
            "t": 0.5,
            "r": 0.05,
            "q": 0.02,
            "v": 0.20,
            "type": "call",
            "style": "european",
        }
        start = time.perf_counter()
        for _ in range(1000):
            resp = client.get("/v1/greeks", params=params)
            assert resp.status_code == 200
        elapsed = time.perf_counter() - start
        assert elapsed < 10.0, f"1000 calls took {elapsed:.2f}s"

    def test_100_leg_portfolio_under_500ms(self, client: TestClient):
        """100-leg portfolio request must complete in < 500 ms."""
        legs = []
        for i in range(100):
            legs.append({
                "id": f"L{i}",
                "qty": 1,
                "s": 100 + i,
                "k": 100,
                "t": 0.5,
                "r": 0.05,
                "q": 0.02,
                "v": 0.20,
                "type": "call",
                "style": "european",
            })
        payload = {"legs": legs}
        start = time.perf_counter()
        resp = client.post("/v1/portfolio/greeks", json=payload, headers={"Accept": "application/json"})
        elapsed = time.perf_counter() - start
        assert resp.status_code == 200
        assert elapsed < 0.5, f"100-leg portfolio took {elapsed:.3f}s"
        data = resp.json()
        assert len(data["portfolio"]["legs"]) == 100
