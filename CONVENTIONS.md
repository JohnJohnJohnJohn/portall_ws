# CONVENTIONS.md — Single Source of Truth for deskpricer Financial Conventions

This file governs every unit, sign, scaling factor, and named constant used
across `src/deskpricer/`.  When code and this file disagree, this file wins.

***

## 1. Time Representation

| Symbol | Definition |
|--------|-----------|
| `t` | Time to expiry expressed as an ACT/365 Fixed year fraction: `t = calendar_days_to_expiry / 365.0` |
| `MIN_T_YEARS` | `1.0 / 365.0` — the minimum value of `t` accepted by any pricer.  Any `t` below this floor is clamped to exactly one calendar day.  Financial rationale: prevents QuantLib singularities at `t → 0`; 0-DTE is supported because callers supply live intraday market data that already embeds intraday decay. |
| Calendar days to expiry | `round(t * 365)`, floored at 1 |
| Business day roll | `ql.Following` — expiry is never rolled earlier than the contractual date |

`t` is the **only** expiry interface.  The pricer does not accept an explicit
expiry date.  Callers derive `t` from a real, pre-validated business-day expiry
date.

***

## 2. Greek Units and P&L Attribution Formulas

All Greeks are on a **per-unit (qty = 1) basis**.  Position scaling is the
caller's responsibility.

### 2.1 Delta (Δ)

- **Unit:** dimensionless; change in option price per $1 change in spot.
- **Range:** calls ∈ (0, 1); puts ∈ (−1, 0).
- **P&L attribution:**
  `delta_pnl = delta × ΔS`
  where `ΔS = S_t − S_{t−1}` in spot currency units.
- **Sign:** positive for calls, negative for puts (model output, no flip).

### 2.2 Gamma (Γ)

- **Unit:** change in delta per $1 change in spot; i.e., `∂²V / ∂S²`.
- **Always non-negative** for vanilla long options.
- **P&L attribution (second-order spot term):**
  `gamma_pnl = 0.5 × gamma × (ΔS)²`
- **Sign:** positive for long vanilla options; no flip applied.

### 2.3 Vega (ν)

- **Raw QuantLib output:** `∂V / ∂σ` per unit change in σ (decimal), i.e.,
  per 100 vol-points.
- **Stored / returned unit:** per **1 vol-point** (1% absolute):
  `vega = raw_vega / 100`
- **P&L attribution:**
  `vega_pnl = vega × Δσ_points`
  where `Δσ_points = (σ_t − σ_{t−1}) × 100` (positive when vol rises).
- **Sign:** positive for long vanilla options; no flip.

### 2.4 Theta (Θ)

- **Unit:** change in option price per **one business day** (forward-looking).
- **Computation:** `theta = price(next_business_day) − price(today)`.
  This is a bump-and-revalue, **not** QuantLib's analytic continuous-time
  theta.  The convention guarantees a directly usable per-business-day P&L
  figure consistent between European and American styles.
- **Sign under `theta_convention="pnl"` (default):**
  Negative for a typical long option (the position loses value as time passes).
  Example: theta = −0.05 means the option loses approximately $0.05 per
  business day.
- **Sign under `theta_convention="decay"` (Bloomberg DM<GO> convention):**
  `theta_decay = −theta_pnl`.  Positive for a typical long option, expressing
  the magnitude of decay.
- **P&L attribution — business-day mode (`theta_time_unit="business_day"`):**
  `theta_pnl = theta_pnl_convention × trading_days`
  where `trading_days = count_business_days(t−1, t)`, minimum 1 (intraday
  repricing still charges one full day's decay).
- **P&L attribution — calendar-day mode (`theta_time_unit="calendar_day"`):**
  `theta_pnl = theta_pnl_convention × (ANNUAL_TRADING_DAYS / CALENDAR_DAYS_PER_YEAR) × calendar_days`
  This converts the per-business-day theta rate to a per-calendar-day rate
  before multiplying, preventing overstatement of decay over
  weekends/holidays.
  The ratio used is `252 / 365` (see Section 4, `ANNUAL_TRADING_DAYS`).

  **Important:** regardless of `theta_convention`, the value of `theta`
  stored in `GreeksOutput` is always in `"pnl"` or `"decay"` sign depending
  on the request parameter.  The `theta_time_unit` parameter governs only
  the P&L attribution scaling in `run_pnl_attribution`; it does not change
  the stored `theta` value.

### 2.5 Rho (ρ)

- **Raw QuantLib output:** `∂V / ∂r` per unit change in `r` (decimal), i.e.,
  per 100 rate-points.
- **Stored / returned unit:** per **1 rate-point** (1% absolute):
  `rho = raw_rho / 100`
- **P&L attribution:**
  `rho_pnl = rho × Δr_points`
  where `Δr_points = (r_t − r_{t−1}) × 100`.
- **Sign:** positive for calls (higher rates → higher call value), negative
  for puts.

### 2.6 Charm (∂Δ/∂t per business day)

- **Unit:** change in delta per **one business day** passing.
- **Computation:** `charm = delta(next_business_day) − delta(today)`.
  Same bump-and-revalue convention as theta.
- **Sign under `theta_convention="pnl"` (default):**
  Negative for a long ATM/OTM call approaching expiry (delta decays toward 0
  or toward the digital payoff limit).
  Positive for a deep ITM call (delta converges toward 1).
- **Sign under `theta_convention="decay"`:**
  `charm_decay = −charm_pnl`.
- **P&L attribution:** charm is a **delta-rate-of-change** sensitivity.
  It is used to project how delta will shift over the holding period, enabling
  a delta re-hedge schedule, not as a standalone P&L term in the Taylor
  expansion implemented here.

### 2.7 Vanna (∂²V / ∂S ∂σ)

- **Unit:** per **$1** spot move per **1 vol-point**.
  Computed via 4-point cross central difference:
  `vanna = [V(S+dS, σ+dσ) − V(S+dS, σ−dσ) − V(S−dS, σ+dσ) + V(S−dS, σ−dσ)] / (4 × dS × dσ_points)`
  where `dσ_points = dσ_abs × 100`.
- **Sign:** positive for OTM calls (higher vol → higher delta), negative for
  deep ITM calls.
- **P&L attribution:**
  `vanna_pnl = vanna × ΔS × Δσ_points`

### 2.8 Volga / Vomma (∂²V / ∂σ²)

- **Unit:** per **(1 vol-point)²**.
  Computed via central second difference on vol:
  `volga = [V(S, σ+dσ) − 2V(S, σ) + V(S, σ−dσ)] / (dσ_points)²`
- **Sign:** always non-negative for long vanilla options (price is convex in
  vol).
- **P&L attribution:**
  `volga_pnl = 0.5 × volga × (Δσ_points)²`

***

## 3. Full P&L Attribution Formula

The Taylor expansion used in `run_pnl_attribution` is:

```
ΔV_explained =
    delta   × ΔS                       [first-order spot]
  + 0.5 × gamma × (ΔS)²               [second-order spot]
  + vega    × Δσ_points                [first-order vol, backward or average]
  + theta   × time_scalar              [time decay]
  + rho     × Δr_points                [first-order rate, backward or average]
  + vanna   × ΔS × Δσ_points          [cross spot-vol, if cross_greeks=True]
  + 0.5 × volga × (Δσ_points)²        [second-order vol, if cross_greeks=True]

ΔV_actual   = price_t − price_{t−1}
residual    = ΔV_actual − ΔV_explained
```

Where:
- `ΔS = S_t − S_{t−1}` (spot currency units)
- `Δσ_points = (σ_t − σ_{t−1}) × 100` (vol-points)
- `Δr_points = (r_t − r_{t−1}) × 100` (rate-points)
- `time_scalar`:
  - `theta_time_unit="business_day"`: `= trading_days` (minimum 1)
  - `theta_time_unit="calendar_day"`: `= (ANNUAL_TRADING_DAYS / CALENDAR_DAYS_PER_YEAR) × calendar_days`
- `theta` used in the formula is always in `"pnl"` sign convention
  (negative for typical long-option decay), regardless of the
  `theta_convention` request parameter.  If `theta_convention="decay"` was
  requested, the stored theta has been sign-flipped relative to the P&L
  convention; `run_pnl_attribution` must use `theta_convention="pnl"` for
  its internal pricing calls to ensure the formula above is applied
  consistently.  **See Section 4, Fix 1 for the specific consequence.**

***

## 4. Named Constants

All constants must be defined in `src/deskpricer/pricing/constants.py` and
imported from there.  No numeric literal that appears in this table may remain
as an inline literal in any business-logic file.

| Constant Name | Value | Location (current) | Financial Principle | Calendar-aware? |
|---|---|---|---|---|
| `MIN_T_YEARS` | `1.0 / 365.0` | `conventions.py` | Minimum time-to-expiry floor; prevents QuantLib singularity at `t → 0`. | No — one calendar day is universally valid. |
| `ANNUAL_TRADING_DAYS` | `252` | `pricing_service.py` (inline in theta_pnl branch) | Standard US/HK equity market convention for the number of business days per calendar year, used to convert per-business-day theta to a per-calendar-day rate. | **Yes** — see note below. |
| `CALENDAR_DAYS_PER_YEAR` | `365` | `pricing_service.py` (inline in theta_pnl branch) | Denominator for ACT/365 year fraction and for calendar-day theta scaling. | No. |
| `MAX_EXPIRY_T_DISCREPANCY` | `0.20` | `conventions.py` (`_MAX_EXPIRY_T_DISCREPANCY`) | Warning threshold: if the ACT/365 round-trip discrepancy between input `t` and effective QuantLib `t` exceeds 20%, something unusual has occurred (very short-dated or very long-dated). | No. |
| `DEFAULT_STEPS` | `500` | `conventions.py` | Number of binomial tree steps; balances accuracy vs. speed for American pricing. Increase for LEAPS (>1 year). | No (but callers may override). |
| `DEFAULT_BUMP_SPOT_REL` | `0.01` | `conventions.py` | 1% relative spot bump; large enough to avoid floating-point noise, small enough for accurate finite difference. | No. |
| `DEFAULT_BUMP_VOL_ABS` | `0.001` | `conventions.py` | 0.1 vol-point absolute vol bump (0.1% in decimal). | No. |
| `DEFAULT_BUMP_RATE_ABS` | `0.001` | `conventions.py` | 0.1 rate-point absolute rate bump (0.1% in decimal). | No. |
| `IV_SOLVER_VOL_LO` | `1e-6` | `implied_vol.py` (inline in `impliedVolatility` call) | Lower vol bound for IV solver; effectively zero but avoids log(0) in BSM. | No. |
| `IV_SOLVER_VOL_HI` | `5.0` | `implied_vol.py` (inline) | Upper vol bound = 500% implied vol; catches instruments with extreme option premiums. | No. |
| `IV_SOLVER_VOL_LO_RETRY` | `1e-8` | `implied_vol.py` (inline retry block) | Tighter lower bound used in the retry pass for root-not-bracketed errors. | No. |
| `IV_SOLVER_VOL_HI_RETRY` | `10.0` | `implied_vol.py` (inline retry block) | Extended upper bound (1000%) for the retry pass. | No. |
| `IV_SEED_VOL` | `0.20` | `implied_vol.py` (inline) | 20% seed vol for the IV solver's initial vol surface; chosen as a typical ATM equity vol. | No. |
| `IV_TOLERANCE_MULTIPLIER_ANALYTIC` | `10` | `implied_vol.py` (inline) | Analytic engine re-price tolerance = `10 × accuracy`; tight because the analytic engine has no discretisation noise. | No. |
| `IV_TOLERANCE_MULTIPLIER_TREE` | `50` | `implied_vol.py` (inline) | Tree engine re-price tolerance = `50 × accuracy`; relaxed to accommodate binomial discretisation error at 500 steps. | No. |
| `IV_HIGH_VOL_WARNING_THRESHOLD` | `2.0` | `implied_vol.py` (inline) | Log a warning when solved IV exceeds 200%; indicates likely data-quality issue. | No. |
| `IV_REPRICE_RELATIVE_TOLERANCE` | `0.001` | `implied_vol.py` (inline) | Relative tolerance (0.1% of target price) for IV reprice verification; prevents over-tight rejection on high-nominal underlyings. | No. |
| `SPOT_DIVERGENCE_THRESHOLD` | `0.05` | `schemas.py` (`check_spot_divergence`) | Portfolio legs with spot prices diverging by more than 5% receive a warning that aggregate Greeks are a linear approximation across independent positions. | No. |
| `VOL_BUMP_CAP_FACTOR` | `0.5` | `american.py`, `cross_greeks.py` (inline) | Vol bump is capped at `v × 0.5` to ensure `v − bump > 0`; prevents negative vol in the down-bump leg of finite differences. | No. |

### Note on `ANNUAL_TRADING_DAYS` and calendar-awareness

The value `252` is currently hardcoded in `pricing_service.py` in the
`theta_time_unit="calendar_day"` branch.  This value is the **US/NYSE
convention**.  The HK Exchange has approximately 246 trading days per year;
the UK Exchange has approximately 253.

**Decision for this codebase:** use the fixed constant `252` regardless of
the chosen calendar.  Rationale: the calendar-day conversion is an
approximation by design (it transforms a per-business-day rate to a daily
rate over a mixed calendar/trading-day hold period); the 5–6 day difference
across markets introduces less than 2% error in the theta P&L attribution
term over typical hold periods, which is within the residual tolerance.

If calendar-aware precision is required in a future version, replace the
constant with a function `get_annual_trading_days(calendar_name)` that maps
each `CalendarLiteral` to its empirically observed trading-day count, and
update all call sites.  This change should only be made together with
updating the regression tests in Section 3, Test 13.

***

## 5. Sign Convention Summary Table

| Greek | `theta_convention="pnl"` | `theta_convention="decay"` |
|---|---|---|
| Theta | Negative for long vanilla option | Positive for long vanilla option |
| Charm | Negative for long ATM/OTM call (delta converging to 0 near expiry); positive for deep ITM call (delta converging to 1) | Sign flipped relative to pnl |
| All other Greeks | Unaffected by `theta_convention` | Unaffected |

***

## 6. Bump Semantics

| Greek | Method | Bump type |
|---|---|---|
| Delta (European) | QuantLib analytic | — |
| Gamma (European) | QuantLib analytic | — |
| Vega (European) | QuantLib analytic (`option.vega()`) then ÷100 | — |
| Rho (European) | QuantLib analytic (`option.rho()`) then ÷100 | — |
| Theta (European & American) | Next-business-day revalue | Calendar/business-day forward bump |
| Charm (European & American) | Next-business-day revalue of delta | Calendar/business-day forward bump |
| Delta (American) | Central difference on spot; bump = `DEFAULT_BUMP_SPOT_REL × S` | Relative |
| Gamma (American) | Central second difference on spot | Relative |
| Vega (American) | Central difference on vol; bump = `DEFAULT_BUMP_VOL_ABS`; result ÷100 | Absolute |
| Rho (American) | Central difference on rate; bump = `DEFAULT_BUMP_RATE_ABS`; result ÷100 | Absolute |
| Vanna | 4-point cross central difference on (spot, vol) | Relative spot × absolute vol |
| Volga | Central second difference on vol | Absolute vol |
