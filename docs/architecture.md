# DeskPricer Architecture

Module boundaries, data flow, and invariants.

> **Design intent:** DeskPricer is a **local-only** tool for personal desk pricing and option analytics. It is **not intended to be run or served as a public/server-style service**. All design choices — localhost binding, no auth, no TLS, no rate limiting, XML-by-default — reflect this.

## Module Boundaries

```
HTTP Layer          Validation          Pricing Core          Serialization         Services
───────────         ───────────         ────────────          ─────────────         ────────
app.py              schemas.py          pricing/engine.py     responses.py          services/pricing_service.py
  ├── middleware      ├── _VanillaOption    ├── price_vanilla     ├── XML/JSON            ├── run_greeks
  └── routers         │   CoreBase          ├── compute_iv        ├── _clean_value        ├── run_impliedvol
    ├── health        ├── GreeksRequest     └── pricing/*.py      └── _to_xml             ├── run_portfolio
    ├── greeks        ├── ImpliedVolRequest                                               └── run_pnl_attribution
    ├── impliedvol    ├── PnLRequest                                                      services/ql_runtime.py
    ├── portfolio     └── PortfolioReq                                                      └── ProcessPoolExecutor
    └── pnl_attribution                                                                             worker.py
                                                                                                  └── execute_task
```

| Module | Responsibility |
|--------|----------------|
| `app.py` | FastAPI factory, middleware (request logging, content-type negotiation), exception-handler registration, router inclusion, lifespan hook that shuts down the worker pool on exit. |
| `routers/*.py` | `APIRouter` modules per endpoint domain (`health`, `greeks`, `impliedvol`, `portfolio`, `pnl_attribution`). Handle request validation and call the service layer. |
| `services/pricing_service.py` | Orchestration functions (`run_greeks`, `run_impliedvol`, `run_portfolio`, `run_pnl_attribution`) that dispatch pricing work to the process pool, assemble `meta`/`inputs`/`outputs` dicts, and support optional in-process fn injection for tests. |
| `services/ql_runtime.py` | `ProcessPoolExecutor` management (`get_pool`, `shutdown_pool`, `run_pricing_task`). Pool size defaults to `min(4, cpu_count())`, overridable via `DESKPRICER_WORKERS`. |
| `worker.py` | Top-level worker entrypoint `execute_task()` for process-pool dispatch. Each task sets an isolated `ql.Settings.instance().evaluationDate` in its worker process before calling the pricing core. |
| `mcp_server.py` | MCP stdio server (`deskpricer-mcp`) exposing four pricing tools to AI agents; calls `pricing_service` directly (no HTTP). |
| `mcp_tools.py` | MCP tool JSON schemas (from Pydantic) and detailed agent-facing descriptions. |
| `schemas.py` | Pydantic v2 request/response models. `_EngineDefaultsMixin` sets `engine` default based on `style`. `_VanillaOptionCoreBase` removes field duplication between Greeks and IV requests. Model validators enforce cross-field rules (date order, bump vs. vol, unique leg IDs). |
| `errors.py` | Custom exceptions (`DeskPricerError`, `InvalidInputError`, `UnsupportedCombinationError`) and FastAPI exception handlers. Catchall handler returns 500 / `PRICING_FAILURE` with no traceback leakage. |
| `responses.py` | `serialize_*` family for each endpoint. `_clean_value` rounds floats to 9 decimals and converts non-finite to `None`. `_to_xml` sanitizes illegal XML characters and has a hard fallback. |
| `logging_config.py` | `_SafeRotatingFileHandler` (Windows-safe rollover), `JSONFormatter` (surrogate-safe, absolute fallback). |
| `main.py` | Uvicorn entrypoint, CLI arg parsing (`--port`, `--host`, `--quiet`), startup banner. |
| `pricing/engine.py` | Dispatcher. Validates inputs, floors `t` to 1 day, routes Europeans and equivalent Americans to `bsm_fast`, otherwise routes Americans to `price_american`. |
| `pricing/bsm_fast.py` | Production European pricer: pure scipy BSM with calendar-day theta/charm and borrow-cost carry (`q + b`). Thread-safe; no QuantLib global state. |
| `pricing/european.py` | QuantLib reference European pricer (`AnalyticEuropeanEngine`). Retained for parity/regression tests against `bsm_fast`. |
| `pricing/equivalence.py` | Detects when an American option is economically identical to its European counterpart and can skip the binomial tree. |
| `pricing/american.py` | Binomial CRR/JR via `BinomialVanillaEngine`. Greeks via bump-and-revalue (central differences on spot, vol, rate). Theta/charm via 1-calendar-day expiry shortening and reprice, with fallback to intrinsic value at zero DTE. |
| `pricing/implied_vol.py` | Brent solver (`impliedVolatility`) with bounds `[1e-6, 5.0]`. Re-prices at solved vol as sanity check. Always uses QuantLib. |
| `pricing/cross_greeks.py` | Vanna and volga via uniform finite differences using the same bump conventions as the main Greeks. |
| `pricing/conventions.py` | Date helpers (`ql_date_from_iso`, `expiry_from_t`) and numerical constants (`MIN_T_YEARS`, `DEFAULT_STEPS`, `DEFAULT_BORROW_COST`, `DEFAULT_BUMP_*`, `DAY_COUNT`). |

## Data Flow

1. **Request arrives** → FastAPI router (`routers/*.py`).
2. **Query/body validation** → Pydantic model (`schemas.py`). `_EngineDefaultsMixin` fills default engine if omitted.
3. **Call service layer** → `run_greeks()` / `run_portfolio()` etc. in `services/pricing_service.py`.
4. **Dispatch to worker pool** → `run_pricing_task()` submits `execute_task()` to a `ProcessPoolExecutor` (or runs inline when `DESKPRICER_INLINE=1`, used by tests).
5. **Set evaluation date** → worker process sets `ql.Settings.instance().evaluationDate = ql_date_from_iso(valuation_date)` before any QuantLib call.
6. **Dispatch** → `price_vanilla()` or `compute_implied_vol()` in `pricing/engine.py`.
7. **Compute** → Europeans and equivalent Americans use closed-form BSM (`bsm_fast`); other Americans use QuantLib binomial; IV solving uses QuantLib.
8. **Build response payload** → `meta`, `inputs`, `outputs` dicts.
9. **Serialize** → `responses.py` picks JSON or XML based on `Accept` header / `?format=json`.
10. **Return** → `Response` with correct `Content-Type`.

## Key Invariants

1. **QuantLib work runs in worker processes**, each with its own `Settings.instance()`. The async event loop never mutates global QuantLib state directly.
2. **Engine/style mapping is rigid**: European → `analytic` only. American → `binomial_crr` or `binomial_jr` only. Any other combination raises `UnsupportedCombinationError` (422).
3. **American→European reroute** when early-exercise premium is zero: calls when `|q + b| ≤ 1e-8`, puts when `|r| ≤ 1e-8`. Rerouted legs use the same `bsm_fast` path as Europeans.
4. **`t < 1/365` is floored to 1 day** in `expiry_from_t`. The expiry is computed as `valuation_date + round(t * 365)` calendar days, then rolled to the next business day via the chosen calendar. This prevents QuantLib from collapsing on zero-day options.
5. **Vega and rho are per 1% point**; **theta and charm are per calendar day**.
6. **All numeric outputs are finite** before serialization. `_clean_value` converts non-finite floats to `None` as a last-ditch guard.
7. **XML responses are sanitized** for illegal characters (control chars, surrogates, non-characters) before `xmltodict.unparse`.
8. **Log rollover failures are swallowed** on Windows (antivirus file locks). The `_SafeRotatingFileHandler` cooldowns for 60s and reopens the stream.

## Environment Variables

| Variable | Default | Purpose |
|----------|---------|---------|
| `DESKPRICER_WORKERS` | `min(4, cpu_count())` | Process-pool size for concurrent QuantLib pricing |
| `DESKPRICER_INLINE` | unset (pool mode) | Set to `1` in tests to run pricing in-process (enables caplog/monkeypatch) |
