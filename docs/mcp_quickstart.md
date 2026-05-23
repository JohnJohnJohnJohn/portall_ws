# DeskPricer MCP Quickstart

DeskPricer exposes the same pricing engine as the local HTTP API through **MCP (Model Context Protocol)** over stdio. AI agents (Claude Desktop, Cursor, Continue, etc.) can call deterministic option pricing instead of guessing prices or Greeks.

## Install

From PyPI:

```bash
pip install deskpricer
```

This installs the `deskpricer-mcp` MCP command alongside the `deskpricer` HTTP server.

For development from a clone:

```bash
pip install -e .
```

## Cursor configuration

Add to `~/.cursor/mcp.json`:

```json
{
  "mcpServers": {
    "deskpricer": {
      "command": "deskpricer-mcp",
      "args": []
    }
  }
}
```

Use the full path to `deskpricer-mcp` if it is not on your PATH. Reload Cursor after saving.

## Claude Desktop configuration

Add to `claude_desktop_config.json`:

```json
{
  "mcpServers": {
    "deskpricer": {
      "command": "deskpricer-mcp"
    }
  }
}
```

If `deskpricer-mcp` is not on your PATH, use the full path to the executable in your virtualenv, for example:

```json
{
  "mcpServers": {
    "deskpricer": {
      "command": "/path/to/venv/bin/deskpricer-mcp"
    }
  }
}
```

Restart Claude Desktop after editing the config.

## Cursor / other MCP clients

Use the same command (`deskpricer-mcp`) in your client's MCP server settings. DeskPricer communicates over **stdio** only — no HTTP port is required for MCP.

## Environment variables

| Variable | Default | Purpose |
|----------|---------|---------|
| `DESKPRICER_WORKERS` | `min(4, cpu_count())` | Process pool size for QuantLib pricing |
| `DESKPRICER_INLINE` | unset | Set to `1` to run pricing in-process (testing only) |

## Tool catalog

All tools return **JSON text** in MCP `TextContent`, matching the HTTP API response shapes.

### `price_option`

**HTTP:** `GET /v1/greeks`

Price one vanilla call or put. Returns price and Greeks (delta, gamma, vega, theta, rho, charm) **per one contract**.

**Key inputs:** `s`, `k`, `t`, `r`, `q`, `v`, `type` (`call`|`put`), `style` (`european`|`american`).

**Optional:** `b` (borrow cost), `engine`, `steps`, `valuation_date`, `calendar`, bump parameters.

**Example arguments:**

```json
{
  "s": 100,
  "k": 105,
  "t": 0.25,
  "r": 0.05,
  "q": 0.02,
  "v": 0.20,
  "type": "call",
  "style": "european",
  "calendar": "null"
}
```

### `implied_volatility`

**HTTP:** `GET /v1/impliedvol`

Solve for implied vol given an observed market `price`.

**Key inputs:** same as `price_option`, plus `price` (observed premium).

**Example:** back out vol from a $3.40 mid on a 3M ATM call.

### `pnl_attribution`

**HTTP:** `GET /v1/pnl_attribution`

Explain PnL between two market snapshots using delta, gamma, vega, theta, rho; optionally vanna and volga (`cross_greeks: true`).

**Key inputs:** `s_t_minus_1`, `s_t`, `k`, `t_t_minus_1`, `t_t`, rates/yields/vol at both dates, `type`, `style`.

**Optional:** `method` (`backward`|`average`), `cross_greeks`, valuation dates, `qty` (reporting only — outputs stay per unit).

### `portfolio_greeks`

**HTTP:** `POST /v1/portfolio/greeks`

Price up to **500 legs**; returns unit Greeks per leg and a **qty-weighted aggregate**.

**Key inputs:** `legs[]` with `id`, `qty`, and the same fields as `price_option` per leg.

**Example:** long 2× ATM call + short 1× ATM put (risk reversal).

## Conventions agents must follow

- **Decimals, not percentages:** `r=0.05`, `q=0.02`, `v=0.20` (not 5, 2, 20).
- **Time:** `t` is years on ACT/365; values below ~1 day are floored to 1 calendar day.
- **Greek units:** vega and rho are per **1% point**; theta and charm are per **1 calendar day**.
- **Per-unit outputs:** multiply by position size yourself except in `portfolio_greeks` aggregate (which applies `qty`).
- **Engines:** `european` → `analytic`; `american` → `binomial_crr` (default) or `binomial_jr`.
- **Calendars:** `hong_kong` (default), `us_nyse`, `us_settlement`, `united_kingdom`, `null`.

## Validation prompt

After connecting the server, ask your agent:

> Use DeskPricer to price a 3-month European call: spot 100, strike 105, vol 20%, rate 5%, dividend 2%.

Expected: a JSON result with `greeks.outputs.price` > 0 and `delta` between 0 and 1.

## Errors

Failed tool calls return JSON:

```json
{
  "error": {
    "code": "INVALID_INPUT",
    "message": "...",
    "field": "s"
  }
}
```

Codes mirror the HTTP API: `INVALID_INPUT`, `UNSUPPORTED_COMBINATION`, `PRICING_FAILURE`, `NOT_FOUND`.

## HTTP vs MCP

| Transport | When to use |
|-----------|-------------|
| MCP (`deskpricer-mcp`) | AI agents, Claude Desktop, Cursor |
| HTTP (`deskpricer`) | Excel `WEBSERVICE`, curl, local integrations |

Both paths call the same `pricing_service` layer and return the same numeric results.
