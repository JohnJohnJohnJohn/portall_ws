"""Conditions under which American and European vanilla options coincide."""

import math

from deskpricer.pricing.constants import AMERICAN_EUROPEAN_EQUIVALENCE_ABS_TOL


def american_is_european_equivalent(option_type: str, r: float, q: float, b: float) -> bool:
    """Return True when early exercise never carries premium over the European value.

    American call = European call when the effective carry yield is non-positive
    (``q + b <= 0`` within ``AMERICAN_EUROPEAN_EQUIVALENCE_ABS_TOL``; Merton's
    condition): without carry drag, exercising a call early forfeits time value
    with no offsetting benefit.

    American put = European put when the risk-free rate is zero (``r ≈ 0`` within
    the same tolerance) *and* the carry yield is non-negative (``q + b >= 0``):
    with no interest on the strike, receiving K early has no advantage, and a
    non-negative carry rules out accretion-driven early exercise.
    """
    tol = AMERICAN_EUROPEAN_EQUIVALENCE_ABS_TOL
    if option_type == "call":
        return (q + b) <= tol
    if option_type == "put":
        return math.isclose(r, 0.0, rel_tol=0.0, abs_tol=tol) and (q + b) >= -tol
    return False
