"""Financial regression tests with independent BSM reference implementation."""

import asyncio
import math
from contextlib import contextmanager
from datetime import date

import pytest
import QuantLib as ql
from scipy.stats import norm

from deskpricer.pricing.conventions import (
    count_business_days,
    get_calendar,
    ql_date_from_iso,
)
from deskpricer.pricing.cross_greeks import compute_cross_greeks
from deskpricer.pricing.engine import price_vanilla
from deskpricer.pricing.implied_vol import compute_implied_vol
from deskpricer.schemas import PnLAttributionGETRequest
from deskpricer.services.pricing_service import run_pnl_attribution


def _d1(S, K, T, r, q, sigma):
    return (math.log(S / K) + (r - q + sigma**2 / 2) * T) / (sigma * math.sqrt(T))


def _d2(S, K, T, r, q, sigma):
    return _d1(S, K, T, r, q, sigma) - sigma * math.sqrt(T)


def bs_call(S, K, T, r, q, sigma):
    d1 = _d1(S, K, T, r, q, sigma)
    d2 = _d2(S, K, T, r, q, sigma)
    return S * math.exp(-q * T) * norm.cdf(d1) - K * math.exp(-r * T) * norm.cdf(d2)


def bs_put(S, K, T, r, q, sigma):
    return bs_call(S, K, T, r, q, sigma) - S * math.exp(-q * T) + K * math.exp(-r * T)


def bs_delta_call(S, K, T, r, q, sigma):
    return math.exp(-q * T) * norm.cdf(_d1(S, K, T, r, q, sigma))


def bs_delta_put(S, K, T, r, q, sigma):
    return math.exp(-q * T) * (norm.cdf(_d1(S, K, T, r, q, sigma)) - 1)


def bs_gamma(S, K, T, r, q, sigma):
    d1 = _d1(S, K, T, r, q, sigma)
    return math.exp(-q * T) * norm.pdf(d1) / (S * sigma * math.sqrt(T))


def bs_vega_per_volpoint(S, K, T, r, q, sigma):
    d1 = _d1(S, K, T, r, q, sigma)
    return S * math.exp(-q * T) * norm.pdf(d1) * math.sqrt(T) / 100


def bs_rho_call_per_ratepoint(S, K, T, r, q, sigma):
    d2 = _d2(S, K, T, r, q, sigma)
    return K * T * math.exp(-r * T) * norm.cdf(d2) / 100


def bs_rho_put_per_ratepoint(S, K, T, r, q, sigma):
    d2 = _d2(S, K, T, r, q, sigma)
    return -K * T * math.exp(-r * T) * norm.cdf(-d2) / 100


@contextmanager
def _sync_eval_date(valuation_date):
    old_eval = ql.Settings.instance().evaluationDate
    ql.Settings.instance().evaluationDate = ql_date_from_iso(valuation_date)
    try:
        yield
    finally:
        ql.Settings.instance().evaluationDate = old_eval


class TestEuropeanBSMReference:
    _S = 100.0
    _K = 100.0
    _T = 1.0
    _r = 0.05
    _q = 0.0
    _sigma = 0.20
    _valuation_date = date(2025, 6, 16)

    def test_atm_european_call_price(self):
        with _sync_eval_date(self._valuation_date):
            result = price_vanilla(
                s=self._S, k=self._K, t=self._T, r=self._r, q=self._q, v=self._sigma,
                option_type="call", style="european", engine="analytic",
                valuation_date=self._valuation_date, calendar_name="null",
            )
        expected = bs_call(self._S, self._K, self._T, self._r, self._q, self._sigma)
        assert abs(result.price - expected) < 1e-3

    def test_atm_european_put_price_put_call_parity(self):
        with _sync_eval_date(self._valuation_date):
            call_price = price_vanilla(
                s=self._S, k=self._K, t=self._T, r=self._r, q=self._q, v=self._sigma,
                option_type="call", style="european", engine="analytic",
                valuation_date=self._valuation_date, calendar_name="null",
            ).price
            put_price = price_vanilla(
                s=self._S, k=self._K, t=self._T, r=self._r, q=self._q, v=self._sigma,
                option_type="put", style="european", engine="analytic",
                valuation_date=self._valuation_date, calendar_name="null",
            ).price
        expected_put = call_price - self._S + self._K * math.exp(-self._r * self._T)
        assert abs(put_price - expected_put) < 1e-4

    def test_european_call_delta(self):
        with _sync_eval_date(self._valuation_date):
            result = price_vanilla(
                s=self._S, k=self._K, t=self._T, r=self._r, q=self._q, v=self._sigma,
                option_type="call", style="european", engine="analytic",
                valuation_date=self._valuation_date, calendar_name="null",
            )
        expected = bs_delta_call(self._S, self._K, self._T, self._r, self._q, self._sigma)
        assert abs(result.delta - expected) < 5e-4

    def test_european_call_vega(self):
        with _sync_eval_date(self._valuation_date):
            result = price_vanilla(
                s=self._S, k=self._K, t=self._T, r=self._r, q=self._q, v=self._sigma,
                option_type="call", style="european", engine="analytic",
                valuation_date=self._valuation_date, calendar_name="null",
            )
        expected = bs_vega_per_volpoint(self._S, self._K, self._T, self._r, self._q, self._sigma)
        assert abs(result.vega - expected) < 5e-4

    def test_european_call_rho(self):
        with _sync_eval_date(self._valuation_date):
            result = price_vanilla(
                s=self._S, k=self._K, t=self._T, r=self._r, q=self._q, v=self._sigma,
                option_type="call", style="european", engine="analytic",
                valuation_date=self._valuation_date, calendar_name="null",
            )
        expected = bs_rho_call_per_ratepoint(self._S, self._K, self._T, self._r, self._q, self._sigma)
        assert abs(result.rho - expected) < 5e-4


class TestAmericanEuropeanConsistency:
    def test_american_call_no_dividend_equals_european(self):
        S, K, T, r, q, sigma = 100.0, 100.0, 1.0, 0.05, 0.0, 0.20
        valuation_date = date(2025, 6, 16)
        with _sync_eval_date(valuation_date):
            european = price_vanilla(
                s=S, k=K, t=T, r=r, q=q, v=sigma,
                option_type="call", style="european", engine="analytic",
                valuation_date=valuation_date, calendar_name="null",
            )
            american = price_vanilla(
                s=S, k=K, t=T, r=r, q=q, v=sigma,
                option_type="call", style="american", engine="binomial_crr", steps=500,
                valuation_date=valuation_date, calendar_name="null",
            )
        assert abs(american.price - european.price) < 0.05


class TestImpliedVol:
    def test_implied_vol_roundtrip(self):
        S, K, T, r, q, sigma = 100.0, 100.0, 0.5, 0.05, 0.0, 0.25
        valuation_date = date(2025, 6, 16)
        with _sync_eval_date(valuation_date):
            price_at_025 = price_vanilla(
                s=S, k=K, t=T, r=r, q=q, v=sigma,
                option_type="call", style="european", engine="analytic",
                valuation_date=valuation_date, calendar_name="null",
            ).price
            result = compute_implied_vol(
                s=S, k=K, t=T, r=r, q=q, target_price=price_at_025,
                option_type="call", style="european", engine="analytic",
                valuation_date=valuation_date, calendar_name="null",
            )
        assert abs(result.implied_vol - 0.25) < 1e-4


class TestThetaCharmSign:
    def test_theta_sign_long_call_pnl_convention(self):
        valuation_date = date(2025, 6, 16)
        with _sync_eval_date(valuation_date):
            result = price_vanilla(
                s=100.0, k=100.0, t=0.25, r=0.05, q=0.0, v=0.20,
                option_type="call", style="european", engine="analytic",
                valuation_date=valuation_date, calendar_name="null",
                theta_convention="pnl",
            )
        assert result.theta < -1e-6

    def test_charm_sign_itm_call_approaching_expiry_pnl(self):
        valuation_date = date(2025, 6, 16)
        with _sync_eval_date(valuation_date):
            result = price_vanilla(
                s=100.0, k=80.0, t=7.0 / 365.0, r=0.05, q=0.0, v=0.20,
                option_type="call", style="european", engine="analytic",
                valuation_date=valuation_date, calendar_name="null",
                theta_convention="pnl",
            )
        assert result.charm >= -1e-6


class TestCrossGreeks:
    def test_vanna_sign_otm_call_positive(self):
        S, K, T, r, q, sigma = 100.0, 110.0, 0.5, 0.05, 0.0, 0.20
        valuation_date = date(2025, 6, 16)
        with _sync_eval_date(valuation_date):
            base = price_vanilla(
                s=S, k=K, t=T, r=r, q=q, v=sigma,
                option_type="call", style="european", engine="analytic",
                valuation_date=valuation_date, calendar_name="null",
            )
            vanna, _ = compute_cross_greeks(
                base_price=base.price, s=S, k=K, t=T, r=r, q=q, v=sigma,
                option_type="call", style="european", engine="analytic",
                valuation_date=valuation_date, calendar_name="null",
            )
        assert vanna > 1e-6

    @pytest.mark.parametrize(
        "k, option_type",
        [
            (100.0, "call"),
            (110.0, "call"),
            (90.0, "put"),
        ],
    )
    def test_volga_non_negative_vanilla(self, k, option_type):
        S, T, r, q, sigma = 100.0, 0.5, 0.05, 0.0, 0.20
        valuation_date = date(2025, 6, 16)
        with _sync_eval_date(valuation_date):
            base = price_vanilla(
                s=S, k=k, t=T, r=r, q=q, v=sigma,
                option_type=option_type, style="european", engine="analytic",
                valuation_date=valuation_date, calendar_name="null",
            )
            _, volga = compute_cross_greeks(
                base_price=base.price, s=S, k=k, t=T, r=r, q=q, v=sigma,
                option_type=option_type, style="european", engine="analytic",
                valuation_date=valuation_date, calendar_name="null",
            )
        assert volga >= -1e-8


class TestPnLAttributionClosure:
    @pytest.mark.parametrize("theta_convention", ["pnl", "decay"])
    def test_pnl_attribution_closure_european(self, theta_convention):
        params = PnLAttributionGETRequest(
            s_t_minus_1=100.0,
            s_t=102.0,
            k=100.0,
            t_t_minus_1=0.25,
            t_t=0.25 - 1.0 / 365.0,
            r_t_minus_1=0.05,
            r_t=0.05,
            q_t_minus_1=0.0,
            q_t=0.0,
            v_t_minus_1=0.20,
            v_t=0.21,
            type="call",
            style="european",
            valuation_date_t_minus_1=date(2025, 6, 16),
            valuation_date_t=date(2025, 6, 17),
            method="backward",
            cross_greeks=True,
            theta_time_unit="business_day",
            theta_convention=theta_convention,
            calendar="null",
        )
        meta, inputs, outputs = asyncio.run(run_pnl_attribution(params))
        actual_pnl = outputs["actual_pnl"]
        residual_pnl = outputs["residual_pnl"]
        assert abs(actual_pnl) > 1e-4
        assert abs(residual_pnl) <= 0.02 * abs(actual_pnl)
        assert outputs["theta_pnl"] < 0


class TestCalendarBusinessDays:
    @pytest.mark.parametrize(
        "calendar_name, lo, hi",
        [
            ("hong_kong", 240, 252),
            ("us_nyse", 248, 256),
            ("united_kingdom", 248, 258),
        ],
    )
    def test_calendar_business_day_counts(self, calendar_name, lo, hi):
        start = ql_date_from_iso(date(2024, 1, 1))
        end = ql_date_from_iso(date(2025, 1, 1))
        calendar = get_calendar(calendar_name)
        count = count_business_days(start, end, calendar)
        assert lo <= count <= hi


class TestPortfolioThetaConventionConsistency:
    def test_mixed_theta_convention_rejected(self):
        from pydantic import ValidationError
        from deskpricer.schemas import PortfolioRequest, LegInput
        with pytest.raises(ValidationError) as exc_info:
            PortfolioRequest(legs=[
                LegInput(
                    id="leg1", s=100, k=100, t=0.25, r=0.05, q=0, v=0.20,
                    type="call", style="european", theta_convention="pnl", qty=1,
                ),
                LegInput(
                    id="leg2", s=100, k=100, t=0.25, r=0.05, q=0, v=0.20,
                    type="call", style="european", theta_convention="decay", qty=1,
                ),
            ])
        assert "All legs in a portfolio must share the same theta_convention" in str(exc_info.value)


class TestEuropeanGoldenCrossValidation:
    def test_european_golden_values_match_bsm_null_calendar(self):
        import sys
        sys.path.insert(0, "tests")
        from test_financial_golden import _GOLDEN, _PARAMS
        for key in _GOLDEN:
            if not key.startswith("european_"):
                continue
            p = _PARAMS[key]
            if p["type"] == "call":
                bs = bs_call(p["s"], p["k"], p["t"], p["r"], p["q"], p["v"])
            else:
                bs = bs_put(p["s"], p["k"], p["t"], p["r"], p["q"], p["v"])
            with _sync_eval_date(date.fromisoformat(p["valuation_date"])):
                engine = price_vanilla(
                    s=p["s"], k=p["k"], t=p["t"], r=p["r"], q=p["q"], v=p["v"],
                    option_type=p["type"], style="european", engine="analytic",
                    valuation_date=date.fromisoformat(p["valuation_date"]),
                    calendar_name="null",
                )
            disc = abs(engine.price - bs)
            assert disc < 1e-3, f"{key} engine={engine.price} BSM={bs} disc={disc}"
