# DeskPricer API Reference

## Base URL

```
http://127.0.0.1:8765/v1
```

Port is configurable via the `DESK_PRICER_PORT` environment variable.

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
  <service>1.0.0</service>
  <quantlib>1.42</quantlib>
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
| `t` | float > 0 | Yes | Time to expiry in years (ACT/365F) |
| `r` | float | Yes | Continuously compounded risk-free rate |
| `q` | float | Yes | Continuously compounded dividend yield |
| `v` | float > 0 | Yes | Black volatility (decimal) |
| `type` | `call` / `put` | Yes | Option type |
| `style` | `european` / `american` | Yes | Option style |
| `engine` | enum | No | `analytic`, `binomial_crr`, `binomial_jr`. Default: `analytic` for European, `binomial_crr` for American |
| `steps` | int (10–5000) | No | Tree steps. Default: 400 |
| `valuation_date` | ISO date | No | Defaults to today |
| `bump_spot_rel` | float | No | Relative spot bump for bump-and-revalue Greeks. Default: 0.01 |
| `bump_vol_abs` | float | No | Absolute vol bump. Default: 0.0001 |
| `bump_rate_abs` | float | No | Absolute rate bump. Default: 0.0001 |

#### Default Engine Selection

- `style=european` → `analytic` (Black-Scholes-Merton closed form)
- `style=american` → `binomial_crr` with 400 steps (Cox-Ross-Rubinstein)

#### Greek Conventions

| Greek | Definition | Unit |
|-------|-----------|------|
| `delta` | ∂V/∂S | absolute |
| `gamma` | ∂²V/∂S² | absolute |
| `vega` | ∂V/∂σ | per **1% vol point** (standard market convention) |
| `theta` | ∂V/∂t | per **calendar day** (annual theta / 365) |
| `rho` | ∂V/∂r | per **1% rate point** (standard market convention) |
| `charm` | ∂²V/∂S∂t = ∂delta/∂t | per **calendar day** (delta today − delta tomorrow)

#### Response (XML)

```xml
<greeks>
  <meta>
    <service_version>1.0.0</service_version>
    <quantlib_version>1.42</quantlib_version>
    <engine>analytic</engine>
    <valuation_date>2026-04-20</valuation_date>
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
    <price>3.141592</price>
    <delta>0.423100</delta>
    <gamma>0.031400</gamma>
    <vega>0.187806</vega>
    <theta>-0.026009</theta>
    <rho>0.085719</rho>
    <charm>0.000158</charm>
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
      "style": "european"
    }
  ]
}
```

#### Response (JSON)

```json
{
  "meta": {
    "service_version": "1.0.0",
    "quantlib_version": "1.42"
  },
  "legs": [
    {
      "id": "L1",
      "price": 3.14,
      "delta": 0.42,
      "gamma": 0.031,
      "vega": 0.196,
      "theta": -0.029,
      "rho": 0.130,
      "charm": 0.0002
    }
  ],
  "aggregate": {
    "delta": 4.2,
    "gamma": 0.31,
    "vega": 1.96,
    "theta": -0.29,
    "rho": 1.30,
    "charm": 0.0004
  }
}
```

Aggregate = Σ qty × per-leg Greek.

---

### `GET /v1/impliedvol`

Solve for implied volatility given an observed market price.

#### Query Parameters

| Name | Type | Required | Description |
|------|------|----------|-------------|
| `s` | float > 0 | Yes | Spot price |
| `k` | float > 0 | Yes | Strike |
| `t` | float > 0 | Yes | Time to expiry in years (ACT/365F) |
| `r` | float | Yes | Continuously compounded risk-free rate |
| `q` | float | Yes | Continuously compounded dividend yield |
| `price` | float > 0 | Yes | Observed market price of the option |
| `type` | `call` / `put` | Yes | Option type |
| `style` | `european` / `american` | Yes | Option style |
| `engine` | enum | No | `analytic`, `binomial_crr`, `binomial_jr`. Default: `analytic` for European, `binomial_crr` for American |
| `steps` | int (10–5000) | No | Tree steps. Default: 400 |
| `valuation_date` | ISO date | No | Defaults to today |
| `accuracy` | float | No | Brent solver accuracy. Default: `1e-4` |
| `max_iterations` | int | No | Max solver iterations. Default: `1000` |

#### Response (XML)

```xml
<impliedvol>
  <meta>
    <service_version>1.0.0</service_version>
    <quantlib_version>1.42</quantlib_version>
    <engine>analytic</engine>
    <valuation_date>2026-04-20</valuation_date>
  </meta>
  <inputs>
    <s>100.0</s>
    <k>100.0</k>
    <t>0.5</t>
    <r>0.05</r>
    <q>0.02</q>
    <price>6.877605</price>
    <type>call</type>
    <style>european</style>
  </inputs>
  <outputs>
    <implied_vol>0.199984</implied_vol>
    <npv_at_iv>6.877177</npv_at_iv>
  </outputs>
</impliedvol>
```

**`npv_at_iv`** is the re-priced NPV at the solved vol, provided as a sanity check.

#### Error Cases

- If `price` is outside arbitrage bounds (e.g., below intrinsic value or above max possible), the endpoint returns `400 INVALID_INPUT` with field=`price`.
- If the Brent solver fails to converge, returns `400 INVALID_INPUT`.

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
| 400 | `INVALID_INPUT` | Validation failed |
| 422 | `UNSUPPORTED_COMBINATION` | e.g. `american` + `analytic` |
| 500 | `PRICING_FAILURE` | QuantLib exception |
| 503 | `SERVICE_DEGRADED` | Reserved |
