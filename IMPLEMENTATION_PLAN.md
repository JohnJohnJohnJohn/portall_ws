# DeskPricer — Implementation Plan

> Version 1.0 · May 2026  
> Milestone 1 target: MCP-ready and listed on Smithery.ai / mcp.so

---

## Guiding Principles

- **Additive, not destructive**: every change extends the existing codebase; nothing in the current Excel/local-HTTP workflow breaks.
- **Correctness before scale**: the QuantLib pricing core is not touched until the MCP layer is working and validated.
- **Ship fast, iterate**: Milestone 1 is a thin MCP wrapper over existing endpoints — not a rewrite.
- **1–2 hours/day budget**: tasks are scoped so no single session exceeds ~2 hours of focused work.

---

## Milestone 1 — MCP-Ready & Registry Listed

**Goal**: Any MCP-compatible agent (Claude Desktop, Cursor, Continue, etc.) can add DeskPricer as a tool server and successfully call `price_option`, `implied_volatility`, `pnl_attribution`, and `portfolio_greeks`.

**Definition of done**: Listed and installable on Smithery.ai and mcp.so with a passing health check.

**Status (May 2026):** Engineering complete. PyPI publish live (`pip install deskpricer`). MCP validated in Inspector and Cursor. Registry submissions in flight (mcp.so pending; awesome-mcp-servers PR pending). Smithery deferred until MCPB packaging (Smithery’s current stdio path requires a `.mcpb` bundle — see Phase 1C notes). Phase 1D launch comms optional follow-up.

---

### Phase 1A — QuantLib Concurrency Fix (Pre-requisite)

The current `asyncio.Lock` serializes all requests in a single process. This is acceptable for local use but will produce unacceptable latency under concurrent agent calls. Fix this before exposing the service externally.

**Task 1A-1: Replace asyncio.Lock with ProcessPoolExecutor**

- Add a `src/deskpricer/worker.py` module that wraps the pricing core in a worker function suitable for `ProcessPoolExecutor`.
- In `services/pricing_service.py`, replace the `asyncio.Lock` block with a `loop.run_in_executor(pool, worker_fn, params)` call.
- Default pool size: `min(4, os.cpu_count())`; configurable via `DESKPRICER_WORKERS` env var.
- Each worker process has its own isolated QuantLib `Settings.instance()` — no shared global state.
- Regression test: all existing `pytest tests -v` must pass unchanged.

**Task 1A-2: Pure-Python BSM fallback for Europeans (optional but recommended)**

- Add `src/deskpricer/pricing/bsm_fast.py` — a pure numpy/scipy BSM implementation for European calls/puts.
- When `style=european` and `engine=analytic`, route to `bsm_fast` instead of QuantLib.
- This path is thread-safe, sub-millisecond, and removes QuantLib as a bottleneck for the most common case.
- QuantLib remains the authoritative engine for American options and IV solving.
- Validate outputs match QuantLib to 6 decimal places in a new `tests/test_bsm_fast_parity.py`.

**Estimated effort**: 1 focused weekend (4–6 hours total)

---

### Phase 1B — MCP Transport Layer

**Task 1B-1: Add `mcp` dependency**

```toml
# pyproject.toml — add to [project.dependencies]
"mcp>=1.0"
```

**Task 1B-2: Create `src/deskpricer/mcp_server.py`**

This is the core new file. It creates an MCP `Server` instance and registers one tool per pricing endpoint. Each tool:
- Declares a JSON schema for its input parameters (mirroring existing Pydantic schemas)
- Calls the existing pricing service directly (not via HTTP — internal function call for efficiency)
- Returns a structured `TextContent` result (JSON string of the existing response model)

Skeleton structure:

```python
from mcp.server import Server
from mcp.server.stdio import stdio_server
from mcp.types import Tool, TextContent
import json

app = Server("deskpricer")

@app.list_tools()
async def list_tools():
    return [
        Tool(
            name="price_option",
            description=(
                "Price a vanilla European or American equity option and return "
                "full Greeks (delta, gamma, vega, theta, rho, charm) using "
                "QuantLib. Supports borrow cost, dividend yield, and HK calendar."
            ),
            inputSchema={ ... }  # mirrors GreeksRequest Pydantic schema
        ),
        Tool(name="implied_volatility", description="...", inputSchema={ ... }),
        Tool(name="pnl_attribution", description="...", inputSchema={ ... }),
        Tool(name="portfolio_greeks", description="...", inputSchema={ ... }),
    ]

@app.call_tool()
async def call_tool(name: str, arguments: dict):
    if name == "price_option":
        result = await pricing_service.compute_greeks(**arguments)
        return [TextContent(type="text", text=json.dumps(result))]
    # ... other tools

async def main():
    async with stdio_server() as (read, write):
        await app.run(read, write, app.create_initialization_options())
```

**Task 1B-3: Add MCP entrypoint to `pyproject.toml`**

```toml
[project.scripts]
deskpricer-mcp = "deskpricer.mcp_server:main"
```

This allows users to run the MCP server as:
```bash
pip install deskpricer
deskpricer-mcp
```

**Task 1B-4: Add `claude_desktop_config` example to docs**

Create `docs/mcp_quickstart.md` with copy-paste config for Claude Desktop:

```json
{
  "mcpServers": {
    "deskpricer": {
      "command": "deskpricer-mcp"
    }
  }
}
```

And a validation prompt users can run in Claude to confirm it works:
> *"Use DeskPricer to price a 3-month European call: spot 100, strike 105, vol 20%, rate 5%, dividend 2%."*

**Estimated effort**: 1 focused weekend (4–6 hours total)

---

### Phase 1C — Smithery / mcp.so Registration Requirements

Smithery and mcp.so both require specific metadata to list a server. Complete all of the following before submitting.

**Task 1C-1: Add `smithery.yaml` to repo root**

```yaml
name: deskpricer
displayName: DeskPricer — Options Pricing
description: >
  QuantLib-backed MCP server for vanilla option pricing, Greeks,
  implied volatility, PnL attribution, and portfolio Greeks.
  Supports European and American options, borrow cost, dividend yield,
  and Hong Kong calendar. Deterministic, auditable, hallucination-free.
version: 3.4.0
homepage: https://github.com/JohnJohnJohnJohn/portall_ws
license: MIT
categories:
  - finance
  - quantitative
  - pricing
tags:
  - options
  - greeks
  - quantlib
  - derivatives
  - pnl-attribution
startCommand:
  type: stdio
  command: deskpricer-mcp
```

**Task 1C-2: Ensure `pyproject.toml` is PyPI-publishable**

- Keep `project.name = "deskpricer"` (PyPI package name; MCP command remains `deskpricer-mcp`)
- Add `project.description`, `project.readme`, `project.license`, `project.urls`
- Add classifiers: `Topic :: Office/Business :: Financial`, `Topic :: Scientific/Engineering :: Mathematics`
- Run `python -m build` and verify the wheel builds cleanly
- Publish to PyPI (`twine upload dist/*`) — Smithery resolves packages from PyPI

**Task 1C-3: Add GitHub repo topics**

Add the following topics to the GitHub repo settings:
`mcp-server`, `quantlib`, `options-pricing`, `greeks`, `derivatives`, `fastapi`, `finance`, `pnl-attribution`

**Task 1C-4: Update README for MCP audience**

Add a new top-level section to `README.md` immediately after the intro:

```markdown
## Use with AI Agents (MCP)

DeskPricer is available as an MCP server. Add it to Claude Desktop, Cursor, or any MCP-compatible agent:

\`\`\`bash
pip install deskpricer
\`\`\`

Then add to your `claude_desktop_config.json`:

\`\`\`json
{
  "mcpServers": {
    "deskpricer": { "command": "deskpricer-mcp" }
  }
}
\`\`\`

See [docs/mcp_quickstart.md](docs/mcp_quickstart.md) for full setup and example prompts.
```

**Task 1C-5: Submit to registries**

- **mcp.so**: submit via https://mcp.so/submit (Type: MCP Server, repo URL, stdio config JSON)
- **awesome-mcp-servers**: open a PR to [https://github.com/punkpeye/awesome-mcp-servers](https://github.com/punkpeye/awesome-mcp-servers) under **Finance & Fintech**
- **Smithery**: deferred — current docs at [smithery.ai/docs/build/publish](https://smithery.ai/docs/build/publish) require either a public Streamable HTTP URL or an MCPB (`.mcpb`) bundle for stdio; `smithery.yaml` alone is not sufficient. Revisit when MCPB packaging is added.

**Estimated effort**: 2–3 hours (mostly admin, not engineering)

---

### Phase 1D — Launch Comms

**Task 1D-1: Write and publish launch post**

Target platforms: X (Twitter) and LinkedIn. Suggested framing:

> *I built an MCP server that gives AI agents access to QuantLib-backed options pricing — price + full Greeks, IV solving, and PnL attribution (delta/gamma/vega/theta/vanna/volga). No Bloomberg needed. Open source, runs locally. [link]*

Tag: `#MCP #QuantLib #Options #AlgoTrading #LLM #FinTech`

**Task 1D-2: Post to relevant communities**

- r/algotrading — frame as "options pricing tool for LLM agents"
- r/MachineLearning / r/LocalLLaMA — frame as "finance MCP server"
- Quant Finance Discord servers
- MCP-specific Discord / Slack channels (Anthropic developer community)

**Estimated effort**: 1–2 hours

---

## Milestone 1 Checklist

```
[x] 1A-1  ProcessPoolExecutor replaces asyncio.Lock
[x] 1A-2  Pure-Python BSM fast path for Europeans (optional)
[x] 1B-1  mcp dependency added to pyproject.toml
[x] 1B-2  src/deskpricer/mcp_server.py created and tested
[x] 1B-3  deskpricer-mcp entrypoint in pyproject.toml
[x] 1B-4  docs/mcp_quickstart.md created
[x] 1C-1  smithery.yaml added to repo root
[x] 1C-2  pyproject.toml PyPI-publishable; package published (pypi.org/project/deskpricer)
[x] 1C-3  GitHub repo topics updated
[x] 1C-4  README MCP section added
[~] 1C-5  Registry listings (see breakdown below)
[ ] 1D-1  Launch post published on X + LinkedIn          (optional follow-up)
[ ] 1D-2  Posted to algotrading / MCP communities        (optional follow-up)
```

### 1C-5 registry breakdown

```
[x] 1C-5a  mcp.so — submitted (pending approval)
[x] 1C-5b  awesome-mcp-servers — PR opened (pending merge)
[ ] 1C-5c  Smithery — deferred (MCPB bundle required; see 1C-5 notes above)
```

**Milestone 1 engineering gate:** PASSED (261 tests; MCP + PyPI + docs complete).  
**Milestone 1 discovery gate:** IN PROGRESS (awaiting mcp.so / awesome-mcp-servers approval).

---

## Milestone 2 — Community Traction (Month 2–3)

Once listed, focus shifts from building to growing.

- Monitor GitHub issues; respond within 48 hours
- Add a `CONTRIBUTING.md` to encourage community PRs
- Track Smithery install count and GitHub star velocity weekly
- Consider adding one high-demand feature based on issue feedback (likely: vol surface / term structure, or FX options support)
- Set up a simple email waitlist landing page for the hosted API (Carrd or Notion page + Mailchimp)

**KPI**: 200 GitHub stars, 50 Smithery installs

---

## Milestone 3 — Hosted Beta (Month 4–6)

Triggered when: 200+ stars OR 3+ GitHub issues requesting a hosted/cloud version.

### Architecture Changes for Hosted

1. **Auth layer**: Add API key middleware to FastAPI (validate key against a Postgres/Redis store)
2. **Network binding**: Change `127.0.0.1` → `0.0.0.0`; add TLS termination via Cloudflare or nginx reverse proxy
3. **Rate limiting**: Add `slowapi` (FastAPI rate limiter) per API key
4. **Usage metering**: Log each request with key + timestamp to Postgres; expose usage endpoint for Stripe metered billing
5. **Deployment**: Single VPS (Hetzner CX22 or equivalent, ~€5/month); Docker container; GitHub Actions CD pipeline

### Billing

- Stripe metered billing — charge per 1,000 API calls above free tier
- Stripe Customer Portal for self-serve plan management
- Lemon Squeezy as alternative if Stripe tax handling is preferred

**KPI**: 10 paying Pro users ($19/month tier)

---

## Milestone 4 — Extended Models & Enterprise Pipeline (Year 2)

- Add barrier options (knock-in/knock-out) — QuantLib `BarrierOption`
- Add digital/binary options
- Add vol surface endpoint (term structure + smile, SABR or SVI parametrization)
- Outreach to HK prop desks and family offices via personal network
- Prepare a one-page commercial deck for enterprise prospects

**KPI**: $500 MRR, 1 enterprise conversation in progress

---

## Non-Goals (Explicitly Out of Scope)

- No investment advice or trade recommendations — ever
- No AUM management or client money
- No regulated activity requiring SFC licence
- No Bloomberg data redistribution
- No UI/dashboard (API-first always)
