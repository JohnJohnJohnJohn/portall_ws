"""Process-pool worker entrypoints for isolated QuantLib pricing."""

from datetime import date
from typing import Any

import QuantLib as ql

from deskpricer.pricing.conventions import ql_date_from_iso


def _set_evaluation_date(valuation_date: date) -> None:
    ql.Settings.instance().evaluationDate = ql_date_from_iso(valuation_date)


def execute_task(task: str, valuation_date_iso: str, payload: dict[str, Any]) -> Any:
    """Run a pricing task in a worker process with an isolated evaluation date."""
    valuation_date = date.fromisoformat(valuation_date_iso)
    _set_evaluation_date(valuation_date)

    if task == "price_vanilla":
        from deskpricer.pricing.engine import price_vanilla

        kwargs = dict(payload)
        kwargs["valuation_date"] = valuation_date
        return price_vanilla(**kwargs).model_dump()

    if task == "portfolio_legs":
        from deskpricer.pricing.engine import price_vanilla

        rows: list[dict[str, Any]] = []
        for leg in payload["legs"]:
            leg_kwargs = dict(leg)
            leg_kwargs["valuation_date"] = valuation_date
            rows.append(price_vanilla(**leg_kwargs).model_dump())
        return rows

    if task == "compute_implied_vol":
        from deskpricer.pricing.implied_vol import compute_implied_vol

        kwargs = dict(payload)
        kwargs["valuation_date"] = valuation_date
        return compute_implied_vol(**kwargs).model_dump()

    if task == "compute_cross_greeks":
        from deskpricer.pricing.cross_greeks import compute_cross_greeks

        kwargs = dict(payload)
        kwargs["valuation_date"] = valuation_date
        return compute_cross_greeks(**kwargs)

    raise ValueError(f"Unknown worker task: {task}")
