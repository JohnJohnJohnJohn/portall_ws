# Changelog

## Unreleased

_Nothing pending — see 3.4.1 milestone entry below._

## 3.4.1 — 2026-06-10

### Fixed
- **American gamma sub-tick collapse (CRR/JR lattice alignment)** — Deep-OTM American
  options priced with `binomial_crr` and the default `bump_spot_rel=0.01` could return
  gamma at floating-point noise level (e.g. `3.75e-07` instead of `~0.02`). The root
  cause was that the delta and gamma finite differences shared the same bump
  `h_s = bump_spot_rel × S`. When `h_s` is smaller than one CRR lattice tick
  (`S × (exp(σ√Δt) − 1)`), all three repriced option prices land on the same
  locally-linear segment of the piecewise-linear binomial surface and the second
  difference collapses. Fixed by computing a separate `h_s_gamma = max(h_s,
  GAMMA_MIN_TICKS × crr_tick)` that spans at least 3 lattice ticks. Delta and charm
  continue to use the original fine bump. When `h_s` already exceeds the threshold
  (ATM options, large explicit bumps), the gamma reprices reuse the delta reprices
  with no extra NPV calls and no performance regression.
- **`GAMMA_MIN_TICKS = 3`** constant added to `src/deskpricer/pricing/constants.py`
  with full rationale docstring.
- **Regression tests** — `tests/test_gamma_sub_tick_regression.py` added with 5 cases
  covering the originally-failing deep-OTM input (`S=29.74, K=47`), the working
  control case (`S=26.52, K=42`), both CRR and JR engines, and an ATM guard confirming
  the fix does not disturb normal inputs.

## 3.4.0 — Milestone 1 (MCP-ready) — 2026-05-23

### Added
- **Phase 1C — PyPI and registry metadata**
  - `smithery.yaml` for future Smithery listing (`deskpricer-mcp` stdio start command).
  - PyPI publish: https://pypi.org/project/deskpricer/ (`pip install deskpricer`).
  - README MCP section (Cursor + Claude Desktop) and updated `docs/mcp_quickstart.md`.
  - GitHub repo topics; default branch migrated to `main`.
  - Submitted to mcp.so and awesome-mcp-servers (pending approval).
- **Phase 1B — MCP transport layer**
  - MCP stdio server (`mcp_server.py`, `mcp_tools.py`) with tools: `price_option`,
    `implied_volatility`, `pnl_attribution`, `portfolio_greeks`.
  - CLI entrypoint `deskpricer-mcp`; runtime dependency `mcp>=1.0`.
  - Agent setup guide [`docs/mcp_quickstart.md`](docs/mcp_quickstart.md).
  - `tests/test_mcp_server.py` (20 MCP spec/execution tests; 261 total).
- **Phase 1A — concurrency and BSM fast path**
  - `ProcessPoolExecutor` worker pool replaces the former `asyncio.Lock` serialization
    (`worker.py`, `services/ql_runtime.py`). Configurable via `DESKPRICER_WORKERS`
    (default `min(4, cpu_count())`). Pool shuts down on app exit.
  - Pure-Python European pricer `pricing/bsm_fast.py` (scipy BSM) for `style=european`
    and for American options that are economically equivalent to Europeans.
  - American→European reroute when `|q + b| ≤ 1e-8` (calls) or `|r| ≤ 1e-8` (puts).
  - `tests/test_bsm_fast_parity.py`, `tests/test_american_european_reroute.py`,
    `tests/test_worker_pool.py`.
  - `DESKPRICER_INLINE=1` test mode (set in `conftest.py`) for in-process pricing.

### Changed
- Documentation updated for process-pool architecture and MCP (`README.md`, `AGENTS.md`,
  `docs/architecture.md`, `docs/operator_guide.md`, `IMPLEMENTATION_PLAN.md`).
- American call golden values aligned with European equivalents (reroute removes
  binomial discretisation error).

## 3.4.0 — 2026-05-19

### Added
- **Stock borrow cost parameter `b`** — all pricing endpoints (`/greeks`,
  `/portfolio/greeks`, `/impliedvol`, `/pnl_attribution`) now accept an optional
  `b` parameter (annualized continuously compounded borrow cost, decimal, default
  `0.0`). The effective cost-of-carry is `r − q − b`, implemented via QuantLib
  dividend yield `q + b`. Callers omitting `b` receive identical results to prior
  versions (fully backward compatible).
- `DEFAULT_BORROW_COST = 0.0` constant in `pricing/constants.py`.
- No-arbitrage bounds in the IV solver updated to use `exp(−(q + b) × T)` for the
  discount factor on the spot leg, correctly shifting call/put bounds for
  hard-to-borrow names.
- 9 new tests: zero-default regression, call/put price directionality, portfolio
  legs, PnL attribution passthrough, IV roundtrip, and boundary validation
  (`b = 5.1` → HTTP 422).

### Fixed
- **Documentation sync for 3.4.0** — release executable name (`DeskPricer_v3.exe`),
  borrow-cost `b` in operator/excel guides, repaired PnL attribution parameter table
  in `docs/api.md`, and AGENTS.md test count (216).

## 3.3.1 — 2026-04-24

### Fixed
- **Documentation version numbers** — updated all stale `service_version` examples across `README.md`, `docs/api.md`, and `docs/operator_guide.md` from `2.1.0`/`2.5.1`/`3.0.1` to `3.3.1`.
- **AGENTS.md test count** — corrected expected test count from 104 to 207.

## 3.3.0 — 2026-04-24

### Changed
- **Migrated theta and charm to 1-calendar-day ACT/365 convention.** Removed `next_business_day` bump, `theta_convention` parameter, and all business-day theta references. European and American pricers now compute theta/charm by shortening expiry by exactly 1 calendar day (`expiry_date - 1`) and revaluing. PnL attribution is now `theta_pnl = theta × calendar_days_elapsed` with no business-day adjustment.
- **Weekend/holiday theta** — theta decay now accrues on weekends and holidays (Friday→Monday = ~3× theta). This matches Bloomberg, broker risk screens, and FRTB PnL Explain conventions.

### Removed
- `next_business_day` function and `MAX_NEXT_BD_SEARCH_DAYS` constant.
- `theta_convention` parameter from all pricers, schemas, routers, and services.
- `theta_time_unit` parameter from PnL attribution (calendar-day is now the only mode).
- `trading_days` field from PnL attribution meta; replaced by `calendar_days`.
- `ANNUAL_TRADING_DAYS` constant (no longer needed).

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
