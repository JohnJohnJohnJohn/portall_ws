"""Parity tests: pure-Python BSM fast path vs QuantLib European engine."""

from datetime import date

import pytest
import QuantLib as ql

from deskpricer.pricing.bsm_fast import price_european_bsm
from deskpricer.pricing.conventions import ql_date_from_iso
from deskpricer.pricing.european import price_european

PARITY_TOL = 1e-6

_CASES = [
    pytest.param(
        {
            "s": 100.0,
            "k": 100.0,
            "t": 1.0,
            "r": 0.05,
            "q": 0.02,
            "v": 0.20,
            "option_type": "call",
            "b": 0.0,
            "calendar_name": "null",
        },
        id="atm_call_1y",
    ),
    pytest.param(
        {
            "s": 100.0,
            "k": 100.0,
            "t": 1.0,
            "r": 0.05,
            "q": 0.02,
            "v": 0.20,
            "option_type": "put",
            "b": 0.0,
            "calendar_name": "null",
        },
        id="atm_put_1y",
    ),
    pytest.param(
        {
            "s": 42.0,
            "k": 40.0,
            "t": 0.5,
            "r": 0.10,
            "q": 0.0,
            "v": 0.20,
            "option_type": "call",
            "b": 0.0,
            "calendar_name": "null",
        },
        id="hull_call",
    ),
    pytest.param(
        {
            "s": 100.0,
            "k": 110.0,
            "t": 30 / 365,
            "r": 0.05,
            "q": 0.0,
            "v": 0.20,
            "option_type": "call",
            "b": 0.0,
            "calendar_name": "hong_kong",
        },
        id="otm_call_30dte_hk",
    ),
    pytest.param(
        {
            "s": 100.0,
            "k": 90.0,
            "t": 90 / 365,
            "r": 0.05,
            "q": 0.0,
            "v": 0.20,
            "option_type": "put",
            "b": 0.0,
            "calendar_name": "hong_kong",
        },
        id="itm_put_90dte_hk",
    ),
    pytest.param(
        {
            "s": 100.0,
            "k": 100.0,
            "t": 0.25,
            "r": 0.05,
            "q": 0.02,
            "v": 0.20,
            "option_type": "call",
            "b": 0.05,
            "calendar_name": "null",
        },
        id="call_with_borrow",
    ),
    pytest.param(
        {
            "s": 100.0,
            "k": 100.0,
            "t": 1 / 365,
            "r": 0.05,
            "q": 0.0,
            "v": 0.20,
            "option_type": "call",
            "b": 0.0,
            "calendar_name": "null",
        },
        id="one_dte_call",
    ),
    pytest.param(
        {
            "s": 50.0,
            "k": 50.0,
            "t": 1 / 365,
            "r": 0.05,
            "q": 0.0,
            "v": 0.40,
            "option_type": "put",
            "b": 0.0,
            "calendar_name": "null",
        },
        id="one_dte_put",
    ),
]


VALUATION_DATE = date(2024, 1, 2)


@pytest.fixture(autouse=True)
def sync_eval_date():
    old_eval = ql.Settings.instance().evaluationDate
    ql.Settings.instance().evaluationDate = ql_date_from_iso(VALUATION_DATE)
    try:
        yield VALUATION_DATE
    finally:
        ql.Settings.instance().evaluationDate = old_eval


@pytest.mark.parametrize("params", _CASES)
def test_bsm_fast_matches_quantlib(params, sync_eval_date):
    valuation_date = sync_eval_date
    ql_result = price_european(valuation_date=valuation_date, **params)
    fast_result = price_european_bsm(valuation_date=valuation_date, **params)
    for field in ("price", "delta", "gamma", "vega", "theta", "rho", "charm"):
        assert abs(getattr(fast_result, field) - getattr(ql_result, field)) < PARITY_TOL, (
            f"{params.get('option_type')} {field}: "
            f"fast={getattr(fast_result, field)} ql={getattr(ql_result, field)}"
        )
