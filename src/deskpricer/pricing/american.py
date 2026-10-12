"""American option pricing via BinomialVanillaEngine with bump-and-revalue Greeks."""

import logging
import math
from datetime import date

import QuantLib as ql

from deskpricer.errors import InvalidInputError
from deskpricer.pricing.constants import (
    DEFAULT_BUMP_RATE_ABS,
    DEFAULT_BUMP_SPOT_REL,
    DEFAULT_BUMP_VOL_ABS,
    GAMMA_MIN_TICKS,
    GAMMA_NOISE_FLOOR,
    MIN_T_YEARS,
    RICHARDSON_MAX_STEPS,
    VOL_BUMP_CAP_FACTOR,
)
from deskpricer.pricing.conventions import (
    DEFAULT_CALENDAR,
    CalendarLiteral,
    default_day_count,
    expiry_from_t,
    get_calendar,
    ql_date_from_iso,
)
from deskpricer.schemas import GreeksOutput


def _npv(
    s: float,
    k: float,
    r: float,
    q: float,
    v: float,
    option_type: str,
    valuation_date: ql.Date,
    expiry_date: ql.Date,
    steps: int,
    engine_type: str,
    calendar: ql.Calendar,
    b: float = 0.0,
) -> float:
    """Return the NPV of an American option.

    ``valuation_date`` is used as the earliest exercise date
    (``ql.AmericanExercise(valuation_date, expiry_date)``), matching the
    standard listed-equity convention of immediate exercise.  Callers who
    need a T+1 earliest exercise date (e.g. options on futures) should pass
    ``valuation_date + 1`` as the start parameter.
    """
    if steps < 1:
        raise InvalidInputError("steps must be positive", field="steps")

    day_count = default_day_count()

    spot_handle = ql.QuoteHandle(ql.SimpleQuote(s))
    div_ts = ql.YieldTermStructureHandle(ql.FlatForward(valuation_date, q + b, day_count))
    rf_ts = ql.YieldTermStructureHandle(ql.FlatForward(valuation_date, r, day_count))
    vol_ts = ql.BlackVolTermStructureHandle(
        ql.BlackConstantVol(valuation_date, calendar, v, day_count)
    )

    process = ql.BlackScholesMertonProcess(spot_handle, div_ts, rf_ts, vol_ts)
    payoff = ql.PlainVanillaPayoff(ql.Option.Call if option_type == "call" else ql.Option.Put, k)
    exercise = ql.AmericanExercise(valuation_date, expiry_date)
    option = ql.VanillaOption(payoff, exercise)
    option.setPricingEngine(ql.BinomialVanillaEngine(process, engine_type, steps))

    try:
        return float(option.NPV())
    except RuntimeError as exc:
        logging.getLogger("deskpricer").warning(
            "American pricing failed", extra={"error": str(exc)}
        )
        raise InvalidInputError("Pricing failed for the given inputs") from exc


def price_american(
    s: float,
    k: float,
    t: float,
    r: float,
    q: float,
    v: float,
    option_type: str,
    valuation_date: date,
    steps: int,
    engine_type: str,
    b: float = 0.0,
    bump_spot_rel: float = DEFAULT_BUMP_SPOT_REL,
    bump_vol_abs: float = DEFAULT_BUMP_VOL_ABS,
    bump_rate_abs: float = DEFAULT_BUMP_RATE_ABS,
    calendar_name: CalendarLiteral = DEFAULT_CALENDAR,
) -> GreeksOutput:
    """Price an American option and return bump-and-revalue Greeks.

    Early exercise is permitted from the valuation date onward
    (``ql.AmericanExercise(valuation_date, expiry_date)``), matching the
    standard listed-equity convention of immediate exercise.  Callers who
    need a T+1 earliest exercise date (e.g. options on futures) should pass
    ``valuation_date + 1`` as the start parameter.

    Gamma uses a separate, wider bump (``h_s_gamma``) that is guaranteed to
    span at least ``GAMMA_MIN_TICKS`` CRR/JR lattice ticks.  This prevents
    the three spot reprices from landing on the same locally-linear segment
    of the binomial surface, which would cause the second difference to
    collapse to numerical noise.  Delta continues to use the finer
    ``bump_spot_rel`` bump for accuracy.  When ``h_s`` already exceeds the
    tick threshold (ATM options, large explicit bumps), ``h_s_gamma == h_s``
    and the gamma reprices reuse the delta reprices with no extra NPV calls.
    """
    if s <= 0:
        raise InvalidInputError("spot price must be positive", field="s")
    if k <= 0:
        raise InvalidInputError("strike must be positive", field="k")
    if v <= 0:
        raise InvalidInputError("volatility must be positive", field="v")
    if bump_spot_rel <= 0:
        raise InvalidInputError("bump_spot_rel must be positive", field="bump_spot_rel")
    if bump_vol_abs <= 0:
        raise InvalidInputError("bump_vol_abs must be positive", field="bump_vol_abs")
    if bump_rate_abs <= 0:
        raise InvalidInputError("bump_rate_abs must be positive", field="bump_rate_abs")
    if bump_spot_rel >= 1.0:
        raise InvalidInputError("bump_spot_rel must be < 1.0", field="bump_spot_rel")

    ql_date = ql_date_from_iso(valuation_date)
    calendar = get_calendar(calendar_name)
    expiry_date = expiry_from_t(ql_date, t, calendar)

    _common = (option_type, ql_date, expiry_date, steps, engine_type, calendar)
    price = _npv(s, k, r, q, v, *_common, b=b)

    # --- Delta: fine central-difference bump on spot ---
    h_s = bump_spot_rel * s
    if h_s <= 0.0 or not math.isfinite(h_s):
        raise InvalidInputError(
            "Spot bump underflowed to zero; use larger spot or bump_spot_rel",
            field="bump_spot_rel",
        )
    price_up_s = _npv(s + h_s, k, r, q, v, *_common, b=b)
    price_down_s = _npv(s - h_s, k, r, q, v, *_common, b=b)
    delta = (price_up_s - price_down_s) / (2.0 * h_s)

    # --- Gamma: sub-tick widening with collapse detection ---
    # When h_s is smaller than a few CRR lattice ticks, the three spot reprices
    # used in the second-difference gamma formula can either (a) all land on the
    # same locally-linear segment (collapsing gamma to numerical noise, e.g.
    # 3.75e-07 vs ~0.02), or (b) straddle a kink and overestimate gamma.  In
    # either case the fine-bump gamma is unreliable, so we widen the bump to
    # span at least GAMMA_MIN_TICKS ticks whenever h_s falls below that threshold.
    #
    # As a further guard against collapse that survives the widening (seen at
    # high vol / low step counts), we cross-check against an even wider bump
    # and fall back to it if the wide gamma still looks like noise.
    dt = t / steps
    crr_tick = s * (math.exp(v * math.sqrt(dt)) - 1.0)
    h_s_gamma = max(h_s, GAMMA_MIN_TICKS * crr_tick)
    if h_s_gamma > h_s:
        logging.getLogger("deskpricer").debug(
            "Gamma bump widened: h_s=%.6f -> h_s_gamma=%.6f (crr_tick=%.6f, min_ticks=%d)",
            h_s, h_s_gamma, crr_tick, GAMMA_MIN_TICKS,
        )
        price_up_g = _npv(s + h_s_gamma, k, r, q, v, *_common, b=b)
        price_down_g = _npv(s - h_s_gamma, k, r, q, v, *_common, b=b)
        gamma = (price_up_g - 2.0 * price + price_down_g) / (h_s_gamma * h_s_gamma)
        # Cross-check: if the widened gamma still looks like numerical noise,
        # try an even wider bump.  This catches the high-vol/low-steps collapse
        # mode where even GAMMA_MIN_TICKS ticks isn't enough span.
        if abs(gamma) < GAMMA_NOISE_FLOOR:
            h_s_extra = max(h_s_gamma, 2 * GAMMA_MIN_TICKS * crr_tick)
            if h_s_extra > h_s_gamma:
                price_up_x = _npv(s + h_s_extra, k, r, q, v, *_common, b=b)
                price_down_x = _npv(s - h_s_extra, k, r, q, v, *_common, b=b)
                gamma_extra = (price_up_x - 2.0 * price + price_down_x) / (h_s_extra * h_s_extra)
                if abs(gamma_extra) > abs(gamma):
                    logging.getLogger("deskpricer").debug(
                        "Gamma collapse detected after widening: gamma=%.2e -> gamma_extra=%.2e "
                        "(h_s_gamma=%.6f, h_s_extra=%.6f, crr_tick=%.6f, s=%.2f, v=%.4f, steps=%d)",
                        gamma, gamma_extra, h_s_gamma, h_s_extra, crr_tick, s, v, steps,
                    )
                    gamma = gamma_extra
    else:
        # h_s already spans >= GAMMA_MIN_TICKS ticks; the delta reprices are usable.
        gamma = (price_up_s - 2.0 * price + price_down_s) / (h_s * h_s)

    # Vega via central difference on vol
    # Divide by 100 to report standard market convention (per 1%)
    # Cap h_v at v*VOL_BUMP_CAP_FACTOR to prevent negative vol on v - h_v; warn when capped.
    h_v = min(bump_vol_abs, v * VOL_BUMP_CAP_FACTOR)
    if h_v < bump_vol_abs:
        logging.getLogger("deskpricer").warning(
            "American vol bump auto-capped: bump_vol_abs=%.6f -> effective=%.6f (v=%.6f)",
            bump_vol_abs,
            h_v,
            v,
        )
    if h_v <= 0.0 or not math.isfinite(h_v):
        raise InvalidInputError(
            "Vol bump underflowed to zero; use larger vol or bump_vol_abs",
            field="bump_vol_abs",
        )
    price_up_v = _npv(s, k, r, q, v + h_v, *_common, b=b)
    price_down_v = _npv(s, k, r, q, v - h_v, *_common, b=b)
    vega = (price_up_v - price_down_v) / (2.0 * h_v) / 100.0

    # Rho via central difference on rate
    # Divide by 100 to report standard market convention (per 1%)
    h_r = bump_rate_abs
    price_up_r = _npv(s, k, r + h_r, q, v, *_common, b=b)
    price_down_r = _npv(s, k, r - h_r, q, v, *_common, b=b)
    rho = (price_up_r - price_down_r) / (2.0 * h_r) / 100.0

    # Theta: P&L impact of one calendar day passing (forward-looking, negative for a long option).
    # Revalue with expiry shortened by 1 calendar day and subtract today's price.
    # When the option has <= 1 calendar day left, fallback to intrinsic value.
    # Richardson extrapolation (2*N steps combined with N steps to cancel the
    # leading O(1/N) binomial discretisation error) is applied to theta/charm
    # when N is small enough that doubling is still affordable.
    if t <= MIN_T_YEARS:
        price_t1 = max(s - k, 0.0) if option_type == "call" else max(k - s, 0.0)
        theta = price_t1 - price
        charm = 0.0
    else:
        expiry_t1 = expiry_date - 1
        _common_t1 = (option_type, ql_date, expiry_t1, steps, engine_type, calendar)
        price_t1 = _npv(s, k, r, q, v, *_common_t1, b=b)
        price_up_s_t1 = _npv(s + h_s, k, r, q, v, *_common_t1, b=b)
        price_down_s_t1 = _npv(s - h_s, k, r, q, v, *_common_t1, b=b)
        delta_t1 = (price_up_s_t1 - price_down_s_t1) / (2.0 * h_s)
        # Richardson extrapolation on theta/charm: theta = P(T-1) - P(T), and
        # both P(T-1) and P(T) carry O(1/N) binomial error.  We extrapolate
        # theta directly (not the individual prices): theta_rich = 2*theta_2N -
        # theta_N cancels the leading error.  Requires the at-today price and
        # delta at 2N steps too.  Skipped when 2N would exceed the step cap.
        if 2 * steps <= RICHARDSON_MAX_STEPS:
            _common_2n = (option_type, ql_date, expiry_date, 2 * steps, engine_type, calendar)
            _common_t1_2n = (option_type, ql_date, expiry_t1, 2 * steps, engine_type, calendar)
            price_2n = _npv(s, k, r, q, v, *_common_2n, b=b)
            price_t1_2n = _npv(s, k, r, q, v, *_common_t1_2n, b=b)
            price_up_s_2n = _npv(s + h_s, k, r, q, v, *_common_2n, b=b)
            price_down_s_2n = _npv(s - h_s, k, r, q, v, *_common_2n, b=b)
            price_up_s_t1_2n = _npv(s + h_s, k, r, q, v, *_common_t1_2n, b=b)
            price_down_s_t1_2n = _npv(s - h_s, k, r, q, v, *_common_t1_2n, b=b)
            delta_2n = (price_up_s_2n - price_down_s_2n) / (2.0 * h_s)
            delta_t1_2n = (price_up_s_t1_2n - price_down_s_t1_2n) / (2.0 * h_s)
            theta_n = price_t1 - price
            theta_2n = price_t1_2n - price_2n
            theta = 2.0 * theta_2n - theta_n
            charm_n = delta_t1 - delta
            charm_2n = delta_t1_2n - delta_2n
            charm = 2.0 * charm_2n - charm_n
        else:
            theta = price_t1 - price
            charm = delta_t1 - delta

    return GreeksOutput(
        price=price,
        delta=delta,
        gamma=gamma,
        vega=vega,
        theta=theta,
        rho=rho,
        charm=charm,
    )
