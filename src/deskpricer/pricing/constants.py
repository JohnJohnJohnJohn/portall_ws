"""Named constants for deskpricer financial conventions.

See CONVENTIONS.md Section 4 for definitions and rationale.
"""

MIN_T_YEARS: float = 1.0 / 365.0
"""CONVENTIONS.md §4: Minimum expiry floor = 1 calendar day; prevents QuantLib singularity at t → 0."""

MAX_EXPIRY_T_DISCREPANCY: float = 0.20
"""CONVENTIONS.md §4: 20% round-trip discrepancy warning threshold in expiry_from_t."""

DEFAULT_STEPS: int = 500
"""CONVENTIONS.md §4: Default binomial tree steps; balances accuracy vs. speed.

Also the sentinel value used to detect "caller did not override steps" in
engine.py:price_vanilla — when the request arrives with steps == DEFAULT_STEPS,
the adaptive step logic is allowed to pick a more appropriate value based on
time-to-expiry.  Callers who explicitly want 500 steps can set any other value
(the adaptive path only triggers on the exact sentinel).
"""

ADAPTIVE_STEPS_TARGET: int = 200
"""Target binomial steps per year of maturity, used by the adaptive step picker.

Long-dated options need fewer steps to converge; short-dated options need
more to resolve the payoff kink near expiry.  engine.py multiplies this by
1/t (clamped to [ADAPTIVE_STEPS_MIN, ADAPTIVE_STEPS_MAX]) to pick a default
step count that's both faster and more accurate than a fixed 500.
"""

ADAPTIVE_STEPS_MIN: int = 100
"""Lower bound for adaptive step count."""

ADAPTIVE_STEPS_MAX: int = 2000
"""Upper bound for adaptive step count; also the threshold below which
Richardson extrapolation (2N steps) stays within the 5000 schema cap."""

INSUFFICIENT_STEPS_WARNING_THRESHOLD: float = 50.0
"""Minimum recommended steps per year of maturity; below this a warning is
logged because gamma/theta accuracy degrades noticeably."""

DEFAULT_BUMP_SPOT_REL: float = 0.01
"""CONVENTIONS.md §4: 1% relative spot bump; large enough to avoid noise, small enough for accurate FD."""

DEFAULT_BUMP_VOL_ABS: float = 0.001
"""CONVENTIONS.md §4: 0.1 vol-point absolute vol bump (0.1% decimal)."""

DEFAULT_BUMP_RATE_ABS: float = 0.001
"""CONVENTIONS.md §4: 0.1 rate-point absolute rate bump (0.1% decimal)."""

DEFAULT_BORROW_COST: float = 0.0
"""CONVENTIONS.md §4: Default stock borrow cost (zero = no borrow cost)."""

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

IV_LOW_VEGA_WARNING_THRESHOLD: float = 0.01
"""Vega (per 1 vol-point) at the solved IV below which the inversion is flagged
as ill-conditioned: dIV/dPrice = 1/vega, so below this threshold ~0.01 of
price noise maps to more than 1 vol-point of IV error (deep-ITM/OTM regime)."""

AMERICAN_CROSS_GREEKS_MIN_STEPS: int = 2000
"""Minimum binomial steps for trustworthy American cross-greeks.  Below this,
the second vol difference (volga) is dominated by lattice noise rather than
the option's actual vol convexity; a warning is logged."""

IV_REPRICE_RELATIVE_TOLERANCE: float = 0.001
"""CONVENTIONS.md §4: Relative tolerance (0.1% of target price) for IV reprice verification."""

VOL_BUMP_CAP_FACTOR: float = 0.5
"""CONVENTIONS.md §4: Cap at 50% of current vol ensures the down-bumped vol is always positive."""

AMERICAN_EUROPEAN_EQUIVALENCE_ABS_TOL: float = 1e-8
"""Absolute tolerance for q+b (calls) and r (puts) when deciding American→European reroute."""

IV_SOLVER_DEFAULT_ACCURACY: float = 1e-4
"""Default Brent solver accuracy for IV root finding; tighter than QuantLib's own default to minimise reprice residual."""

IV_SOLVER_MAX_ITERATIONS: int = 1000
"""Maximum Brent iterations; sufficient for all practical BSM IV searches."""

GAMMA_MIN_TICKS: int = 3
"""Number of CRR/JR lattice ticks the *fallback* gamma bump spans.

When the fine delta-style bump h_s = bump_spot_rel * S is smaller than a
small multiple of the CRR lattice tick size, the three spot reprices used
in the second-difference gamma formula can all land on the same locally-
linear segment of the piecewise-linear binomial surface, collapsing
gamma to numerical noise.  american.py computes both a fine gamma and a
wider gamma (h_s_wide = max(h_s, GAMMA_MIN_TICKS * crr_tick)); if the fine
gamma has collapsed (below GAMMA_NOISE_FLOOR and discrepant from the wide
gamma), the wide gamma is reported instead.  See american.py for details.
"""

GAMMA_NOISE_FLOOR: float = 1e-4
"""Gamma values below this threshold are treated as numerical noise.

Used by the runtime collapse detector in american.py to decide whether to
fall back to the wider-bump gamma estimate.  Tuned to be well below any
realistic equity-option gamma (typical ATM gamma is 0.01-0.10) but above
the noise floor of the binomial second difference (~1e-7).
"""

RICHARDSON_MAX_STEPS: int = 5000
"""Upper bound on the 2N-step Richardson extrapolation for theta/charm.

american.py applies Richardson extrapolation to cancel the leading O(1/N)
binomial error in theta and charm, doubling the step count from N to 2N.
This cap (matching the schema's overall steps cap of 5000) prevents the
doubling from silently exceeding sane limits.  When N > RICHARDSON_MAX_STEPS/2
the extrapolation is skipped and raw N-step values are used.
"""
