# Changelog

## 3.1.0 — 2026-04-24

### Fixed
- **Vanna P&L dimensional inconsistency** — `run_pnl_attribution` now converts the absolute spot move to a percentage (`ΔS_pct = ΔS / S₀ × 100`) before applying the vanna term, matching the documented unit of vanna (per 1% relative spot move per vol-point).
- **Calendar-day theta not calendar-aware** — `run_pnl_attribution` now uses `annual_business_days(calendar, year)` instead of the hardcoded `252` in the calendar-day theta conversion, fixing ~2.4% overstatement for HK options.

### Added
- `CONVENTIONS.md` — Single source of truth for financial units, sign conventions, scaling factors, named constants, and P&L attribution formulas.
- `tests/test_financial_regression.py` — 14 financial regression tests with independent pure-Python BSM reference implementation (Tests 1-14 per FIX_INSTRUCTIONS.md).
- `tests/test_conventions_doc_exists.py` — Structural guard asserting `CONVENTIONS.md` exists.
- `MAX_NEXT_BD_SEARCH_DAYS`, `IV_SOLVER_DEFAULT_ACCURACY`, `IV_SOLVER_MAX_ITERATIONS` named constants in `src/deskpricer/pricing/constants.py`.

### Changed
- `implied_vol.py` function signature defaults now use `IV_SOLVER_DEFAULT_ACCURACY` and `IV_SOLVER_MAX_ITERATIONS`.
- `schemas.py` and `pricing_service.py` now use `IV_SOLVER_DEFAULT_ACCURACY` and `IV_SOLVER_MAX_ITERATIONS` instead of inline literals.
- `conventions.py` no longer re-exports dead constant `ANNUAL_TRADING_DAYS`.

## 3.0.1 — 2026-04-24

### Fixed
- **Date-dependent test fragility** — Three tests that relied on `date.today()` or direct QuantLib engine calls without global evaluation date management broke when the calendar rolled from Thursday to Friday:
  - `test_impliedvol_high_vol_warning` now sets `ql.Settings.instance().evaluationDate` before calling `compute_implied_vol` directly.
  - `test_omit_both_dates_diff_t` now mocks `date.today()` to a weekday so `next_business_day` is exactly 1 calendar day away.
  - `test_cross_greeks_reduces_residual_on_large_move` now uses explicit valuation dates to avoid Friday→Monday weekend jumps in theta and expiry calculations.

## 3.0.0 — 2026-04-23

### Fixed
- **Theta convention isolation** — `run_pnl_attribution` now internally forces `theta_convention="pnl"` before applying the PnL formula, preventing sign inversion when the caller requests `decay` convention.
- **Portfolio theta consistency** — `PortfolioRequest` now rejects legs with mixed `theta_convention` values with HTTP 422.
- **Calendar-day theta scaling** — PnL attribution with `theta_time_unit=calendar_day` now uses the fixed `252/365` ratio per `CONVENTIONS.md` §4, preventing overstatement of decay over weekends/holidays.

### Added
- `CONVENTIONS.md` — Central design-decision record for day counts, unit conventions, and numeric constants.
- `src/deskpricer/pricing/constants.py` — Named constants for all financial numeric literals (bumps, IV solver bounds, tolerance multipliers, etc.).
- `tests/test_financial_regression.py` — Independent BSM reference implementation and 16 cross-validation tests.

### Changed
- All hard-coded numeric literals in `pricing_service.py`, `implied_vol.py`, `american.py`, `cross_greeks.py`, and `schemas.py` replaced with named constants from `constants.py`.

## 2.7.0 — 2026-04-22

### Fixed
- **Issue 1** — `expiry_from_t` now computes expiry from ACT/365 calendar days (`round(t * 365)`) rolled to the next business day, ensuring the effective year fraction seen by QuantLib matches the caller's input `t`. This is a **numerical/behavioral change**; prices for longer-dated options (≥ 90 DTE) will shift compared to prior versions.
- **Issue 2** — PnL attribution drops the DTE-proxy fallback. When both valuation dates are omitted, `trading_days` is set to 1 instead of inferring business days from implied expiry dates. Provide explicit dates for accurate multi-day theta PnL. **Behavioral change**.
- **Issue 3** — Portfolio aggregate now includes `price` (sum of `qty × leg_price`).
- **Issue 4** — Implied volatility solver retries once with widened bounds `[1e-8, 10.0]` when the initial Brent bracket `[1e-6, 5.0]` fails, improving robustness for deep OTM / 0DTE options.
- **Issue 5** — Documented theta sign convention: negative for typical long options (opposite of Bloomberg DM<GO>).
- **Issue 6** — American vol bump now emits a `logger.warning` when auto-capped to `v * 0.5`.

### Added
- `tests/test_financial_golden.py` — Golden-values regression suite pinning European and American prices + Greeks across ATM/OTM/ITM, 7/30/90/365 DTE, and HK holiday crossing.

## 2.6.0 — 2026-04-22

### Changed
- Trading-day expiry conversion (`round(t * 252)` business days via `calendar.advance`).
- `MIN_T_YEARS` floor unified across European/American/IV pricers.
- Same-date `theta_pnl` guards removed (`count_business_days` always returns ≥ 1).
- `DEFAULT_STEPS` 400 → 500.
- European charm NameError fix.
- Cross-greeks, American early-exercise, rho scope, and per-unit PnL documentation updates.
