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
    ├── portfolio     └── PortfolioReq                                                      └── _QL_LOCK
    └── pnl_attribution                                                                             └── with_evaluation_date
```

| Module | Responsibility |
|--------|----------------|
| `app.py` | FastAPI factory, middleware (request logging, content-type negotiation), exception-handler registration, router inclusion. Thin composition root (< 100 lines). |
| `routers/*.py` | `APIRouter` modules per endpoint domain (`health`, `greeks`, `impliedvol`, `portfolio`, `pnl_attribution`). Handle request validation and call the service layer. |
| `services/pricing_service.py` | Orchestration functions (`run_greeks`, `run_impliedvol`, `run_portfolio`, `run_pnl_attribution`) that acquire the QuantLib lock, manage evaluation dates, invoke pricing engines, and assemble `meta`/`inputs`/`outputs` dicts. |
| `services/ql_runtime.py` | Global `_QL_LOCK` and async context manager `with_evaluation_date()` that saves/restores `ql.Settings.instance().evaluationDate`. |
| `schemas.py` | Pydantic v2 request/response models. `_EngineDefaultsMixin` sets `engine` default based on `style`. `_VanillaOptionCoreBase` removes field duplication between Greeks and IV requests. Model validators enforce cross-field rules (date order, bump vs. vol, unique leg IDs). |
| `errors.py` | Custom exceptions (`DeskPricerError`, `InvalidInputError`, `UnsupportedCombinationError`) and FastAPI exception handlers. Catchall handler returns 500 / `PRICING_FAILURE` with no traceback leakage. |
| `responses.py` | `serialize_*` family for each endpoint. `_clean_value` rounds floats to 9 decimals and converts non-finite to `None`. `_to_xml` sanitizes illegal XML characters and has a hard fallback. |
| `logging_config.py` | `_SafeRotatingFileHandler` (Windows-safe rollover), `JSONFormatter` (surrogate-safe, absolute fallback). |
| `main.py` | Uvicorn entrypoint, CLI arg parsing (`--port`, `--host`, `--quiet`), startup banner. |
| `pricing/engine.py` | Dispatcher. Validates inputs, floors `t` to 1 day, routes `european` → `price_european`, `american` → `price_american`. |
| `pricing/european.py` | Analytic Black-Scholes-Merton via `AnalyticEuropeanEngine`. Charm computed by forward-differencing delta 1 day forward. |
| `pricing/american.py` | Binomial CRR/JR via `BinomialVanillaEngine`. Greeks via bump-and-revalue (central differences on spot, vol, rate). Theta/charm via 1-day-forward reprice with expiry fallback to intrinsic value. |
| `pricing/implied_vol.py` | Brent solver (`impliedVolatility`) with bounds `[1e-6, 5.0]`. Re-prices at solved vol as sanity check. |
| `pricing/cross_greeks.py` | Vanna and volga via uniform finite differences using the same bump conventions as the main Greeks. |
| `pricing/conventions.py` | Date helpers (`ql_date_from_iso`, `expiry_from_t`) and numerical constants (`MIN_T_YEARS`, `DEFAULT_STEPS`, `DEFAULT_BUMP_*`, `DAY_COUNT`). |

## Data Flow

1. **Request arrives** → FastAPI router (`routers/*.py`).
2. **Query/body validation** → Pydantic model (`schemas.py`). `_EngineDefaultsMixin` fills default engine if omitted.
3. **Call service layer** → `run_greeks()` / `run_portfolio()` etc. in `services/pricing_service.py`.
4. **Acquire `_QL_LOCK`** → only one pricing call mutates global QuantLib state at a time.
5. **Set evaluation date** → `ql.Settings.instance().evaluationDate = ql_date_from_iso(valuation_date)` via `with_evaluation_date()`.
6. **Dispatch** → `price_vanilla()` or `compute_implied_vol()` in `pricing/engine.py`.
7. **Compute** → QuantLib engine calculates NPV and Greeks. European uses closed-form; American uses binomial tree.
8. **Restore evaluation date** → `finally` block resets global state.
9. **Build response payload** → `meta`, `inputs`, `outputs` dicts.
10. **Serialize** → `responses.py` picks JSON or XML based on `Accept` header / `?format=json`.
11. **Return** → `Response` with correct `Content-Type`.

## Key Invariants

1. **`_QL_LOCK` must be held** whenever `ql.Settings.instance().evaluationDate` is read or written. The lock is acquired in the service layer (`services/pricing_service.py`), not inside pricing functions.
2. **Engine/style mapping is rigid**: European → `analytic` only. American → `binomial_crr` or `binomial_jr` only. Any other combination raises `UnsupportedCombinationError` (422).
3. **`t < 1/365` is floored to 1 trading day** in `expiry_from_t`. This prevents QuantLib from collapsing on zero-day options.
4. **Vega and rho are per 1% point**; **theta and charm are per trading day**.
5. **All numeric outputs are finite** before serialization. `_clean_value` converts non-finite floats to `None` as a last-ditch guard.
6. **XML responses are sanitized** for illegal characters (control chars, surrogates, non-characters) before `xmltodict.unparse`.
7. **Log rollover failures are swallowed** on Windows (antivirus file locks). The `_SafeRotatingFileHandler` cooldowns for 60s and reopens the stream.
