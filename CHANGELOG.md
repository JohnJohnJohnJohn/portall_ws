# Changelog

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
