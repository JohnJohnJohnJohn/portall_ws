"""Process-pool worker integration tests."""

import asyncio
from datetime import date

from deskpricer.schemas import GreeksRequest
from deskpricer.services import pricing_service
from deskpricer.worker import execute_task


class TestWorkerExecuteTask:
    def test_price_vanilla_in_worker(self):
        payload = {
            "s": 100.0,
            "k": 100.0,
            "t": 0.25,
            "r": 0.05,
            "q": 0.0,
            "b": 0.0,
            "v": 0.20,
            "option_type": "call",
            "style": "european",
            "engine": "analytic",
            "steps": 500,
            "calendar_name": "null",
        }
        result = execute_task("price_vanilla", "2026-04-20", payload)
        assert result["price"] > 0
        assert 0 < result["delta"] < 1


class TestPricingServiceUsesWorkerPool:
    def test_run_greeks_via_service(self):
        async def _run():
            params = GreeksRequest(
                s=100.0,
                k=100.0,
                t=0.25,
                r=0.05,
                q=0.0,
                v=0.20,
                type="call",
                style="european",
                valuation_date=date(2026, 4, 20),
                calendar="null",
            )
            return await pricing_service.run_greeks(params)

        meta, inputs, outputs = asyncio.run(_run())
        assert meta["engine"] == "analytic"
        assert outputs["price"] > 0
        assert inputs["style"] == "european"

    def test_concurrent_greeks_requests(self):
        async def _run():
            params = GreeksRequest(
                s=100.0,
                k=100.0,
                t=0.25,
                r=0.05,
                q=0.0,
                v=0.20,
                type="call",
                style="european",
                valuation_date=date(2026, 4, 20),
                calendar="null",
            )

            async def _one():
                return await pricing_service.run_greeks(params)

            return await asyncio.gather(*(_one() for _ in range(4)))

        results = asyncio.run(_run())
        prices = [item[2]["price"] for item in results]
        assert len(set(prices)) == 1
