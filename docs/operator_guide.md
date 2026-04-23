# DeskPricer Operator Guide

## Quickstart

From a clean clone to a working pricing call in under 5 minutes:

```powershell
# 1. Install
python -m venv .venv
.venv\Scripts\activate
pip install -e ".[dev]"

# 2. Run
python -m deskpricer.main

# 3. Test with curl
curl "http://127.0.0.1:8765/v1/greeks?s=100&k=105&t=0.25&r=0.05&q=0.02&v=0.20&type=call&style=european"

# Expected output (XML):
# <?xml version="1.0" encoding="UTF-8"?>
# <greeks>
#   <meta>
#     <service_version>2.1.0</service_version>
#     ...
#   </meta>
#   <inputs>...</inputs>
#   <outputs>
#     <price>2.288743</price>
#     <delta>0.356244</delta>
#     ...
#   </outputs>
# </greeks>
```

For JSON, add `Accept: application/json` or `?format=json` to any request.

## Log Location

DeskPricer writes structured JSON logs to a rotating file.

- **Default path**
  - Windows: `C:\ProgramData\DeskPricer\logs\pricer.log`
  - Linux/macOS: `~/.local/share/deskpricer/logs/pricer.log`
- **Override**: set the `DESKPRICER_LOG_DIR` environment variable before starting the service.
  ```powershell
  $env:DESKPRICER_LOG_DIR = "C:\MyLogs"
  python -m deskpricer.main
  ```
- **Rotation**: 10 MB per file, 5 backups kept.
- **Fallback**: if the log directory cannot be created, logs go to `stderr`.

## Troubleshooting

### QuantLib install failures

**Symptom**: `pip install` fails with a compiler or wheel error.

**Fix**: QuantLib provides pre-built wheels for Windows and many Linux distributions. If you are on an unsupported platform:
1. Ensure you have a C++ compiler and CMake available.
2. Install QuantLib separately first: `pip install QuantLib`.
3. If building from source, see the [QuantLib build docs](https://www.quantlib.org/install.shtml).

### Zero-DTE surprises

**Symptom**: `t=0` returns a small positive price and non-zero Greeks instead of collapsing to intrinsic.

**Explanation**: DeskPricer floors `t < 1/365` to 1 day to prevent QuantLib from crashing on zero-day options. This is intentional. If you need true intrinsic-only valuation, subtract the 1-day time value manually or set `t` to a very small positive number and accept the floor.

### Engine/style mismatches

**Symptom**: `422 UNSUPPORTED_COMBINATION` with message about engine.

**Rules**:
- `style=european` → **only** `engine=analytic` (default).
- `style=american` → **only** `engine=binomial_crr` (default) or `binomial_jr`.

American options are priced with early-exercise permitted from the valuation date onward (standard listed-equity convention).

Any other combination is rejected. The schema auto-fills the correct default engine if you omit it.

### XML vs JSON content negotiation

**Symptom**: Excel `WEBSERVICE` returns garbled text.

**Explanation**: DeskPricer returns XML by default. Excel's `WEBSERVICE` does not send `Accept: application/json`, so XML is the correct format for Excel. Programmatic clients should send:
```
Accept: application/json
```
or append `?format=json` to the URL.

### DeskPricerError subclasses

| Exception | HTTP | Code | Meaning |
|-----------|------|------|---------|
| `InvalidInputError` | 400 | `INVALID_INPUT` | Business-rule validation failed (e.g., price out of arbitrage bounds, date out of range). |
| `UnsupportedCombinationError` | 422 | `UNSUPPORTED_COMBINATION` | Engine/style mismatch or other unsupported parameter pairing. |
| (catchall) | 500 | `PRICING_FAILURE` | Unexpected internal error. Never leaks raw tracebacks. |

## Limitations

DeskPricer is intentionally scoped as a **local-only desk tool**. The following are by design, not oversights:

- **No finite-difference (FD) engine** — only analytic Black-Scholes-Merton for Europeans and binomial CRR/JR for Americans.
- **European requires analytic** — the `engine` parameter is ignored for European style; it always uses `AnalyticEuropeanEngine`.
- **Portfolio endpoint serializes requests** — the entire portfolio loop holds `_QL_LOCK` to protect QuantLib global state. Throughput is lower than a true concurrent service, but correctness is guaranteed.
- **Max 500 legs per portfolio** — hard limit to prevent accidental denial-of-self.
- **Bounded bump ranges** — `bump_spot_rel` ∈ (0, 0.1], `bump_vol_abs` ∈ (0, 0.01], `bump_rate_abs` ∈ (0, 0.01].
- **No database or persistence** — all state is in-memory and per-request.
- **No auth, TLS, or rate limiting** — binds to `127.0.0.1` only.

## Sample Workbook

The file `sample/DeskPricer_Bitcoin_Demo.xlsx` is a ready-to-run Excel workbook that demonstrates:

- **Greeks sheet**: a European call on Bitcoin — $75K spot, $100K strike, 3M expiry, 50% vol — with live `WEBSERVICE` + `FILTERXML` formulas pulling price, delta, gamma, vega, theta, rho, and charm.
- **ImpliedVol sheet**: back out ~68.3% implied vol from a $3,398.71 market price using the `GET /v1/impliedvol` endpoint.
- **PnL Attribution sheet**: decompose PnL when spot rallies $75K → $80K and vol widens 50% → 55%, showing delta, gamma, vega, theta, vanna, volga, and residual buckets.

Open the workbook, start DeskPricer, and the cells populate automatically.
