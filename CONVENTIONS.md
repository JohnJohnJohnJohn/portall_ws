# CONVENTIONS.md — deskpricer Financial Conventions

This file is the single source of truth for every financial unit,
sign convention, scaling factor, named constant, and P&L attribution
formula used in the deskpricer codebase. Every other file defers to
this document. In case of conflict, this file wins.

***

## 1. Time Convention

| Symbol | Definition |
|--------|-----------|
| `t` | Time to expiry expressed as an ACT/365 year fraction. `t = (expiry_date − today).days / 365`. |
| Calendar days | `t × 365`, rounded to the nearest integer, floored at 1. |
| `MIN_T_YEARS` | `1/365 ≈ 0.002740`. The minimum value of `t` accepted by the pricing engine. Any input `t < MIN_T_YEARS` is silently floored to `MIN_T_YEARS` before being passed to QuantLib. This prevents a numerical singularity in the BSM formula as `t → 0`. The floor is financially acceptable because callers are expected to supply live intraday market data (spot and IV) that already embeds intraday decay; the floor does not introduce meaningful pricing error for any practical 0-DTE workflow. |

***

## 2. Greek Units

### 2.1 Delta
- **Unit**: dimensionless, ∂V/∂S.
- **Range**:  for calls, [−1, 0] for puts (without dividend carry).
- **P&L attribution**: `delta_pnl = delta × ΔS`, where `ΔS = S_t − S_{t−1}` in price units.
- **No scaling applied.**

### 2.2 Gamma
- **Unit**: per price unit, ∂²V/∂S².
- **P&L attribution**: `gamma_pnl = 0.5 × gamma × (ΔS)²`.
- **No scaling applied.**

### 2.3 Vega
- **Raw QuantLib output**: ∂V/∂σ, where σ is expressed as a decimal (e.g. 0.20 for 20% vol). The raw value therefore represents the price change per 1.00 unit of decimal vol, i.e. per 100 vol-points.
- **Reported unit (market convention)**: per 1 vol-point (1% absolute). Achieved by **dividing the raw value by 100** before storing in `GreeksOutput.vega`.
- **P&L attribution**: `vega_pnl = vega × Δσ_points`, where `Δσ_points = (σ_t − σ_{t−1}) × 100`. The factor of 100 in `Δσ_points` cancels the division-by-100 in `vega`, recovering the correct dollar PnL.
- **Summary**: `vega` as stored = (∂V/∂σ) / 100. `vega_pnl = vega × Δσ_points`.

### 2.4 Theta
- **Unit**: price change per one business day passing, forward-looking.
- **Computation**: `theta = V(t+1 business day, all else equal) − V(today)`. This is a revalue-based (bump-and-revalue) estimate, not a continuous-time derivative.
- **Sign under `theta_convention="pnl"` (default)**:
  - A long option loses value as time passes → theta < 0.
  - This is the P&L sign: theta directly represents how much money is made/lost per business day.
- **Sign under `theta_convention="decay"`**:
  - theta is negated: theta > 0 for a long option, representing the magnitude of decay (as reported by Bloomberg's DM<GO>).
  - **Never use `"decay"` in P&L attribution.** The `run_pnl_attribution` function always calls `price_vanilla_fn` with `theta_convention="pnl"` regardless of the request parameter. This is correct and intentional.
- **P&L attribution (business-day mode)**: `theta_pnl = theta × trading_days`, where `trading_days` is the count of business days in `[valuation_date_{t−1}, valuation_date_t)` according to the chosen calendar, with a minimum of 1 (intraday repricing still charges one full business day of decay).
- **P&L attribution (calendar-day mode)**: `theta_pnl = theta × (ANNUAL_TRADING_DAYS / CALENDAR_DAYS_PER_YEAR) × calendar_days`. The ratio `252/365` converts a per-business-day theta into a per-calendar-day rate, preventing overstatement of decay over weekends and holidays.

### 2.5 Rho
- **Raw QuantLib output**: ∂V/∂r, where r is a decimal. Raw value represents price change per 1.00 unit of decimal rate, i.e. per 100 rate-points.
- **Reported unit**: per 1 rate-point (1% absolute). Achieved by **dividing raw value by 100**.
- **P&L attribution**: `rho_pnl = rho × Δr_points`, where `Δr_points = (r_t − r_{t−1}) × 100`.

### 2.6 Charm (delta decay)
- **Unit**: change in delta per one business day passing, forward-looking.
- **Computation**: `charm = delta(t+1 business day) − delta(today)`.
- **Sign under `theta_convention="pnl"`**: For a long ATM or ITM call approaching expiry, delta drifts toward 1 (in-the-money convergence) or toward 0 (OTM), so charm can be positive or negative depending on moneyness. Specifically, for an ITM call approaching expiry (delta > 0.5), charm is **negative** because delta decays back toward 0.5 as seen from next business day — wait, more precisely: for a long call that is ITM and approaching expiry, delta is increasing toward 1.0 (not decaying). Charm is the forward difference in delta. Under `"pnl"` convention, charm retains the same sign as the forward difference.
- **Sign under `theta_convention="decay"`**: charm is negated (same negation as theta).
- Charm is **not currently used in P&L attribution** in `pricing_service.py`. It is an output-only Greek. This is correct; charm enters PnL at third order and is excluded by design.

### 2.7 Vanna
- **Unit**: ∂²V / (∂S × ∂σ), expressed per 1% relative spot move per 1 vol-point.
- **Computation**: 4-point central cross-difference. `ds = S × bump_spot_rel` (relative). `dv_points = effective_bump_vol × 100`. The cross-difference formula is:
  `vanna = [V(S+ds, σ+dv) − V(S+ds, σ−dv) − V(S−ds, σ+dv) + V(S−ds, σ−dv)] / (4 × ds × dv_points)`
- **Sign**: For a call option, vanna = ∂delta/∂σ > 0 when the option is OTM (higher vol increases delta of an OTM call). For an ITM call, vanna < 0.
- **P&L attribution**: `vanna_pnl = vanna × ΔS_pct × Δσ_points`, where `ΔS_pct = (S_t − S_{t−1}) / S_{t−1} × 100` and `Δσ_points = (σ_t − σ_{t−1}) × 100`. Note the unit consistency: vanna is per 1% relative spot move per 1 vol-point.

### 2.8 Volga (Vomma)
- **Unit**: ∂²V/∂σ², per (1 vol-point)².
- **Computation**: central second difference: `volga = [V(S, σ+dv) − 2V(S, σ) + V(S, σ−dv)] / (dv_points²)`.
- **Sign**: volga ≥ 0 for any vanilla option (option price is convex in vol).
- **P&L attribution**: `volga_pnl = 0.5 × volga × (Δσ_points)²`.

***

## 3. Sign Convention Summary

| Greek | `theta_convention="pnl"` | `theta_convention="decay"` |
|-------|--------------------------|---------------------------|
| theta (long call/put) | **negative** (P&L loss) | **positive** (decay magnitude) |
| charm | forward difference sign preserved | negated |
| All other Greeks | unaffected | unaffected |

***

## 4. Named Constants

| Constant | Value | Financial Principle | Calendar-Aware? |
|----------|-------|---------------------|-----------------|
| `MIN_T_YEARS` | `1/365 ≈ 0.002740` | Floor to 1 calendar day to prevent BSM singularity | No |
| `MAX_EXPIRY_T_DISCREPANCY` | `0.20` (20%) | Warning threshold for rounding error in `expiry_from_t` | No |
| `DEFAULT_STEPS` | `500` | Binomial tree depth; balances accuracy vs. latency for American options | No |
| `DEFAULT_BUMP_SPOT_REL` | `0.01` (1%) | Relative spot bump for FD Greeks; large enough to clear noise, small enough for linearity | No |
| `DEFAULT_BUMP_VOL_ABS` | `0.001` (0.1 vol-point) | Absolute vol bump; consistent with 0.1 vol-point market quoting granularity | No |
| `DEFAULT_BUMP_RATE_ABS` | `0.001` (0.1 rate-point) | Absolute rate bump; consistent with central bank policy step granularity | No |
| `ANNUAL_TRADING_DAYS` | `252` | Standard NYSE/HK proxy for business days per calendar year; used only as a ratio `252/365` in calendar-day theta conversion. For actual business-day counts, `annual_business_days(calendar_name, year)` is used. | Yes — see note below |
| `CALENDAR_DAYS_PER_YEAR` | `365` | ACT/365 denominator; matches the day count convention throughout | No |
| `SPOT_DIVERGENCE_THRESHOLD` | `0.05` (5%) | Portfolio aggregate Greeks are a coarse approximation when legs have spot prices diverging by more than 5%; warning only | No |
| `IV_SOLVER_VOL_LO` | `1e-6` | Effective-zero lower vol bound for IV solver; avoids log(0) in BSM | No |
| `IV_SOLVER_VOL_HI` | `5.0` (500%) | Upper vol bound; caps solver search space to financially plausible range | No |
| `IV_SOLVER_VOL_LO_RETRY` | `1e-8` | Extended lower bound for root-not-bracketed retry | No |
| `IV_SOLVER_VOL_HI_RETRY` | `10.0` (1000%) | Extended upper bound for retry; catches extreme distressed situations | No |
| `IV_SEED_VOL` | `0.20` (20%) | Initial seed vol for solver; typical ATM equity starting point | No |
| `IV_TOLERANCE_MULTIPLIER_ANALYTIC` | `10` | Multiplier on `accuracy` for reprice tolerance; tight because closed-form has no discretisation noise | No |
| `IV_TOLERANCE_MULTIPLIER_TREE` | `50` | Multiplier for tree engine; relaxed to absorb binomial discretisation error | No |
| `IV_HIGH_VOL_WARNING_THRESHOLD` | `2.0` (200%) | Log warning above this IV; indicates likely data-quality issue | No |
| `IV_REPRICE_RELATIVE_TOLERANCE` | `0.001` (0.1%) | Relative tolerance floor for IV reprice check on high-nominal underlyings | No |
| `VOL_BUMP_CAP_FACTOR` | `0.5` (50%) | Cap vol bump at 50% of current vol to ensure `v − h_v > 0` always holds | No |
| `MAX_NEXT_BD_SEARCH_DAYS` | `30` | Maximum calendar days to scan when searching for the next business day; guards against infinite loop over holiday clusters. | No |
| `IV_SOLVER_DEFAULT_ACCURACY` | `1e-4` | Default Brent solver accuracy for IV root finding; tighter than QuantLib's own default to minimise reprice residual. | No |
| `IV_SOLVER_MAX_ITERATIONS` | `1000` | Maximum Brent iterations; sufficient for all practical BSM IV searches. | No |

**Note on `ANNUAL_TRADING_DAYS` calendar-awareness**: The value `252` is used exclusively in the ratio `ANNUAL_TRADING_DAYS / CALENDAR_DAYS_PER_YEAR` inside the calendar-day theta conversion in `pricing_service.py`. This ratio is a long-run average. For maximum accuracy, this ratio should be computed dynamically using `annual_business_days(calendar_name, year)` for the specific calendar and year in question. The current fixed value of 252 is acceptable for HK and NYSE calendars in typical years (actual values: HK ~246, NYSE ~252, UK ~253) but overstates the conversion rate for HK by approximately 2.4%. Whether this constitutes a material error depends on the holding period. Until a calendar-aware version is implemented, the constant value of 252 must be used with documentation noting this approximation.

***

## 5. P&L Attribution Formula

The full first- and second-order Taylor expansion used in `run_pnl_attribution`:

```
ΔV_explained
  = delta        × ΔS                           [first-order spot]
  + 0.5 × gamma  × (ΔS)²                        [second-order spot]
  + vega         × Δσ_points                    [first-order vol; vega already per vol-point]
  + theta        × N_days                        [time decay; N_days as described in §2.4]
  + rho          × Δr_points                    [first-order rate; rho already per rate-point]
  + vanna        × ΔS_pct × Δσ_points              [cross spot-vol; ΔS_pct = ΔS / S₀ × 100]
  + 0.5 × volga  × (Δσ_points)²                [second-order vol]

ΔV_actual  = V(S_t, σ_t, t_t, r_t, q_t) − V(S_{t−1}, σ_{t−1}, t_{t−1}, r_{t−1}, q_{t−1})

residual   = ΔV_actual − ΔV_explained
```

All quantities are **per unit** (no position size or qty applied at this layer). Position sizing (multiplication by `leg.qty`) is applied only in `run_portfolio`, not in `run_pnl_attribution`.

Signs: a long call position gains value when S rises (delta_pnl > 0), when σ rises (vega_pnl > 0), and loses value as time passes (theta_pnl < 0 under `"pnl"` convention). All signs above are for a long position; callers scale by signed quantity.
