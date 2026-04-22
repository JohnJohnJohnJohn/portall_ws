"""QuantLib runtime helpers."""

import asyncio
from contextlib import asynccontextmanager
from datetime import date

import QuantLib as ql

from deskpricer.pricing.conventions import ql_date_from_iso

_QL_LOCK = asyncio.Lock()


@asynccontextmanager
async def with_evaluation_date(valuation_date: date):
    """Acquire the QuantLib lock, set the evaluation date, and restore it on exit."""
    async with _QL_LOCK:
        old_eval = ql.Settings.instance().evaluationDate
        try:
            ql.Settings.instance().evaluationDate = ql_date_from_iso(valuation_date)
            yield
        finally:
            ql.Settings.instance().evaluationDate = old_eval
