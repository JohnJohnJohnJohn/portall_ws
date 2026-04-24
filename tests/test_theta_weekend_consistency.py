"""Regression tests proving calendar-day theta consistency across weekends and holidays."""

from datetime import date

import pytest

from deskpricer.pricing.engine import price_vanilla


def _price_with_theta(s, k, t, r, q, v, option_type, style, engine, valuation_date):
    return price_vanilla(
        s=s,
        k=k,
        t=t,
        r=r,
        q=q,
        v=v,
        option_type=option_type,
        style=style,
        engine=engine,
        valuation_date=valuation_date,
        calendar_name="hong_kong",
    )


class TestThetaWeekendConsistency:
    """Calendar-day theta must be invariant to weekends and holidays."""

    def test_theta_friday_equals_monday(self):
        """Theta on Friday should equal theta on Monday for the same parameters."""
        params = {
            "s": 100.0,
            "k": 100.0,
            "t": 0.25,
            "r": 0.05,
            "q": 0.0,
            "v": 0.20,
            "option_type": "call",
            "style": "european",
            "engine": "analytic",
        }
        # 2026-04-17 is Friday, 2026-04-20 is Monday
        friday = _price_with_theta(valuation_date=date(2026, 4, 17), **params)
        monday = _price_with_theta(valuation_date=date(2026, 4, 20), **params)

        # Theta should be within 1% (small differences from actual t changes only)
        assert friday.theta == pytest.approx(monday.theta, rel=0.01)
        assert friday.charm == pytest.approx(monday.charm, rel=0.01)

    def test_theta_holiday_equals_normal_weekday(self):
        """Theta on the day before a holiday should equal theta on a normal weekday."""
        params = {
            "s": 100.0,
            "k": 100.0,
            "t": 0.25,
            "r": 0.05,
            "q": 0.0,
            "v": 0.20,
            "option_type": "call",
            "style": "european",
            "engine": "analytic",
        }
        # 2026-04-28 is Tuesday (normal HK business day)
        # 2026-04-30 is Thursday (day before Labour Day holiday, May 1)
        normal = _price_with_theta(valuation_date=date(2026, 4, 28), **params)
        pre_holiday = _price_with_theta(valuation_date=date(2026, 4, 30), **params)

        assert normal.theta == pytest.approx(pre_holiday.theta, rel=0.01)
        assert normal.charm == pytest.approx(pre_holiday.charm, rel=0.01)

    def test_zero_dte_fallback(self):
        """When t <= 1/365, theta falls back to intrinsic - price and charm to 0."""
        params = {
            "s": 100.0,
            "k": 100.0,
            "t": 1.0 / 365.0,
            "r": 0.05,
            "q": 0.0,
            "v": 0.20,
            "option_type": "call",
            "style": "european",
            "engine": "analytic",
        }
        result = _price_with_theta(valuation_date=date(2026, 4, 20), **params)
        intrinsic = max(100.0 - 100.0, 0.0)
        assert result.theta == pytest.approx(intrinsic - result.price, abs=1e-10)
        assert result.charm == pytest.approx(0.0, abs=1e-10)

    def test_theta_scales_linearly_with_calendar_days(self):
        """theta * 3 should approximate the 3-day revaluation within gamma tolerance."""
        params = {
            "s": 100.0,
            "k": 100.0,
            "t": 0.25,
            "r": 0.05,
            "q": 0.0,
            "v": 0.20,
            "option_type": "call",
            "style": "european",
            "engine": "analytic",
        }
        friday = _price_with_theta(valuation_date=date(2026, 4, 17), **params)
        # Revalue with t shortened by 3/365 years (Friday -> Monday)
        monday_short_params = {**params, "t": 0.25 - 3.0 / 365.0}
        monday_short = _price_with_theta(valuation_date=date(2026, 4, 17), **monday_short_params)
        actual_3day_pnl = monday_short.price - friday.price
        assert friday.theta * 3 == pytest.approx(actual_3day_pnl, abs=5e-4)

    def test_american_theta_friday_equals_monday(self):
        """American theta on Friday should equal theta on Monday."""
        params = {
            "s": 100.0,
            "k": 100.0,
            "t": 0.25,
            "r": 0.05,
            "q": 0.0,
            "v": 0.20,
            "option_type": "put",
            "style": "american",
            "engine": "binomial_crr",
        }
        friday = _price_with_theta(valuation_date=date(2026, 4, 17), **params)
        monday = _price_with_theta(valuation_date=date(2026, 4, 20), **params)

        assert friday.theta == pytest.approx(monday.theta, rel=0.01)
