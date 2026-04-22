# DeskPricer v2.2.0

Local HTTP pricing microservice for vanilla European and American equity options. Designed for Excel `WEBSERVICE` + `FILTERXML` integration — no VBA, no Bloomberg terminal calls inside the service.

> **Design intent:** DeskPricer is a **local-only tool** for personal desk pricing and option analytics. It is **not intended to be run or served as a public/server-style service**. All design choices — localhost binding, no auth, no TLS, no rate limiting, XML-by-default — reflect this.

---

## Quickstart

Go from clean clone to a working pricing call in under 5 minutes:

```powershell
# 1. Install
python -m venv .venv
.venv\Scripts\activate
pip install -e ".[dev]"

# 2. Run
python -m deskpricer.main

# 3. Test with curl
curl "http://127.0.0.1:8765/v1/greeks?s=100&k=105&t=0.25&r=0.05&q=0.02&v=0.20&type=call&style=european"

# 4. Test with Excel (copy into a cell)
# =FILTERXML(WEBSERVICE("http://127.0.0.1:8765/v1/greeks?s=100&k=105&t=0.25&r=0.05&q=0.02&v=0.20&type=call&style=european"),"//outputs/price")
```

Expected output for the curl call (XML):

```xml
<?xml version="1.0" encoding="UTF-8"?>
<greeks>
  <meta>
    <service_version>2.2.0</service_version>
    <quantlib_version>1.42.1</quantlib_version>
    <engine>analytic</engine>
    <valuation_date>2026-04-22</valuation_date>
  </meta>
  <inputs>
    <s>100.0</s>
    <k>105.0</k>
    <t>0.25</t>
    <r>0.05</r>
    <q>0.02</q>
    <v>0.2</v>
    <type>call</type>
    <style>european</style>
  </inputs>
  <outputs>
    <price>2.288743</price>
    <delta>0.356244</delta>
    <gamma>0.037206</gamma>
    <vega>0.185519</vega>
    <theta>-0.023001</theta>
    <rho>0.083111</rho>
    <charm>-0.001241</charm>
  </outputs>
</greeks>
```

For JSON, send `Accept: application/json` or append `?format=json`.

---

## Try the Demo Workbook

Open **`sample/DeskPricer_Bitcoin_Demo.xlsx`** for a ready-to-run example. It contains 3 sheets:

| Sheet | What it shows |
|-------|---------------|
| **Greeks** | Bitcoin European Call — $75K spot, $100K strike, 3M expiry, 50% vol |
| **ImpliedVol** | Back out ~68.3% implied vol from a $3,398.71 market price |
| **PnL Attribution** | Decompose PnL when spot rallies $75K → $80K and vol widens 50% → 55% |

Each sheet has the actual `WEBSERVICE` and `FILTERXML` formulas pre-loaded. Just start DeskPricer and the cells will populate automatically.

---

## What it does

- **Price + Greeks** for single options or multi-leg portfolios
- **Implied volatility** solver (Brent method via QuantLib)
- **PnL attribution** — decompose option PnL into delta, gamma, vega, theta, rho, vanna, volga, and residual
- **XML by default** — Excel `WEBSERVICE` + `FILTERXML` work out of the box; JSON available via `Accept: application/json`
- **Localhost-only** — binds to `127.0.0.1`; no network exposure

---

## Installation Options

### Standalone Executable (Recommended)

Download `DeskPricer_v2.exe` from the [Releases](https://github.com/JohnJohnJohnJohn/portall_ws/releases) page and run:

```powershell
.\DeskPricer_v2.exe
```

The service starts on port `8765`. To use a different port:

```powershell
.\DeskPricer_v2.exe --port 9000
```

### From Source

```powershell
python -m venv .venv
.venv\Scripts\activate
pip install -e ".[dev]"
python -m deskpricer.main
```

---

## Excel User Guide

### Service Status

Check that the service is running before pulling prices:

| Cell | Formula |
|------|---------|
| Status | `=IFERROR(FILTERXML(WEBSERVICE("http://127.0.0.1:8765/v1/health"),"//status"),"DOWN")` |

**Expected output:** `UP`

---

### Example 1: Price a Single Option + Greeks

Assume your sheet has:

| Column | Label | Example Value |
|--------|-------|---------------|
| C | Spot | `100` |
| K | Strike | `105` |
| T | Time to expiry (years) | `0.25` |
| R | Risk-free rate | `0.05` |
| Q | Dividend yield | `0.02` |
| V | Volatility | `0.20` |
| TYPE | Option type | `call` |
| STYLE | Style | `european` |

**Step 1 — Build the URL in a helper cell (e.g. H2):**

```excel
="http://127.0.0.1:8765/v1/greeks?s="&C2&"&k="&K2&"&t="&T2&"&r="&R2&"&q="&Q2&"&v="&V2&"&type="&TYPE2&"&style="&STYLE2
```

**Step 2 — Fetch the raw XML (e.g. I2):**

```excel
=WEBSERVICE(H2)
```

**Step 3 — Extract values into individual cells:**

| Output | Formula |
|--------|---------|
| Price | `=VALUE(FILTERXML(I2,"//outputs/price"))` |
| Delta | `=VALUE(FILTERXML(I2,"//outputs/delta"))` |
| Gamma | `=VALUE(FILTERXML(I2,"//outputs/gamma"))` |
| Vega  | `=VALUE(FILTERXML(I2,"//outputs/vega"))` |
| Theta | `=VALUE(FILTERXML(I2,"//outputs/theta"))` |
| Rho   | `=VALUE(FILTERXML(I2,"//outputs/rho"))` |
| Charm | `=VALUE(FILTERXML(I2,"//outputs/charm"))` |

**Expected output for the example above:**

| Greek | Value |
|-------|-------|
| Price | `2.288743` |
| Delta | `0.356244` |
| Gamma | `0.037206` |
| Vega  | `0.185519` |
| Theta | `-0.023001` |
| Rho   | `0.083111` |
| Charm | `-0.001241` |

> **Tip:** Wrap each `FILTERXML` in `IFERROR(...,"ERR")` so one bad row doesn't break the whole sheet.

---

### Example 2: Back Out Implied Volatility from Market Price

You observe a mid-market price of `6.50` for the same option and want the implied vol.

**Step 1 — Build the URL (e.g. H2):**

```excel
="http://127.0.0.1:8765/v1/impliedvol?s="&C2&"&k="&K2&"&t="&T2&"&r="&R2&"&q="&Q2&"&price=6.50&type="&TYPE2&"&style="&STYLE2
```

**Step 2 — Extract implied vol:**

```excel
=VALUE(FILTERXML(WEBSERVICE(H2),"//outputs/implied_vol"))
```

**Expected output:** `0.417484` (≈ 41.7 % vol)

---

### Example 3: PnL Attribution

You had a position yesterday (t-1) and want to explain today's PnL.

Assume:

| Field | t-1 Value | t Value |
|-------|-----------|---------|
| Spot | `100` | `102` |
| Time | `0.25` | `0.2466` |
| Vol | `0.20` | `0.22` |
| Rate | `0.05` | `0.05` |
| Div | `0.02` | `0.02` |
| Qty | `10` | — |

**Step 1 — Build the URL:**

```excel
="http://127.0.0.1:8765/v1/pnl_attribution?s_t_minus_1=100&s_t=102&k=105&t_t_minus_1=0.25&t_t=0.2466&r_t_minus_1=0.05&r_t=0.05&q_t_minus_1=0.02&q_t=0.02&v_t_minus_1=0.2&v_t=0.22&type=call&style=european&qty=10&cross_greeks=true"
```

**Step 2 — Extract attribution buckets:**

| Bucket | Formula |
|--------|---------|
| Actual PnL | `=VALUE(FILTERXML(WEBSERVICE(H2),"//outputs/actual_pnl"))` |
| Delta PnL | `=VALUE(FILTERXML(WEBSERVICE(H2),"//outputs/delta_pnl"))` |
| Gamma PnL | `=VALUE(FILTERXML(WEBSERVICE(H2),"//outputs/gamma_pnl"))` |
| Vega PnL | `=VALUE(FILTERXML(WEBSERVICE(H2),"//outputs/vega_pnl"))` |
| Theta PnL | `=VALUE(FILTERXML(WEBSERVICE(H2),"//outputs/theta_pnl"))` |
| Rho PnL | `=VALUE(FILTERXML(WEBSERVICE(H2),"//outputs/rho_pnl"))` |
| Vanna PnL | `=VALUE(FILTERXML(WEBSERVICE(H2),"//outputs/vanna_pnl"))` |
| Volga PnL | `=VALUE(FILTERXML(WEBSERVICE(H2),"//outputs/volga_pnl"))` |
| Residual | `=VALUE(FILTERXML(WEBSERVICE(H2),"//outputs/residual_pnl"))` |

**Expected output:**

| Bucket | Value |
|--------|-------|
| price_t_minus_1 | `2.288743` |
| price_t | `3.448643` |
| Actual PnL | `11.601` |
| Delta PnL | `7.125` |
| Gamma PnL | `0.744` |
| Vega PnL | `3.710` |
| Theta PnL | `-0.230` |
| Rho PnL | `0.0` |
| Vanna PnL | `0.343` |
| Volga PnL | `0.031` |
| Explained PnL | `11.724` |
| Residual | `-0.123` |

> The `residual_pnl` captures higher-order effects and model differences between t-1 and t. Enable `cross_greeks=true` to include vanna and volga contributions.

---

### Example 4: Portfolio / Bulk Greeks

For book-level aggregation, use the `POST /v1/portfolio/greeks` endpoint via Power Query or a small VBA helper. The endpoint accepts a JSON body with multiple legs and returns per-leg and aggregate Greeks.

See [`docs/api.md`](docs/api.md) for the full request/response schema.

---

## Greek Conventions

| Greek | Unit | Notes |
|-------|------|-------|
| Delta | absolute | Per $1 spot move |
| Gamma | absolute | Per $1 spot move |
| Vega | per **1 vol point** | i.e. decimal vol × 100 |
| Theta | per **calendar day** | Annual theta / 365 |
| Rho | per **1% rate point** | i.e. decimal rate × 100 |
| Charm | per **calendar day** | ∂delta/∂t (delta tomorrow − delta today) |

---

## Log Location and Structured Logging

- **Log path**: `DESKPRICER_LOG_DIR` env var overrides the default (`C:\ProgramData\DeskPricer\logs` on Windows, `~/.local/share/deskpricer/logs` elsewhere).
- **Format**: Uses Python's stdlib `logging` module with a custom JSON formatter and `RotatingFileHandler` (10 MB rotation, 5 backups). This replaces the earlier hand-rolled `open()` approach.
- **Change the path**:
  ```powershell
  $env:DESKPRICER_LOG_DIR = "C:\MyLogs"
  python -m deskpricer.main
  ```

---

## Troubleshooting

### QuantLib install failures
If `pip install` fails on QuantLib, ensure you have a C++ compiler and CMake, or use a pre-built wheel. See `docs/operator_guide.md` for detailed steps.

### Zero-DTE surprises
`t=0` is floored to 1 calendar day to prevent QuantLib collapse. You will get a small time-value premium rather than pure intrinsic. This is intentional.

### Engine/style mismatches
- `style=european` → only `engine=analytic`
- `style=american` → only `engine=binomial_crr` or `binomial_jr`

### XML vs JSON
Excel receives XML by default. For JSON, send `Accept: application/json` or `?format=json`.

### Error codes
| Code | Meaning |
|------|---------|
| `INVALID_INPUT` | Business-rule or schema validation failed |
| `UNSUPPORTED_COMBINATION` | Engine/style mismatch |
| `PRICING_FAILURE` | Unexpected internal error (no traceback leaked) |

---

## Limitations

- **No FD engine** — analytic BSM for Europeans, binomial CRR/JR for Americans only.
- **Portfolio serializes via `_QL_LOCK`** — max 500 legs; throughput is limited by QuantLib's global state.
- **Bounded bump ranges** — `bump_spot_rel` ≤ 0.1, `bump_vol_abs` ≤ 0.01, `bump_rate_abs` ≤ 0.01.
- **No database or persistence** — all state is in-memory per-request.
- **No auth, TLS, or rate limiting** — local-only by design.

---

## Running Tests

```powershell
pytest tests -v
```

---

## Design Decisions

### Local-only by design

DeskPricer is built as a **personal desktop tool**, not a public API. This explains every intentional omission:

- **No authentication / authorization** — only `127.0.0.1` can reach the service.
- **No TLS / HTTPS** — local loopback traffic is unencrypted by design.
- **No rate limiting** — the `asyncio.Lock` serializes requests only to protect QuantLib's global `Settings.instance()` state, not to throttle users.
- **No Swagger / Redoc** — OpenAPI docs are hidden in production builds to reduce attack surface.
- **XML by default** — Excel's `WEBSERVICE` function does not send `Accept: application/json`.

If you need any of these features, DeskPricer is the wrong tool. Use a proper API gateway or a full-featured pricing platform.

### Why all requests are serialized (`asyncio.Lock`)

QuantLib's Python bindings rely on a single process-global `Settings.instance()` object. There is no supported way to create isolated per-request QuantLib contexts in the Python API. Holding an `asyncio.Lock` around every pricing call guarantees that concurrent requests never corrupt each other's evaluation date or global state. The tradeoff is lower throughput for portfolio requests, which is acceptable for a desk-pricing tool where correctness matters more than concurrency. A future refactor could explore a `ProcessPoolExecutor` to parallelize work across separate Python processes.

### Why PnL attribution uses GET with many query params

Excel's `WEBSERVICE` function only supports HTTP GET. Since the primary user of this service is Excel, the `GET /v1/pnl_attribution` endpoint is designed specifically for `WEBSERVICE` compatibility. Programmatic clients that need a cleaner JSON body can use `POST /v1/portfolio/greeks` today; a `POST` alternative for PnL attribution may be added in a future release.

---

## Project Structure

```
DeskPricer/
├── pyproject.toml
├── README.md
├── requirements.txt
├── src/deskpricer/          # FastAPI app + pricing core
│   ├── app.py               # Thin composition root
│   ├── routers/             # APIRouter modules
│   ├── services/            # Pricing orchestration + QL lock
│   ├── pricing/             # QuantLib pricing engines
│   ├── schemas.py           # Pydantic models
│   ├── responses.py         # XML/JSON serializers
│   ├── errors.py            # Custom exceptions
│   ├── logging_config.py    # Structured JSON logging
│   └── main.py              # Uvicorn entrypoint
├── tests/                   # pytest + hypothesis
├── tests/fixtures/          # Regression baseline JSONs
├── scripts/                 # Build + fixture generation
├── sample/                  # Demo Excel workbook
└── docs/                    # API ref + operator guide
```

## License

MIT
