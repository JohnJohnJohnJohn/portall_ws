# DeskPricer API Reference

## Base URL

```
http://127.0.0.1:8765/v1
```

Port is configurable via the `DESKPRICER_PORT` environment variable.

## Content Negotiation

- **Default:** XML (`application/xml; charset=utf-8`) for Excel `FILTERXML` compatibility.
- **JSON:** Send `Accept: application/json` or append `?format=json`.

---

## Endpoints

### `GET /v1/health`

Liveness probe.

**Response (XML):**
```xml
<health>
  <status>UP</status>
  <uptime_seconds>12345</uptime_seconds>
</health>
```

### `GET /v1/version`

Version metadata.

**Response (XML):**
```xml
<version>
  <service>2.5.1</service>
  <quantlib>1.42.1</quantlib>
  <python>3.12.7</python>
</version>
```

### `GET /v1/greeks`

Price a single vanilla option and return Greeks.

#### Query Parameters

| Name | Type | Required | Description |
|------|------|----------|-------------|
| `s` | float > 0 | Yes | Spot price |
| `k` | float > 0 | Yes | Strike |
| `t` | float ≥ 0 | Yes | Time to expiry in years (ACT/365F). Values < 1/365 are floored to 1 trading day |
| `r` | float | Yes | Continuously compounded risk-free rate |
| `q` | float | Yes | Continuously compounded dividend yield |
| `v` | float > 0 | Yes | Black volatility (decimal) |
| `type` | `call` / `put` | Yes | Option type |
| `style` | `european` / `american` | Yes | Option style |
| `engine` | enum | No | `analytic`, `binomial_crr`, `binomial_jr`. Default: `analytic` for European, `binomial_crr` for American |
| `steps` | int (10–5000) | No | Tree steps. Default: 500 |
| `calendar` | enum | No | `hong_kong`, `us_nyse`, `us_settlement`, `united_kingdom`, `null`. Default: `hong_kong` |
| `valuation_date` | ISO date | No | Defaults to today |
| `bump_spot_rel` | float | No | Relative spot bump for bump-and-revalue Greeks. Default: 0.01 |
| `bump_vol_abs` | float | No | Absolute vol bump. Default: 0.001 |
| `bump_rate_abs` | float | No | Absolute rate bump. Default: 0.001 |

#### Default Engine Selection

- `style=european` → `analytic` (Black-Scholes-Merton closed form)
- `style=american` → `binomial_crr` with 500 steps (Cox-Ross-Rubinstein)

> **American early exercise**: American options are priced with early-exercise permitted from the valuation date onward.  This matches the standard convention for listed equity options.

#### Greek Conventions

| Greek | Definition | Unit |
|-------|-----------|------|
| `delta` | ∂V/∂S | absolute |
| `gamma` | ∂²V/∂S² | absolute |
| `vega` | ∂V/∂σ | per **1% vol point** (standard market convention) |
| `theta` | ∂V/∂t | per **trading day** (next-BD revalue − today's price). Negative for a decaying long option. |
| `rho` | ∂V/∂r | per **1% rate point** (standard market convention) |
| `charm` | ∂²V/∂S∂t = ∂delta/∂t | per **trading day** (delta next business day − delta today per the chosen calendar)

> **Rho scope**: `rho` measures sensitivity to the **risk-free rate** (`r`) only.  DeskPricer does not return a dividend-yield rho (`rho_q`).

#### Response (XML)

```xml
<greeks>
  <meta>
    <service_version>2.5.1</service_version>
    <quantlib_version>1.42.1</quantlib_version>
    <engine>analytic</engine>
    <valuation_date>2026-04-22</valuation_date>
  </meta>
  <inputs>
    <s>100.0</s>
    <k>105.0</k>
    <t>0.2466</t>
    <r>0.045</r>
    <q>0.012</q>
    <v>0.22</v>
    <type>call</type>
    <style>european</style>
  </inputs>
  <outputs>
    <price>2.667973</price>
    <delta>0.374319</delta>
    <gamma>0.034621</gamma>
    <vega>0.187806</vega>
    <theta>-0.037672</theta>
    <rho>0.085719</rho>
    <charm>-0.001205</charm>
  </outputs>
</greeks>
```

### `POST /v1/portfolio/greeks`

Bulk endpoint for book-level aggregation.

#### Request Body (JSON)

```json
{
  "valuation_date": "2026-04-20",
  "legs": [
    {
      "id": "L1",
      "qty": 10,
      "s": 100,
      "k": 105,
      "t": 0.25,
      "r": 0.045,
      "q": 0.012,
      "v": 0.22,
      "type": "call",
      "style": "european",
      "calendar": "hong_kong"
    }
  ]
}
```

#### Response (JSON)

```json
{
  "meta": {
    "service_version": "2.5.1",
    "quantlib_version": "1.42.1"
  },
  "legs": [
    {
      "id": "L1",
      "engine": "analytic",
      "price": 2.667973,
      "delta": 0.374319,
      "gamma": 0.034621,
      "vega": 0.187806,
      "theta": -0.037672,
      "rho": 0.085719,
      "charm": -0.001205
    }
  ],
  "aggregate": {
    "price": 26.67973,
    "delta": 3.74319,
    "gamma": 0.34621,
    "vega": 1.87806,
    "theta": -0.26009,
    "rho": 0.85719,
    "charm": -0.01205
  }
}
```

Aggregate = Σ qty × per-leg Greek (including price).

#### Response (XML)

```xml
<portfolio>
  <meta>
    <service_version>2.5.1</service_version>
    <quantlib_version>1.42.1</quantlib_version>
    <valuation_date>2026-04-22</valuation_date>
  </meta>
  <legs>
    <leg>
      <id>L1</id>
      <engine>analytic</engine>
      <price>2.667973</price>
      <delta>0.374319</delta>
      <gamma>0.034621</gamma>
      <vega>0.187806</vega>
      <theta>-0.026009</theta>
      <rho>0.085719</rho>
      <charm>-0.001205</charm>
    </leg>
  </legs>
  <aggregate>
    <price>26.67973</price>
    <delta>3.74319</delta>
    <gamma>0.34621</gamma>
    <vega>1.87806</vega>
    <theta>-0.37532</theta>
    <rho>0.85719</rho>
    <charm>-0.01189</charm>
  </aggregate>
</portfolio>
```

---

### `GET /v1/impliedvol`

Solve for implied volatility given an observed market price.

#### Query Parameters

| Name | Type | Required | Description |
|------|------|----------|-------------|
| `s` | float > 0 | Yes | Spot price |
| `k` | float > 0 | Yes | Strike |
| `t` | float ≥ 0 | Yes | Time to expiry in years (ACT/365F). Values < 1/365 are floored to 1 trading day |
| `r` | float | Yes | Continuously compounded risk-free rate |
| `q` | float | Yes | Continuously compounded dividend yield |
| `price` | float > 0 | Yes | Observed market price of the option |
| `type` | `call` / `put` | Yes | Option type |
| `style` | `european` / `american` | Yes | Option style |
| `engine` | enum | No | `analytic`, `binomial_crr`, `binomial_jr`. Default: `analytic` for European, `binomial_crr` for American |
| `steps` | int (10–5000) | No | Tree steps. Default: 500 |
| `valuation_date` | ISO date | No | Defaults to today |
| `accuracy` | float | No | Brent solver accuracy. Default: `1e-4` |
| `max_iterations` | int | No | Max solver iterations. Default: `1000` |
| `calendar` | enum | No | `hong_kong`, `us_nyse`, `us_settlement`, `united_kingdom`, `null`. Default: `hong_kong` |

#### Response (XML)

```xml
<impliedvol>
  <meta>
    <service_version>2.5.1</service_version>
    <quantlib_version>1.42.1</quantlib_version>
    <engine>analytic</engine>
    <valuation_date>2026-04-22</valuation_date>
  </meta>
  <inputs>
    <s>100.0</s>
    <k>100.0</k>
    <t>0.5</t>
    <r>0.05</r>
    <q>0.02</q>
    <price>6.317050</price>
    <type>call</type>
    <style>european</style>
  </inputs>
  <outputs>
    <implied_vol>0.199986</implied_vol>
    <npv_at_iv>6.316673</npv_at_iv>
  </outputs>
</impliedvol>
```

**`npv_at_iv`** is the re-priced NPV at the solved vol, provided as a sanity check.

#### Error Cases

- If `price` is outside arbitrage bounds (e.g., below intrinsic value or above max possible), the endpoint returns `400 INVALID_INPUT` with field=`price`.
- If the Brent solver fails to converge, returns `400 INVALID_INPUT`.

---

### `GET /v1/pnl_attribution`

Decompose option PnL into delta, gamma, vega, theta, rho, vanna, volga, and residual.

> **Valuation dates**: If both `valuation_date_t_minus_1` and `valuation_date_t` are omitted, both default to today and `trading_days` is set to 1. Provide explicit dates for accurate theta PnL across multi-day holds.

#### Query Parameters

| Name | Type | Required | Description |
|------|------|----------|-------------|
| `s_t_minus_1` | float > 0 | Yes | Spot at t-1 |
| `s_t` | float > 0 | Yes | Spot at t |
| `k` | float > 0 | Yes | Strike |
| `t_t_minus_1` | float ≥ 0 | Yes | Time to expiry at t-1 (floored to 1 trading day) |
| `t_t` | float ≥ 0 | Yes | Time to expiry at t (floored to 1 trading day) |
| `r_t_minus_1` | float | Yes | Rate at t-1 |
| `r_t` | float | Yes | Rate at t |
| `q_t_minus_1` | float | Yes | Div yield at t-1 |
| `q_t` | float | Yes | Div yield at t |
| `v_t_minus_1` | float > 0 | Yes | Vol at t-1 |
| `v_t` | float > 0 | Yes | Vol at t |
| `type` | `call` / `put` | Yes | Option type |
| `style` | `european` / `american` | Yes | Option style |
| `qty` | float | No | Position size. Default: 1.0 |
| `method` | `backward` / `average` | No | Greeks averaging method. Default: `backward` |
| `cross_greeks` | bool | No | Include vanna/volga. Default: `false` |
| `engine` | enum | No | Pricing engine |

#### Cross-Greeks (`cross_greeks=true`)

When `cross_greeks=true`, the PnL attribution adds two second-order terms that capture spot–vol interaction:

| Bucket | Definition | When it matters |
|--------|-----------|-----------------|
| `vanna_pnl` | Vanna × ΔS × Δvol_points | Large simultaneous spot and vol moves (e.g. a rally with vol crush) |
| `volga_pnl` | ½ × Volga × (Δvol_points)² | Large vol-of-vol moves |

**Computation**: Vanna (∂²V/∂S∂σ) and volga (∂²V/∂σ²) are computed via uniform finite differences using the same bump conventions as the main Greeks (`bump_spot_rel=0.01`, `bump_vol_abs=0.001`).  `method=average` averages the cross-Greeks at t−1 and t; `method=backward` uses t−1 only.
| `steps` | int (10–5000) | No | Tree steps. Default: 500 |
| `valuation_date_t_minus_1` | ISO date | No | Defaults to today if both dates omitted |
| `valuation_date_t` | ISO date | No | Defaults to today if both dates omitted |
| `bump_spot_rel` | float | No | Relative spot bump. Default: 0.01 |
| `bump_vol_abs` | float | No | Absolute vol bump. Default: 0.001 |
| `bump_rate_abs` | float | No | Absolute rate bump. Default: 0.001 |

#### Response (XML)

```xml
<pnl_attribution>
  <meta>
    <service_version>2.5.1</service_version>
    <quantlib_version>1.42.1</quantlib_version>
    <valuation_date_t_minus_1>2026-04-19</valuation_date_t_minus_1>
    <valuation_date_t>2026-04-20</valuation_date_t>
    <method>backward</method>
    <trading_days>1</trading_days>
  </meta>
  <inputs>
    <s_t_minus_1>100.0</s_t_minus_1>
    <s_t>102.0</s_t>
    <k>105.0</k>
    <t_t_minus_1>0.25</t_t_minus_1>
    <t_t>0.2466</t_t>
    <r_t_minus_1>0.05</r_t_minus_1>
    <r_t>0.05</r_t>
    <q_t_minus_1>0.02</q_t_minus_1>
    <q_t>0.02</q_t>
    <v_t_minus_1>0.2</v_t_minus_1>
    <v_t>0.22</v_t>
    <type>call</type>
    <style>european</style>
    <qty>10.0</qty>
    <cross_greeks>true</cross_greeks>
  </inputs>
  <outputs>
    <price_t_minus_1>2.288743</price_t_minus_1>
    <price_t>3.448862</price_t>
    <actual_pnl>11.601</actual_pnl>
    <delta_pnl>7.125</delta_pnl>
    <gamma_pnl>0.744</gamma_pnl>
    <vega_pnl>3.710</vega_pnl>
    <theta_pnl>-0.333</theta_pnl>
    <rho_pnl>0.0</rho_pnl>
    <vanna_pnl>0.343</vanna_pnl>
    <volga_pnl>0.031</volga_pnl>
    <explained_pnl>11.621</explained_pnl>
    <residual_pnl>-0.020</residual_pnl>
  </outputs>
</pnl_attribution>
```

> **Per-unit outputs**: All PnL buckets (`delta_pnl`, `gamma_pnl`, `vega_pnl`, `theta_pnl`, `rho_pnl`, `vanna_pnl`, `volga_pnl`, `actual_pnl`, `residual_pnl`) are **per unit**.  The `qty` parameter is accepted for API compatibility but is ignored in calculations.  Position-level scaling is the caller's responsibility.

---

## Error Model

All errors return a consistent body:

**XML:**
```xml
<error>
  <code>INVALID_INPUT</code>
  <message>Volatility must be strictly positive; got -0.1.</message>
  <field>v</field>
</error>
```

| HTTP | Code | Meaning |
|------|------|---------|
| 400 | `INVALID_INPUT` | Business-rule validation failed (e.g. price out of arbitrage bounds) |
| 422 | `INVALID_INPUT` | Schema validation failed (Pydantic) |
| 422 | `UNSUPPORTED_COMBINATION` | e.g. `american` + `analytic` |
| 404 | `NOT_FOUND` | Endpoint not found |
| 405 | `METHOD_NOT_ALLOWED` | HTTP method not allowed |
| 500 | `PRICING_FAILURE` | Unexpected internal error |
