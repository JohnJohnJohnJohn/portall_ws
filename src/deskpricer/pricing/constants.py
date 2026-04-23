"""Named constants for deskpricer financial conventions.

See CONVENTIONS.md Section 4 for definitions and rationale.
"""

MIN_T_YEARS: float = 1.0 / 365.0
"""CONVENTIONS.md §4: Minimum expiry floor = 1 calendar day; prevents QuantLib singularity at t → 0."""

MAX_EXPIRY_T_DISCREPANCY: float = 0.20
"""CONVENTIONS.md §4: 20% round-trip discrepancy warning threshold in expiry_from_t."""

DEFAULT_STEPS: int = 500
"""CONVENTIONS.md §4: Default binomial tree steps; balances accuracy vs. speed."""

DEFAULT_BUMP_SPOT_REL: float = 0.01
"""CONVENTIONS.md §4: 1% relative spot bump; large enough to avoid noise, small enough for accurate FD."""

DEFAULT_BUMP_VOL_ABS: float = 0.001
"""CONVENTIONS.md §4: 0.1 vol-point absolute vol bump (0.1% decimal)."""

DEFAULT_BUMP_RATE_ABS: float = 0.001
"""CONVENTIONS.md §4: 0.1 rate-point absolute rate bump (0.1% decimal)."""

ANNUAL_TRADING_DAYS: int = 252
"""CONVENTIONS.md §4: NYSE/HK proxy for business days per calendar year; numerator in per-calendar-day theta rate conversion."""

CALENDAR_DAYS_PER_YEAR: int = 365
"""CONVENTIONS.md §4: ACT/365 denominator; matches the day count convention throughout."""

SPOT_DIVERGENCE_THRESHOLD: float = 0.05
"""CONVENTIONS.md §4: 5% relative spot divergence beyond which portfolio aggregate Greeks are a coarse approximation."""

IV_SOLVER_VOL_LO: float = 1e-6
"""CONVENTIONS.md §4: Effective-zero lower vol bound; avoids log(0) in BSM."""

IV_SOLVER_VOL_HI: float = 5.0
"""CONVENTIONS.md §4: 500% upper vol bound; caps solver search space."""

IV_SOLVER_VOL_LO_RETRY: float = 1e-8
"""CONVENTIONS.md §4: Extended lower bound for root-not-bracketed retry."""

IV_SOLVER_VOL_HI_RETRY: float = 10.0
"""CONVENTIONS.md §4: Extended 1000% upper bound for retry pass."""

IV_SEED_VOL: float = 0.20
"""CONVENTIONS.md §4: 20% seed vol; typical ATM equity starting point."""

IV_TOLERANCE_MULTIPLIER_ANALYTIC: int = 10
"""CONVENTIONS.md §4: Analytic engine residual tolerance multiplier; tight because closed-form has no discretisation noise."""

IV_TOLERANCE_MULTIPLIER_TREE: int = 50
"""CONVENTIONS.md §4: Tree engine residual tolerance multiplier; relaxed for binomial discretisation error."""

IV_HIGH_VOL_WARNING_THRESHOLD: float = 2.0
"""CONVENTIONS.md §4: 200% IV warning threshold for data quality."""

VOL_BUMP_CAP_FACTOR: float = 0.5
"""CONVENTIONS.md §4: Cap at 50% of current vol ensures the down-bumped vol is always positive."""
