"""Financial regression tests with independent BSM reference implementation."""

import math
from datetime import date

from _conventions_ref import annual_business_days
from deskpricer.pricing.cross_greeks import compute_cross_greeks
from _ql_european_ref import price_european
from deskpricer.pricing.engine import price_vanilla
from deskpricer.pricing.implied_vol import compute_implied_vol

from _bsm_ref import (
    bs_call,
    bs_delta_call,
    bs_rho_call_per_point,
    bs_vega_per_point,
    sync_eval_date as _sync_eval_date,
)


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
    )


class TestEuropeanBSMReference:
    """Tests 1-5: European analytic engine vs closed-form BSM."""

    def test_atm_european_call_price_vs_bsm(self):
        # q=0.02, date=2024-01-02
        with _sync_eval_date(date(2024, 1, 2)):
            result = price_european_test(
                S=100.0, K=100.0, T=1.0, r=0.05, q=0.02, sigma=0.20, option_type="call"
            )
        expected = bs_call(100.0, 100.0, 1.0, 0.05, 0.02, 0.20)
        assert abs(result.price - expected) < 0.005

    def test_atm_european_put_price_parity(self):
        # q=0.02, date=2024-01-02
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
        # q=0.02, date=2024-01-02
        with _sync_eval_date(date(2024, 1, 2)):
            result = price_european_test(
                S=100.0, K=100.0, T=1.0, r=0.05, q=0.02, sigma=0.20, option_type="call"
            )
        expected = bs_delta_call(100.0, 100.0, 1.0, 0.05, 0.02, 0.20)
        assert abs(result.delta - expected) < 1e-4

    def test_european_call_vega_vs_bsm(self):
        # q=0.02, date=2024-01-02
        with _sync_eval_date(date(2024, 1, 2)):
            result = price_european_test(
                S=100.0, K=100.0, T=1.0, r=0.05, q=0.02, sigma=0.20, option_type="call"
            )
        expected = bs_vega_per_point(100.0, 100.0, 1.0, 0.05, 0.02, 0.20)
        assert abs(result.vega - expected) < 1e-4

    def test_european_call_rho_vs_bsm(self):
        # q=0.02, date=2024-01-02
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
                s=S,
                k=K,
                t=T,
                r=r,
                q=q,
                v=sigma,
                option_type="call",
                style="american",
                engine="binomial_crr",
                steps=1000,
                valuation_date=valuation_date,
                calendar_name="null",
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
                s=S,
                k=K,
                t=T,
                r=r,
                q=q,
                target_price=target_price,
                option_type="call",
                style="european",
                engine="analytic",
                valuation_date=valuation_date,
                calendar_name="null",
            )
        assert abs(result.implied_vol - 0.25) < 1e-4


class TestThetaCharmSign:
    """Tests 8-10: theta and charm sign conventions."""

    def test_theta_sign_long_call_negative(self):
        # Test 8: T=0.5, q=0.02, date=2024-01-02
        valuation_date = date(2024, 1, 2)
        with _sync_eval_date(valuation_date):
            result = price_vanilla(
                s=100.0,
                k=100.0,
                t=0.5,
                r=0.05,
                q=0.02,
                v=0.20,
                option_type="call",
                style="european",
                engine="analytic",
                valuation_date=valuation_date,
                calendar_name="null",
            )
        assert result.theta < -1e-6

    def test_charm_sign_otm_call_approaching_expiry(self):
        # Changed from ITM (S=100,K=80) to OTM (S=90,K=100); charm should be negative.
        valuation_date = date(2024, 1, 2)
        with _sync_eval_date(valuation_date):
            result = price_vanilla(
                s=90.0,
                k=100.0,
                t=0.1,
                r=0.05,
                q=0.02,
                v=0.20,
                option_type="call",
                style="european",
                engine="analytic",
                valuation_date=valuation_date,
                calendar_name="null",
            )
        assert result.charm < -1e-6


class TestCrossGreeks:
    """Tests 11-12: vanna and volga properties."""

    def test_vanna_sign_otm_call(self):
        # q=0.02, date=2024-01-02
        S, K, T, r, q, sigma = 90.0, 100.0, 0.5, 0.05, 0.02, 0.20
        valuation_date = date(2024, 1, 2)
        with _sync_eval_date(valuation_date):
            base = price_vanilla(
                s=S,
                k=K,
                t=T,
                r=r,
                q=q,
                v=sigma,
                option_type="call",
                style="european",
                engine="analytic",
                valuation_date=valuation_date,
                calendar_name="null",
            )
            vanna, _ = compute_cross_greeks(
                base_price=base.price,
                s=S,
                k=K,
                t=T,
                r=r,
                q=q,
                v=sigma,
                option_type="call",
                style="european",
                engine="analytic",
                valuation_date=valuation_date,
                calendar_name="null",
            )
        assert vanna > 1e-8

    def test_volga_non_negative(self):
        # Three sub-cases: ATM, OTM, deep ITM; all calls; q=0.02; date=2024-01-02.
        valuation_date = date(2024, 1, 2)
        cases = [
            (100.0, 100.0),  # ATM
            (90.0, 100.0),  # OTM
            (120.0, 100.0),  # deep ITM
        ]
        for S, K in cases:
            with _sync_eval_date(valuation_date):
                base = price_vanilla(
                    s=S,
                    k=K,
                    t=0.5,
                    r=0.05,
                    q=0.02,
                    v=0.20,
                    option_type="call",
                    style="european",
                    engine="analytic",
                    valuation_date=valuation_date,
                    calendar_name="null",
                )
                _, volga = compute_cross_greeks(
                    base_price=base.price,
                    s=S,
                    k=K,
                    t=0.5,
                    r=0.05,
                    q=0.02,
                    v=0.20,
                    option_type="call",
                    style="european",
                    engine="analytic",
                    valuation_date=valuation_date,
                    calendar_name="null",
                )
            assert volga >= -1e-8, f"volga negative for S={S}, K={K}"


class TestPnLAttributionClosure:
    """Test 13: P&L attribution closure for a defined market move."""

    def test_pnl_attribution_closure(self):
        # Self-contained computation (replaces the original service-level test).
        S0, K = 100.0, 100.0
        T0, r, q = 0.5, 0.05, 0.02
        sigma0 = 0.20
        S1 = 102.0
        sigma1 = 0.21
        T1 = 0.5 - 1.0 / 252.0
        valuation_date = date(2024, 1, 2)

        with _sync_eval_date(valuation_date):
            greeks_0 = price_vanilla(
                s=S0,
                k=K,
                t=T0,
                r=r,
                q=q,
                v=sigma0,
                option_type="call",
                style="european",
                engine="analytic",
                valuation_date=valuation_date,
                calendar_name="null",
            )
            vanna_0, volga_0 = compute_cross_greeks(
                base_price=greeks_0.price,
                s=S0,
                k=K,
                t=T0,
                r=r,
                q=q,
                v=sigma0,
                option_type="call",
                style="european",
                engine="analytic",
                valuation_date=valuation_date,
                calendar_name="null",
            )
            price_1 = price_vanilla(
                s=S1,
                k=K,
                t=T1,
                r=r,
                q=q,
                v=sigma1,
                option_type="call",
                style="european",
                engine="analytic",
                valuation_date=valuation_date,
                calendar_name="null",
            ).price

        actual_pnl = price_1 - greeks_0.price
        delta_s = S1 - S0
        delta_v_points = (sigma1 - sigma0) * 100.0
        explained_pnl = (
            greeks_0.delta * delta_s
            + 0.5 * greeks_0.gamma * (delta_s**2)
            + greeks_0.vega * delta_v_points
            + greeks_0.theta * 1.0
            + greeks_0.rho * 0.0
            + vanna_0 * delta_s * delta_v_points
            + 0.5 * volga_0 * (delta_v_points**2)
        )
        residual = actual_pnl - explained_pnl
        assert abs(actual_pnl) > 1e-4
        assert abs(residual) <= 0.02 * abs(actual_pnl)


class TestCalendarBusinessDays:
    """Test 14: calendar-aware business day counts."""

    def test_calendar_business_day_counts(self):
        # Use annual_business_days, year=2023
        hk = annual_business_days("hong_kong", 2023)
        nyse = annual_business_days("us_nyse", 2023)
        uk = annual_business_days("united_kingdom", 2023)
        assert 242 <= hk <= 250, f"HK 2023 business days = {hk}"
        assert 250 <= nyse <= 254, f"NYSE 2023 business days = {nyse}"
        assert 250 <= uk <= 255, f"UK 2023 business days = {uk}"


class TestPortfolioThetaNegative:
    def test_portfolio_theta_negative_for_long_option(self):
        # Validates that a long European call has negative theta via the
        # portfolio endpoint (aggregate theta should be negative for a long
        # ATM call).  Prior version only asserted ``qty == 1`` (Pydantic echo)
        # without actually pricing — that was a dead assertion.  This version
        # exercises the real pricing path through the worker pool.
        from deskpricer.services.pricing_service import run_portfolio
        from deskpricer.schemas import PortfolioRequest, LegInput
        import asyncio

        req = PortfolioRequest(
            legs=[
                LegInput(
                    id="leg1",
                    s=100,
                    k=100,
                    t=0.25,
                    r=0.05,
                    q=0,
                    v=0.20,
                    type="call",
                    style="european",
                    qty=1,
                ),
            ]
        )
        _, _, aggregate = asyncio.run(run_portfolio(req))
        assert aggregate["theta"] < 0
