"""Tests for American options that are economically equivalent to Europeans."""

from datetime import date

import pytest
import QuantLib as ql

from deskpricer.pricing.bsm_fast import price_european_bsm
from deskpricer.pricing.conventions import ql_date_from_iso
from deskpricer.pricing.engine import price_vanilla
from deskpricer.pricing.equivalence import american_is_european_equivalent

VALUATION_DATE = date(2024, 1, 2)
PARITY_TOL = 1e-6


@pytest.fixture(autouse=True)
def _sync_eval_date():
    old_eval = ql.Settings.instance().evaluationDate
    ql.Settings.instance().evaluationDate = ql_date_from_iso(VALUATION_DATE)
    try:
        yield
    finally:
        ql.Settings.instance().evaluationDate = old_eval


class TestEquivalenceDetection:
    @pytest.mark.parametrize(
        ("option_type", "r", "q", "b", "expected"),
        [
            ("call", 0.05, 0.0, 0.0, True),
            ("call", 0.05, 0.02, 0.0, False),
            ("call", 0.05, 0.0, 0.05, False),
            ("call", 0.05, 0.02, -0.02, True),
            ("put", 0.0, 0.0, 0.0, True),
            ("put", 0.05, 0.0, 0.0, False),
            ("put", -0.01, 0.0, 0.0, False),
        ],
    )
    def test_equivalence_rules(self, option_type, r, q, b, expected):
        assert american_is_european_equivalent(option_type, r, q, b) is expected

    def test_equivalence_tolerance_boundary(self):
        assert american_is_european_equivalent("call", 0.05, 1e-9, 0.0) is True
        assert american_is_european_equivalent("call", 0.05, 1e-7, 0.0) is False
        assert american_is_european_equivalent("put", 1e-9, 0.0, 0.0) is True
        assert american_is_european_equivalent("put", 1e-7, 0.0, 0.0) is False


class TestAmericanReroutePricing:
    @pytest.mark.parametrize(
        "kwargs",
        [
            pytest.param(
                {
                    "s": 100.0,
                    "k": 100.0,
                    "t": 1.0,
                    "r": 0.05,
                    "q": 0.0,
                    "b": 0.0,
                    "v": 0.20,
                    "option_type": "call",
                },
                id="atm_call_no_div",
            ),
            pytest.param(
                {
                    "s": 100.0,
                    "k": 110.0,
                    "t": 0.5,
                    "r": 0.05,
                    "q": 0.0,
                    "b": 0.0,
                    "v": 0.25,
                    "option_type": "call",
                },
                id="otm_call_no_div",
            ),
            pytest.param(
                {
                    "s": 100.0,
                    "k": 100.0,
                    "t": 1.0,
                    "r": 0.0,
                    "q": 0.0,
                    "b": 0.0,
                    "v": 0.20,
                    "option_type": "put",
                },
                id="atm_put_zero_rate",
            ),
            pytest.param(
                {
                    "s": 80.0,
                    "k": 100.0,
                    "t": 0.5,
                    "r": 0.0,
                    "q": 0.0,
                    "b": 0.0,
                    "v": 0.25,
                    "option_type": "put",
                },
                id="itm_put_zero_rate",
            ),
        ],
    )
    def test_rerouted_american_matches_european(self, kwargs):
        common = {
            "valuation_date": VALUATION_DATE,
            "calendar_name": "null",
        }
        european = price_european_bsm(**kwargs, **common)
        american = price_vanilla(
            **kwargs,
            style="american",
            engine="binomial_crr",
            steps=500,
            **common,
        )
        for field in ("price", "delta", "gamma", "vega", "theta", "rho", "charm"):
            assert abs(getattr(american, field) - getattr(european, field)) < PARITY_TOL, field

    def test_non_rerouted_american_put_still_uses_binomial(self):
        kwargs = {
            "s": 50.0,
            "k": 50.0,
            "t": 0.4167,
            "r": 0.10,
            "q": 0.0,
            "b": 0.0,
            "v": 0.40,
            "option_type": "put",
            "valuation_date": VALUATION_DATE,
            "calendar_name": "null",
        }
        european = price_european_bsm(**kwargs)
        american = price_vanilla(
            **kwargs,
            style="american",
            engine="binomial_crr",
            steps=500,
        )
        assert american.price > european.price
        assert american.price - european.price > 0.01

    def test_non_rerouted_american_call_with_dividends(self):
        kwargs = {
            "s": 100.0,
            "k": 100.0,
            "t": 0.5,
            "r": 0.05,
            "q": 0.05,
            "b": 0.0,
            "v": 0.25,
            "option_type": "call",
            "valuation_date": VALUATION_DATE,
            "calendar_name": "null",
        }
        european = price_european_bsm(**kwargs)
        american = price_vanilla(
            **kwargs,
            style="american",
            engine="binomial_crr",
            steps=500,
        )
        assert american.price > european.price
