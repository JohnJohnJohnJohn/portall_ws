# DeskPricer — Agent Guide

Single entry point for any coding agent working on this repo.

## Project Summary

DeskPricer is a **local-only** HTTP microservice that prices vanilla European and American equity options and returns Greeks, implied volatility, and PnL attribution. The primary consumer is Excel via `WEBSERVICE` + `FILTERXML`; JSON is available for programmatic clients. It is **not intended to be run or served as a public/server-style service**.

## Tech Stack

| Layer | Tool | Version |
|-------|------|---------|
| Language | Python | 3.12.7 |
| Framework | FastAPI | 0.100+ |
| Validation | Pydantic | v2 |
| Pricing engine | QuantLib | 1.42.1 |
| Server | Uvicorn | 0.23+ |
| Test runner | pytest | 7.4+ |
| Fuzzing | hypothesis | 6.82+ |
| Linter / formatter | ruff | 0.15+ |
| Type checker | mypy | 1.5+ |
| Build | setuptools + pyproject.toml | — |
| Executable | PyInstaller | (dev only) |

Package manager: **pip** (venv) or **uv**.

## Directory Map

```
src/deskpricer/          # Application source
  pricing/                # Pricing engine (European, American, IV, cross-greeks)
  app.py                  # FastAPI factory, routes, middleware
  schemas.py              # Pydantic request/response models
  errors.py               # Custom exceptions and FastAPI handlers
  responses.py            # XML/JSON serializers, content negotiation
  logging_config.py       # Structured JSON logging
  main.py                 # Uvicorn entrypoint, CLI args

tests/                    # pytest suite (flat, no subfolders)
docs/                     # API reference, Excel guide, architecture
scripts/                  # PyInstaller build, NSSM service install
sample/                   # Demo Excel workbook
```

## Commands

Copy-pasteable. Run from repo root.

```bash
# Install (runtime + dev)
pip install -e ".[dev]"

# Run
python -m deskpricer.main

# Run on custom port
python -m deskpricer.main --port 9000

# Test
pytest tests -v

# Lint
ruff check src tests

# Format
ruff format src tests

# Typecheck
mypy src

# Build standalone executable
python scripts/build_executable.py
```

## Definition of Done

A task is finished when **all** of these are true:

1. `pytest tests -v` passes (104 tests).
2. `ruff check src tests` reports zero errors.
3. `mypy src` reports zero errors.
4. No new runtime dependencies were added without approval.
5. Application code net line count did not increase (docs/tests/config exempt).

## Boundaries

### Never do

- Never add new **runtime** dependencies without explicit user approval.
- Never create new top-level folders.
- Never modify `sample/` (the demo Excel workbook) without approval.
- Never commit secrets, API keys, or hardcoded credentials.
- Never run `/cleanup` in a loop. One invocation = one pass. If the user says "keep going until clean," reply with the tests/lint/typecheck status and stop.
- Never change Greek conventions (vega/rho per 1%, theta/charm per calendar day) without approval.
- Never modify the XML/JSON response schema shape (meta/inputs/outputs) without approval.

### Ask first

- Adding new HTTP endpoints.
- Changing the PnL attribution formula or adding new attribution buckets.
- Adding database persistence or stateful storage.
- Changing the default pricing engine or day-count convention.
- Bumping minimum Python or QuantLib versions.

## Conventions

- **Naming**: `snake_case` for functions/variables, `PascalCase` for classes, `UPPER_SNAKE` for module-level constants.
- **Error handling**: Raise `InvalidInputError` (400) or `UnsupportedCombinationError` (422) for known bad inputs. Unexpected exceptions bubble to the catchall handler (500 / `PRICING_FAILURE`). Never leak raw tracebacks to clients.
- **Logging**: Use the `deskpricer` logger only. Structured JSON via `JSONFormatter`. Never use `print()` in application code.
- **Pricing layer**: All public functions in `pricing/` raise `InvalidInputError` or `UnsupportedCombinationError`; no raw QuantLib exceptions leak.
- **QuantLib state**: `_QL_LOCK` must be held whenever `ql.Settings.instance().evaluationDate` is mutated.
- **Responses**: All endpoints return `meta` + `inputs` + `outputs`. Portfolio returns `meta` + `legs` + `aggregate`. XML is default; JSON via `Accept: application/json` or `?format=json`.
- **Unit basis**: All pricing outputs from `/greeks`, `/impliedvol`, and `/pnl_attribution` are **per unit** (qty = 1). The pricer prices one contract at a time and does not model position sizing. Quantity scaling is the caller's responsibility. In the `/portfolio` endpoint, each leg returns unscaled unit Greeks; only the `aggregate` block reflects `qty`-weighted sums.

## Pointers

- API contract and examples: [`docs/api.md`](docs/api.md)
- Excel integration guide: [`docs/excel_usage.md`](docs/excel_usage.md)
- Module boundaries and data flow: [`docs/architecture.md`](docs/architecture.md)

## Commands the agent can invoke

- `/cleanup` — Execute the procedure defined in `.agent/commands/cleanup.md` verbatim. Do not paraphrase, do not relax constraints, do not chain multiple passes.
- `/review` — Run `pytest tests -v`, `ruff check src tests`, `mypy src`, and report the full results.
