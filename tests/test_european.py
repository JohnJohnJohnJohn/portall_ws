"""Direct unit tests for the European pricing engine."""

from datetime import date

import QuantLib as ql

from deskpricer.pricing.european import price_european


class TestEuropeanCharmThreadSafety:
    def test_charm_does_not_mutate_global_evaluation_date(self):
        """price_european must leave ql.Settings.instance().evaluationDate unchanged."""
        original = ql.Settings.instance().evaluationDate
        # Short-dated option (5 business days) forces the charm branch
        result = price_european(
            s=100.0,
            k=105.0,
            t=5 / 252.0,
            r=0.05,
            q=0.02,
            v=0.20,
            option_type="call",
            valuation_date=date(2026, 4, 20),
        )
        assert result.charm != 0.0
        assert ql.Settings.instance().evaluationDate == original

    def test_charm_near_max_date_does_not_crash(self):
        """Charm fallback near the QuantLib max date boundary should not crash."""
        original = ql.Settings.instance().evaluationDate
        result = price_european(
            s=100.0,
            k=100.0,
            t=1 / 365.0,
            r=0.05,
            q=0.0,
            v=0.20,
            option_type="call",
            valuation_date=date(2199, 12, 30),
        )
        # Expiry = max date, so expiry > one_day_forward is False → charm = 0.0
        assert result.charm == 0.0
        assert ql.Settings.instance().evaluationDate == original

    def test_next_business_day_failure_raises_invalid_input(self, monkeypatch):
        """If next_business_day raises, InvalidInputError is propagated."""
        import pytest

        import deskpricer.pricing.european as eu

        def _boom(*args, **kwargs):
            raise RuntimeError("simulated max date overflow")

        monkeypatch.setattr(eu, "next_business_day", _boom)
        with pytest.raises(eu.InvalidInputError):
            price_european(
                s=100.0,
                k=100.0,
                t=0.25,
                r=0.05,
                q=0.0,
                v=0.20,
                option_type="call",
                valuation_date=date(2026, 4, 20),
            )
