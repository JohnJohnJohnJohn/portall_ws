# Changelog

## Unreleased

### Fixed

- **IV no-arbitrage pre-check now matches the solver's day-grid T** — the
  pre-check previously discounted at the raw input `t` while the solver
  priced at the whole-day effective T; deep-ITM targets in that half-day gap
  passed the pre-check and failed with the generic "outside solver bounds"
  message. They now fail with the informative lower-bound message.
- **American IV lower bound is now the undiscounted intrinsic (K−S / S−K)**
  — targets below immediate-exercise value (e.g. stale settlement prints)
  are rejected up front with "below the no-arbitrage lower bound <intrinsic>"
  instead of the generic solver-bounds error.

### Added

- **Ill-conditioned IV warning** — when vega at the solved IV falls below
  0.01 per 1 vol-point, a structured warning is logged (deep-ITM/OTM IVs
  carry no vol information; ~0.01 of price noise maps to >1 vol-point).
- **American cross-greeks low-steps warning** — below 2000 steps, volga is
  lattice-noise dominated; callers are warned to treat it as indicative.

### Docs

- `docs/numerical_analysis.md` — full numerical record (accuracy, edge-case
  register); §4.3 corrected after re-measurement (deep-ITM "cancellation"
  was a probe T-grid artifact; double-precision CDF saturation is exact).
- `docs/api.md` — IV conditioning caveat and time-granularity notes.

- **HTTP 500 on 1–1.5-day options** — `bsm_fast._effective_t` produced a
  `effective_t1` of 0 when the expiry lands at `valuation_date + 1` (most
  weekdays on business calendars; always on the `null` calendar), dividing by
  `v·sqrt(0)` in the theta/charm revalue. Such requests now use the same
  intrinsic-theta fallback as the ≤ 1-day branch. Regression sweep in
  `tests/test_zero_day_boundary.py`.
- **American→European reroute signs** — calls now reroute whenever
  `q + b ≤ 0` (full Merton condition; previously only `q + b ≈ 0`), and puts
  with `r ≈ 0` no longer reroute when `q + b < 0` (accreting underlying makes
  early exercise optimal; previously underpriced ~1.4% in that regime).
- **Empty optional query params 422'd** — Excel `WEBSERVICE` renders empty
  cells as `field=`; `b=`, `valuation_date=`, `steps=`, `calendar=` etc. now
  fall back to their defaults instead of failing validation. Root cause:
  starlette `QueryParams` is not a `dict` subclass, so the pre-existing
  `engine=""` coercion never fired on GET requests either — it now does.
- **500s were undebuggable from logs** — the catchall handler now logs
  `exc_info`, so the stack trace lands in the JSON file log's `exception`
  field (client responses unchanged).

### Changed

- Import hygiene: modules now import numeric constants directly from
  `pricing/constants.py` instead of through the `conventions.py` re-export,
  which has been removed.

### Removed

- `pricing/european.py` (test-only QuantLib oracle) moved to
  `tests/_ql_european_ref.py`; unused `annual_business_days` /
  `count_business_days` helpers moved to `tests/_conventions_ref.py`.
  Net −155 lines of application code.

### Docs

- Corrected stale claims: divergent portfolio spots warn (never 422);
  `bsm_fast` uses stdlib `math.erf`, not scipy; reroute conditions;
  expiry-discrepancy threshold is 20%.
- Documented the portfolio task timeout (`DESKPRICER_TASK_TIMEOUT`, 60s
  default) for large American books.

## 3.5.0 — 2026-07-20

### Performance

- **BSM fast path: ~16× faster European pricing (267µs → 16µs)** by replacing
  `scipy.stats.norm.cdf/pdf` with stdlib `math.erf`-based scalar helpers
  (bit-identical results to ~1e-15) and caching `d1`, `d2`, discount factors,
  and CDF/PDF values within a single request (was recomputed 5× per request).
- **Cross-greeks NPV-only fast path** — `compute_cross_greeks` was calling the
  full Greeks pipeline 6× per state but only reading `.price`.  New
  `price_vanilla_npv()` helper skips the bump-and-revalue Greeks entirely,
  cutting American cross-greeks from ~72 tree builds to 6 (10× speedup).
- **Adaptive step count for American options** — when the caller leaves `steps`
  at the default, the engine now picks a value based on time-to-expiry
  (`steps ≈ 200 / t`, clamped to [100, 2000]).  Long-dated options price faster
  (200 steps at T=1yr); short-dated options price more accurately (2000 steps
  at T=0.1yr).  The chosen value is echoed in `meta.effective_steps`.
- **Worker pool default raised 4 → 8** to absorb bursty Excel WEBSERVICE
  recalc concurrency on modern 8+ core desktops.
- **scipy moved to dev-only dependencies** — production no longer requires
  scipy (the BSM path uses stdlib `math.erf`).  Only `tests/_bsm_ref.py`
  (the independent reference oracle) still uses scipy, via the `dev` extra.

### Accuracy

- **Gamma sub-tick collapse detection** — at high vol / low step counts the
  gamma second-difference could collapse to numerical noise (e.g. returning
  0.0004 instead of 0.0157 at v=0.5, steps=500).  The bump is now widened to
  span at least 3 CRR lattice ticks (up from 1), with a runtime cross-check
  that falls back to an even wider bump if the widened gamma still looks like
  noise.  Verified: gamma is now within ~10% of BSM across all vol/step
  combinations tested.
- **Richardson extrapolation for American theta/charm** — combines binomial
  values at N and 2N steps to cancel the leading O(1/N) discretisation error.
  At 500 steps, theta error vs the 20000-step asymptote drops from ~8e-6
  (raw 500-step) to ~3e-6 (Richardson-extrapolated).  Cost: 3 extra NPV calls
  per American request.
- **IV solver honours adaptive steps** — `/impliedvol` now applies the same
  adaptive step logic as `/greeks`, so a `/greeks → /impliedvol` round-trip
  at default steps no longer fails `verify_reprice` on long-dated Americans.
  The solver also enforces a 500-step minimum to avoid the saw-tooth
  convergence that binomial exhibits at low step counts.

### Reliability

- **Pool timeout** — `run_pricing_task` now wraps the executor call in
  `asyncio.wait_for(timeout=60s)` (configurable via `DESKPRICER_TASK_TIMEOUT`).
  On timeout returns HTTP 503 `PRICING_TIMEOUT` instead of hanging indefinitely.
- **BrokenProcessPool recovery** — when a worker dies (segfault, OOM), the
  pool is automatically shut down and rebuilt on the next request, rather
  than leaving the service permanently broken until manual restart.
- **Worker count validation** — invalid `DESKPRICER_WORKERS` values now raise
  a clean error at first request rather than silently clamping.
- **Insufficient-steps warning** — logs a one-time warning (per process)
  when the caller-supplied step count is likely too low for the option's
  tenor and vol.

## 3.4.5 — 2026-06-10

### Fixed
- **PyInstaller process pool crash (take 2)** — The 3.4.4 fix added
  `freeze_support()` to `main.py`, but the PyInstaller build uses
  `scripts/run_deskpricer.py` as its entry point, which never called it.
  Moved `freeze_support()` to the correct entry point and added
  `deskpricer.worker` as an explicit hidden import so the spawned child
  process can locate the worker module.

## 3.4.4 — 2026-06-10

### Fixed
- **PyInstaller multiprocessing crash on Windows** — The process-pool worker
  spawn would fail with `unrecognized arguments: --multiprocessing-fork`
  because the PyInstaller-built executable's `argparse` rejected the
  internal arguments that Python's `multiprocessing` passes to child
  processes on Windows. Fixed by adding `multiprocessing.freeze_support()`
  and switching `parse_args` to `parse_known_args` in `main.py`.

## 3.4.3 — 2026-06-10

### Changed
- **Version bump** — Re-release after verifying 3.4.2 GAMMA_MIN_TICKS fix
  end-to-end (HTTP server, process pool, American Binomial pricing).

## 3.4.2 — 2026-06-10

### Fixed
- **GAMMA_MIN_TICKS too aggressive (3 → 1)** — The gamma sub-tick collapse fix
  introduced in 3.4.1 used `GAMMA_MIN_TICKS=3`, which widened the gamma bump
  whenever `h_s < 3 × crr_tick`. Collapse only occurs when `h_s < 1 × crr_tick`
  (all three finite-difference points on the same linear segment). The
  overly-conservative threshold caused 8 regression failures across golden
  tests, desk fixtures, and the ATM gamma sanity check. Fixed by reducing
  `GAMMA_MIN_TICKS` to 1 — mathematically sufficient to cross a lattice
  boundary and prevent second-difference collapse.

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

## 3.4.0 — 2026-05-23 (Milestone 1, MCP-ready)

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
- 9 borrow-cost tests: zero-default regression, call/put price directionality,
  portfolio legs, PnL attribution passthrough, IV roundtrip, and boundary
  validation (`b = 5.1` → HTTP 422).
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
  - `tests/test_mcp_server.py` (20 MCP spec/execution tests).
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

### Fixed
- **Documentation sync for 3.4.0** — release executable name (`DeskPricer_v3.exe`),
  borrow-cost `b` in operator/excel guides, repaired PnL attribution parameter table
  in `docs/api.md`.

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
- `tests/test_financial_regression.py` — 14 financial regression tests with independent pure-Python BSM reference implementation.
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
