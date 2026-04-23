"""Generate regression baseline fixtures for realistic portfolios/strategies.

Run from repo root:
    python scripts/generate_regression_fixtures.py
"""

import asyncio
import json
from datetime import date
from pathlib import Path

from deskpricer.pricing.engine import price_vanilla
from deskpricer.schemas import PnLAttributionGETRequest
from deskpricer.services.pricing_service import run_pnl_attribution

FIXTURES_DIR = Path("tests/fixtures")


def _price_leg(leg: dict) -> dict:
    """Price a single leg and return Greeks dict."""
    import QuantLib as ql
    from deskpricer.pricing.conventions import ql_date_from_iso

    engine = leg.get("engine")
    if engine is None:
        engine = "analytic" if leg["style"] == "european" else "binomial_crr"
    val_date = date.fromisoformat(leg.get("valuation_date", "2026-04-20"))
    old_eval = ql.Settings.instance().evaluationDate
    try:
        ql.Settings.instance().evaluationDate = ql_date_from_iso(val_date)
        result = price_vanilla(
            s=leg["s"],
            k=leg["k"],
            t=leg["t"],
            r=leg["r"],
            q=leg["q"],
            v=leg["v"],
            option_type=leg["type"],
            style=leg["style"],
            engine=engine,
            valuation_date=val_date,
            steps=leg.get("steps", 400),
            bump_spot_rel=leg.get("bump_spot_rel", 0.01),
            bump_vol_abs=leg.get("bump_vol_abs", 0.001),
            bump_rate_abs=leg.get("bump_rate_abs", 0.001),
        )
    finally:
        ql.Settings.instance().evaluationDate = old_eval
    return result.model_dump()


def _build_portfolio_expected(legs: list[dict]) -> dict:
    """Compute aggregate expected Greeks from leg definitions."""
    aggregate = {
        "delta": 0.0,
        "gamma": 0.0,
        "vega": 0.0,
        "theta": 0.0,
        "rho": 0.0,
        "charm": 0.0,
    }
    legs_out = []
    for leg in legs:
        greeks = _price_leg(leg)
        row = {"id": leg["id"], "engine": leg.get("engine", "analytic" if leg["style"] == "european" else "binomial_crr")}
        row.update(greeks)
        legs_out.append(row)
        for greek in aggregate:
            aggregate[greek] += leg["qty"] * greeks[greek]
    return {"legs": legs_out, "aggregate": aggregate}


async def _build_pnl_expected(pnl_params: dict) -> dict:
    """Compute expected PnL attribution outputs."""
    params = PnLAttributionGETRequest.model_validate(pnl_params)
    _meta, _inputs, outputs = await run_pnl_attribution(params)
    return outputs


async def generate():
    FIXTURES_DIR.mkdir(parents=True, exist_ok=True)

    fixtures = [
        {
            "name": "covered_call",
            "description": "Short 1 ATM European call (the option component of a covered call).",
            "legs": [
                {
                    "id": "call",
                    "qty": -1,
                    "s": 100,
                    "k": 100,
                    "t": 0.25,
                    "r": 0.05,
                    "q": 0.0,
                    "v": 0.20,
                    "type": "call",
                    "style": "european",
                }
            ],
        },
        {
            "name": "vertical_spread",
            "description": "Long 1 95-strike call, short 1 105-strike call (bull call spread).",
            "legs": [
                {
                    "id": "long_call",
                    "qty": 1,
                    "s": 100,
                    "k": 95,
                    "t": 0.25,
                    "r": 0.05,
                    "q": 0.0,
                    "v": 0.22,
                    "type": "call",
                    "style": "european",
                },
                {
                    "id": "short_call",
                    "qty": -1,
                    "s": 100,
                    "k": 105,
                    "t": 0.25,
                    "r": 0.05,
                    "q": 0.0,
                    "v": 0.22,
                    "type": "call",
                    "style": "european",
                },
            ],
        },
        {
            "name": "calendar_spread",
            "description": "Short 1 near-term call, long 1 longer-dated call at same strike.",
            "legs": [
                {
                    "id": "short_call",
                    "qty": -1,
                    "s": 100,
                    "k": 100,
                    "t": 0.25,
                    "r": 0.05,
                    "q": 0.0,
                    "v": 0.20,
                    "type": "call",
                    "style": "european",
                },
                {
                    "id": "long_call",
                    "qty": 1,
                    "s": 100,
                    "k": 100,
                    "t": 0.5,
                    "r": 0.05,
                    "q": 0.0,
                    "v": 0.20,
                    "type": "call",
                    "style": "european",
                },
            ],
        },
        {
            "name": "risk_reversal",
            "description": "Long 1 OTM call, short 1 OTM put (delta-neutral skew play).",
            "legs": [
                {
                    "id": "long_call",
                    "qty": 1,
                    "s": 100,
                    "k": 105,
                    "t": 0.25,
                    "r": 0.05,
                    "q": 0.0,
                    "v": 0.20,
                    "type": "call",
                    "style": "european",
                },
                {
                    "id": "short_put",
                    "qty": -1,
                    "s": 100,
                    "k": 95,
                    "t": 0.25,
                    "r": 0.05,
                    "q": 0.0,
                    "v": 0.20,
                    "type": "put",
                    "style": "european",
                },
            ],
        },
        {
            "name": "iron_condor",
            "description": "Short 1 ATM call, long 1 OTM call, short 1 ATM put, long 1 OTM put.",
            "legs": [
                {
                    "id": "short_call",
                    "qty": -1,
                    "s": 100,
                    "k": 100,
                    "t": 0.25,
                    "r": 0.05,
                    "q": 0.0,
                    "v": 0.20,
                    "type": "call",
                    "style": "european",
                },
                {
                    "id": "long_call",
                    "qty": 1,
                    "s": 100,
                    "k": 110,
                    "t": 0.25,
                    "r": 0.05,
                    "q": 0.0,
                    "v": 0.20,
                    "type": "call",
                    "style": "european",
                },
                {
                    "id": "short_put",
                    "qty": -1,
                    "s": 100,
                    "k": 100,
                    "t": 0.25,
                    "r": 0.05,
                    "q": 0.0,
                    "v": 0.20,
                    "type": "put",
                    "style": "european",
                },
                {
                    "id": "long_put",
                    "qty": 1,
                    "s": 100,
                    "k": 90,
                    "t": 0.25,
                    "r": 0.05,
                    "q": 0.0,
                    "v": 0.20,
                    "type": "put",
                    "style": "european",
                },
            ],
        },
        {
            "name": "zero_dte_put",
            "description": "Long 1 ATM put with t=0 (floored to 1 day).",
            "legs": [
                {
                    "id": "put",
                    "qty": 1,
                    "s": 100,
                    "k": 100,
                    "t": 0,
                    "r": 0.05,
                    "q": 0.0,
                    "v": 0.30,
                    "type": "put",
                    "style": "european",
                }
            ],
        },
        {
            "name": "american_single_stock_put",
            "description": "Long 1 American put on a single stock (no divs).",
            "legs": [
                {
                    "id": "put",
                    "qty": 1,
                    "s": 50,
                    "k": 50,
                    "t": 0.4167,
                    "r": 0.10,
                    "q": 0.0,
                    "v": 0.40,
                    "type": "put",
                    "style": "american",
                    "engine": "binomial_crr",
                    "steps": 400,
                }
            ],
        },
    ]

    for fixture in fixtures:
        expected = _build_portfolio_expected(fixture["legs"])
        fixture["expected"] = expected
        path = FIXTURES_DIR / f"{fixture['name']}.json"
        path.write_text(json.dumps(fixture, indent=2))
        print(f"Wrote {path}")

    # PnL attribution fixture
    pnl_fixture = {
        "name": "pnl_attribution_baseline",
        "description": "Baseline PnL attribution for a single European call with spot and vol moves.",
        "inputs": {
            "s_t_minus_1": 100.0,
            "s_t": 102.0,
            "k": 105.0,
            "t_t_minus_1": 0.25,
            "t_t": 0.2466,
            "r_t_minus_1": 0.05,
            "r_t": 0.05,
            "q_t_minus_1": 0.0,
            "q_t": 0.0,
            "v_t_minus_1": 0.20,
            "v_t": 0.22,
            "type": "call",
            "style": "european",
            "qty": 10.0,
            "method": "backward",
            "cross_greeks": True,
            "valuation_date_t_minus_1": "2026-04-19",
            "valuation_date_t": "2026-04-20",
        },
    }
    pnl_expected = await _build_pnl_expected(pnl_fixture["inputs"])
    pnl_fixture["expected"] = pnl_expected
    path = FIXTURES_DIR / "pnl_attribution_baseline.json"
    path.write_text(json.dumps(pnl_fixture, indent=2))
    print(f"Wrote {path}")


if __name__ == "__main__":
    asyncio.run(generate())
