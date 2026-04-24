"""Financial regression tests with independent BSM reference implementation."""

import math
import sys
from contextlib import contextmanager
from datetime import date

import pytest
import QuantLib as ql
from scipy.stats import norm

from deskpricer.pricing.conventions import (
    annual_business_days,
    ql_date_from_iso,
)
from deskpricer.pricing.cross_greeks import compute_cross_greeks
from deskpricer.pricing.european import price_european
from deskpricer.pricing.engine import price_vanilla
from deskpricer.pricing.implied_vol import compute_implied_vol


def bs_d1(S, K, T, r, q, sigma):
    return (math.log(S / K) + (r - q + sigma**2 / 2) * T) / (sigma * math.sqrt(T))


def bs_d2(S, K, T, r, q, sigma):
    return bs_d1(S, K, T, r, q, sigma) - sigma * math.sqrt(T)


def bs_call(S, K, T, r, q, sigma):
    d1 = bs_d1(S, K, T, r, q, sigma)
    d2 = bs_d2(S, K, T, r, q, sigma)
    return S * math.exp(-q * T) * norm.cdf(d1) - K * math.exp(-r * T) * norm.cdf(d2)


def bs_put(S, K, T, r, q, sigma):
    d1 = bs_d1(S, K, T, r, q, sigma)
    d2 = bs_d2(S, K, T, r, q, sigma)
    return K * math.exp(-r * T) * norm.cdf(-d2) - S * math.exp(-q * T) * norm.cdf(-d1)


def bs_delta_call(S, K, T, r, q, sigma):
    return math.exp(-q * T) * norm.cdf(bs_d1(S, K, T, r, q, sigma))


def bs_vega_raw(S, K, T, r, q, sigma):
    d1 = bs_d1(S, K, T, r, q, sigma)
    return S * math.exp(-q * T) * norm.pdf(d1) * math.sqrt(T)


def bs_vega_per_point(S, K, T, r, q, sigma):
    return bs_vega_raw(S, K, T, r, q, sigma) / 100


def bs_rho_call_raw(S, K, T, r, q, sigma):
    d2 = bs_d2(S, K, T, r, q, sigma)
    return K * T * math.exp(-r * T) * norm.cdf(d2)


def bs_rho_call_per_point(S, K, T, r, q, sigma):
    return bs_rho_call_raw(S, K, T, r, q, sigma) / 100


def price_european_test(S, K, T, r, q, sigma, option_type, calendar_name="null"):
    return price_european(
        s=S,
        k=K,
        t=T,
        r=r,
        q=q,
        v=sigma,
        option_type=option_type,
        valuation_date=date(2024, 1, 2),
        calendar_name=calendar_name,
        theta_convention="pnl",
    )


@contextmanager
def _sync_eval_date(valuation_date):
    old_eval = ql.Settings.instance().evaluationDate
    ql.Settings.instance().evaluationDate = ql_date_from_iso(valuation_date)
    try:
        yield
    finally:
        ql.Settings.instance().evaluationDate = old_eval


class TestEuropeanBSMReference:
    """Tests 1-5: European analytic engine vs closed-form BSM."""

    def test_atm_european_call_price_vs_bsm(self):
        # Updated per FIX_INSTRUCTIONS.md Section 3 Test 1: q=0.02, date=2024-01-02
        with _sync_eval_date(date(2024, 1, 2)):
            result = price_european_test(
                S=100.0, K=100.0, T=1.0, r=0.05, q=0.02, sigma=0.20, option_type="call"
            )
        expected = bs_call(100.0, 100.0, 1.0, 0.05, 0.02, 0.20)
        assert abs(result.price - expected) < 0.005

    def test_atm_european_put_price_parity(self):
        # Updated per FIX_INSTRUCTIONS.md Section 3 Test 2: q=0.02, date=2024-01-02
        with _sync_eval_date(date(2024, 1, 2)):
            call_result = price_european_test(
                S=100.0, K=100.0, T=1.0, r=0.05, q=0.02, sigma=0.20, option_type="call"
            )
            put_result = price_european_test(
                S=100.0, K=100.0, T=1.0, r=0.05, q=0.02, sigma=0.20, option_type="put"
            )
        expected_diff = 100.0 * math.exp(-0.02 * 1.0) - 100.0 * math.exp(-0.05 * 1.0)
        assert abs(call_result.price - put_result.price - expected_diff) < 0.005

    def test_european_call_delta_vs_bsm(self):
        # Updated per FIX_INSTRUCTIONS.md Section 3 Test 3: q=0.02, date=2024-01-02
        with _sync_eval_date(date(2024, 1, 2)):
            result = price_european_test(
                S=100.0, K=100.0, T=1.0, r=0.05, q=0.02, sigma=0.20, option_type="call"
            )
        expected = bs_delta_call(100.0, 100.0, 1.0, 0.05, 0.02, 0.20)
        assert abs(result.delta - expected) < 1e-4

    def test_european_call_vega_vs_bsm(self):
        # Updated per FIX_INSTRUCTIONS.md Section 3 Test 4: q=0.02, date=2024-01-02
        with _sync_eval_date(date(2024, 1, 2)):
            result = price_european_test(
                S=100.0, K=100.0, T=1.0, r=0.05, q=0.02, sigma=0.20, option_type="call"
            )
        expected = bs_vega_per_point(100.0, 100.0, 1.0, 0.05, 0.02, 0.20)
        assert abs(result.vega - expected) < 1e-4

    def test_european_call_rho_vs_bsm(self):
        # Updated per FIX_INSTRUCTIONS.md Section 3 Test 5: q=0.02, date=2024-01-02
        with _sync_eval_date(date(2024, 1, 2)):
            result = price_european_test(
                S=100.0, K=100.0, T=1.0, r=0.05, q=0.02, sigma=0.20, option_type="call"
            )
        expected = bs_rho_call_per_point(100.0, 100.0, 1.0, 0.05, 0.02, 0.20)
        assert abs(result.rho - expected) < 1e-3


class TestAmericanEuropeanConsistency:
    """Test 6: American call on non-dividend stock equals European."""

    def test_american_call_no_dividend_equals_european(self):
        S, K, T, r, q, sigma = 100.0, 100.0, 1.0, 0.05, 0.0, 0.20
        valuation_date = date(2024, 1, 2)
        with _sync_eval_date(valuation_date):
            european = price_european_test(S, K, T, r, q, sigma, option_type="call")
            american = price_vanilla(
                s=S, k=K, t=T, r=r, q=q, v=sigma,
                option_type="call", style="american", engine="binomial_crr", steps=1000,
                valuation_date=valuation_date, calendar_name="null",
            )
        assert abs(american.price - european.price) < 0.02


class TestImpliedVol:
    """Test 7: IV round-trip."""

    def test_implied_vol_round_trip(self):
        S, K, T, r, q, sigma = 100.0, 100.0, 1.0, 0.05, 0.02, 0.25
        valuation_date = date(2024, 1, 2)
        target_price = bs_call(S, K, T, r, q, sigma)
        with _sync_eval_date(valuation_date):
            result = compute_implied_vol(
                s=S, k=K, t=T, r=r, q=q, target_price=target_price,
                option_type="call", style="european", engine="analytic",
                valuation_date=valuation_date, calendar_name="null",
            )
        assert abs(result.implied_vol - 0.25) < 1e-4


class TestThetaCharmSign:
    """Tests 8-10: theta and charm sign conventions."""

    def test_theta_sign_long_call_pnl_convention(self):
        # Test 8: T=0.5, q=0.02, date=2024-01-02
        valuation_date = date(2024, 1, 2)
        with _sync_eval_date(valuation_date):
            result = price_vanilla(
                s=100.0, k=100.0, t=0.5, r=0.05, q=0.02, v=0.20,
                option_type="call", style="european", engine="analytic",
                valuation_date=valuation_date, calendar_name="null",
                theta_convention="pnl",
            )
        assert result.theta < -1e-6

    def test_theta_sign_decay_convention_is_positive(self):
        # Test 9: missing from original; added per FIX_INSTRUCTIONS.md Section 3
        valuation_date = date(2024, 1, 2)
        with _sync_eval_date(valuation_date):
            result = price_vanilla(
                s=100.0, k=100.0, t=0.5, r=0.05, q=0.02, v=0.20,
                option_type="call", style="european", engine="analytic",
                valuation_date=valuation_date, calendar_name="null",
                theta_convention="decay",
            )
        assert result.theta > 1e-6

    def test_charm_sign_otm_call_approaching_expiry(self):
        # Test 10: Updated per FIX_INSTRUCTIONS.md Section 3.
        # Changed from ITM (S=100,K=80) to OTM (S=90,K=100); charm should be negative.
        valuation_date = date(2024, 1, 2)
        with _sync_eval_date(valuation_date):
            result = price_vanilla(
                s=90.0, k=100.0, t=0.1, r=0.05, q=0.02, v=0.20,
                option_type="call", style="european", engine="analytic",
                valuation_date=valuation_date, calendar_name="null",
                theta_convention="pnl",
            )
        assert result.charm < -1e-6


class TestCrossGreeks:
    """Tests 11-12: vanna and volga properties."""

    def test_vanna_sign_otm_call(self):
        # Test 11: Updated per FIX_INSTRUCTIONS.md Section 3: q=0.02, date=2024-01-02
        S, K, T, r, q, sigma = 90.0, 100.0, 0.5, 0.05, 0.02, 0.20
        valuation_date = date(2024, 1, 2)
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
        assert vanna > 1e-8

    def test_volga_non_negative(self):
        # Test 12: Updated per FIX_INSTRUCTIONS.md Section 3.
        # Three sub-cases: ATM, OTM, deep ITM; all calls; q=0.02; date=2024-01-02.
        valuation_date = date(2024, 1, 2)
        cases = [
            (100.0, 100.0),   # ATM
            (90.0, 100.0),    # OTM
            (120.0, 100.0),   # deep ITM
        ]
        for S, K in cases:
            with _sync_eval_date(valuation_date):
                base = price_vanilla(
                    s=S, k=K, t=0.5, r=0.05, q=0.02, v=0.20,
                    option_type="call", style="european", engine="analytic",
                    valuation_date=valuation_date, calendar_name="null",
                )
                _, volga = compute_cross_greeks(
                    base_price=base.price, s=S, k=K, t=0.5, r=0.05, q=0.02, v=0.20,
                    option_type="call", style="european", engine="analytic",
                    valuation_date=valuation_date, calendar_name="null",
                )
            assert volga >= -1e-8, f"volga negative for S={S}, K={K}"


class TestPnLAttributionClosure:
    """Test 13: P&L attribution closure for a defined market move."""

    def test_pnl_attribution_closure(self):
        # Replaced original service-level test with self-contained computation
        # per FIX_INSTRUCTIONS.md Section 3 Test 13.
        S0, K = 100.0, 100.0
        T0, r, q = 0.5, 0.05, 0.02
        sigma0 = 0.20
        S1 = 102.0
        sigma1 = 0.21
        T1 = 0.5 - 1.0 / 252.0
        valuation_date = date(2024, 1, 2)

        with _sync_eval_date(valuation_date):
            greeks_0 = price_vanilla(
                s=S0, k=K, t=T0, r=r, q=q, v=sigma0,
                option_type="call", style="european", engine="analytic",
                valuation_date=valuation_date, calendar_name="null",
            )
            vanna_0, volga_0 = compute_cross_greeks(
                base_price=greeks_0.price, s=S0, k=K, t=T0, r=r, q=q, v=sigma0,
                option_type="call", style="european", engine="analytic",
                valuation_date=valuation_date, calendar_name="null",
            )
            price_1 = price_vanilla(
                s=S1, k=K, t=T1, r=r, q=q, v=sigma1,
                option_type="call", style="european", engine="analytic",
                valuation_date=valuation_date, calendar_name="null",
            ).price

        actual_pnl = price_1 - greeks_0.price
        delta_s = S1 - S0
        delta_v_points = (sigma1 - sigma0) * 100.0
        delta_s_pct = delta_s / S0 * 100.0
        explained_pnl = (
            greeks_0.delta * delta_s
            + 0.5 * greeks_0.gamma * (delta_s**2)
            + greeks_0.vega * delta_v_points
            + greeks_0.theta * 1.0
            + greeks_0.rho * 0.0
            + vanna_0 * delta_s_pct * delta_v_points
            + 0.5 * volga_0 * (delta_v_points**2)
        )
        residual = actual_pnl - explained_pnl
        assert abs(actual_pnl) > 1e-4
        assert abs(residual) <= 0.02 * abs(actual_pnl)


class TestCalendarBusinessDays:
    """Test 14: calendar-aware business day counts."""

    def test_calendar_business_day_counts(self):
        # Updated per FIX_INSTRUCTIONS.md Section 3 Test 14: use annual_business_days, year=2023
        hk = annual_business_days("hong_kong", 2023)
        nyse = annual_business_days("us_nyse", 2023)
        uk = annual_business_days("united_kingdom", 2023)
        assert 242 <= hk <= 250, f"HK 2023 business days = {hk}"
        assert 250 <= nyse <= 254, f"NYSE 2023 business days = {nyse}"
        assert 250 <= uk <= 255, f"UK 2023 business days = {uk}"


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
