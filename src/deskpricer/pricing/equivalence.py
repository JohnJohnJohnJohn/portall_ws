"""Conditions under which American and European vanilla options coincide."""

import math

from deskpricer.pricing.constants import AMERICAN_EUROPEAN_EQUIVALENCE_ABS_TOL


def american_is_european_equivalent(option_type: str, r: float, q: float, b: float) -> bool:
    """Return True when early exercise never carries premium over the European value.

    American call = European call when the underlying pays no effective continuous
    yield (``q + b ≈ 0`` within ``AMERICAN_EUROPEAN_EQUIVALENCE_ABS_TOL``): without
    carry drag, exercising a call early forfeits time value with no offsetting benefit.

    American put = European put when the risk-free rate is zero (``r ≈ 0`` within the
    same tolerance): with no interest on the strike, receiving K early has no advantage.
    """
    tol = AMERICAN_EUROPEAN_EQUIVALENCE_ABS_TOL
    if option_type == "call":
        return math.isclose(q + b, 0.0, rel_tol=0.0, abs_tol=tol)
    if option_type == "put":
        return math.isclose(r, 0.0, rel_tol=0.0, abs_tol=tol)
    return False
