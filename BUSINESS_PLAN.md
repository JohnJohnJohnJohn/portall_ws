# DeskPricer — Business Plan

> Version 1.0 · May 2026  
> Status: Internal planning document — not for public distribution

---

## 1. Executive Summary

DeskPricer is a local HTTP pricing microservice (FastAPI + QuantLib) that delivers QuantLib-backed option prices, Greeks, implied volatility, and PnL attribution via a clean REST API. Originally built as a personal desk tool integrated with Excel, it is being repositioned as an **MCP (Model Context Protocol) server** — a callable tool that AI agents (Claude, Cursor, GPT-based agents, and others) can invoke natively to perform precise, deterministic options pricing.

The business model is **free/open-source first, hosted-paid second**:

1. Publish `deskpricer-mcp` as a free, self-hosted open-source MCP server to build community adoption and registry presence.
2. Launch a hosted cloud tier (`api.deskpricer.io`) once organic user demand justifies the infrastructure investment.
3. Expand to enterprise/white-label contracts for prop desks, family offices, and fintech startups that cannot self-host QuantLib.

The founder retains their primary employment. All activities are structured to avoid conflict of interest or SFC/employer compliance issues: the product is pure educational/analytical tooling with no investment advice, no client solicitation, and no AUM under management.

---

## 2. Problem & Opportunity

### The Problem

AI agents that need to price an option today have three bad options:

- **Ask the LLM directly** — LLMs hallucinate Greeks and produce numerically unreliable results.
- **Call Bloomberg** — requires a terminal licence (>$20,000/year) and is not agent-accessible.
- **Use a general math tool** — requires the agent to implement BSM from scratch with no guarantees of correctness.

There is no production-quality, QuantLib-backed, MCP-native options pricing tool available on any registry as of May 2026.

### The Opportunity

The MCP ecosystem is in early hypergrowth. Smithery.ai, mcp.so, and curated GitHub lists are the primary discovery channels, and **finance/quant tooling is essentially absent**. A well-documented, reliable MCP server for options pricing occupies a near-empty niche with a clearly defined user base: agent developers, quant developers, independent traders, and fintech startups building LLM-powered workflows.

---

## 3. Product

### Core: DeskPricer MCP Server (`deskpricer-mcp`)

An MCP-protocol wrapper over the existing DeskPricer pricing core, exposing the following tools to any MCP-compatible agent:

| MCP Tool Name | Underlying Endpoint | Description |
|---|---|---|
| `price_option` | `GET /v1/greeks` | Price + full Greeks for a single option |
| `implied_volatility` | `GET /v1/impliedvol` | Brent-method IV solver |
| `pnl_attribution` | `GET /v1/pnl_attribution` | Full PnL decomposition (delta, gamma, vega, theta, vanna, volga, residual) |
| `portfolio_greeks` | `POST /v1/portfolio/greeks` | Bulk Greeks for multi-leg portfolios |

All pricing is backed by QuantLib 1.42+ with documented conventions (ACT/365, calendar-day theta, per-vol-point vega, HK calendar support).

### Phase 2: Hosted API (`api.deskpricer.io`)

A cloud-deployed version of the MCP server with:
- API key authentication
- Usage-based billing (Stripe metered)
- Always-warm endpoints (no cold-start latency)
- Higher rate limits than self-hosted defaults

### Phase 3: Extended Model Coverage (Paid Tier)

- Barrier options (knock-in / knock-out)
- Digital / binary options
- Volatility surface construction (term structure + smile interpolation)
- Asian options (Monte Carlo)

---

## 4. Target Market

### Primary: Agent/LLM Developers (Free Tier)

Developers building finance-adjacent AI agents who need a reliable, deterministic pricing oracle. They discover the tool via MCP registries and GitHub, self-host it, and become advocates if the tool is accurate and well-documented.

### Secondary: Independent Quants & Traders (Free → Paid)

Individual traders, small prop desks, and family office analysts who currently price options in Excel or Python notebooks. They value the Excel-native integration (already built) and the MCP interface for AI-assisted workflows.

### Tertiary: Fintech Startups (Paid → Enterprise)

Early-stage fintechs building LLM-powered trading tools, risk dashboards, or advisory platforms that need embeddable pricing without the overhead of licensing and running QuantLib themselves.

---

## 5. Revenue Model

### Phase 1 — Free / Open Source (Months 1–6)

- MIT licence, self-hosted
- Revenue: $0 (intentional — building distribution)
- Cost: minimal (GitHub Actions CI, domain registration)
- Success metric: 200+ GitHub stars, 50+ Smithery installs, 3+ community PRs

### Phase 2 — Hosted API (Months 6–12)

| Tier | Price | Calls/month | Target user |
|---|---|---|---|
| Free | $0 | 1,000 | Evaluation / hobbyist |
| Pro | $19/month | 50,000 | Independent traders, developers |
| Team | $99/month | 500,000 | Small desks, startups |
| Enterprise | Custom | Unlimited + SLA | Prop desks, fintechs |

Conversion driver: latency (hosted is always-warm vs. cold self-hosted), reliability SLA, and access to Phase 3 extended models.

### Phase 3 — Enterprise White-Label (Year 2+)

Annual licence for private deployment + extended model coverage. Target: HKD 50,000–200,000/year per client.

---

## 6. Competitive Landscape

| Competitor | Strength | Weakness vs. DeskPricer |
|---|---|---|
| Bloomberg API | Industry standard, trusted | $20k+/year licence, not agent-accessible |
| QuantLib (raw) | Same pricing core | Not an MCP server; requires Python expertise to deploy |
| Generic math MCP tools | Agent-native | No financial domain knowledge; no validated Greeks |
| Option Alpha / Thinkorswim APIs | Retail-friendly | Tied to specific brokers; not embeddable |
| Open-source BSM scripts | Free | No MCP interface; no PnL attribution; untested |

No direct MCP-native competitor with QuantLib-backed pricing exists on any registry as of the date of this plan.

---

## 7. Compliance & Legal

- **No investment advice**: all outputs are analytical tools. Disclaimers on all endpoints, README, and documentation.
- **No client solicitation**: the product does not solicit trades or manage AUM.
- **SFC / employer OBA**: the business will be disclosed as an Outside Business Activity per standard SFC Code of Conduct requirements. The product is pure technology/analytics — not a regulated activity.
- **Legal entity**: incorporate a Hong Kong private limited company before accepting any payment.
- **Liability limitation**: MIT licence limits warranty; Terms of Service for the hosted API will explicitly disclaim trading-decision liability.

---

## 8. Operating Model

- **Founder time**: 1–2 hours/day maximum
- **Phase 1 labour**: founder only (engineering + community)
- **Phase 2 labour**: founder + 1 part-time contractor for DevOps/infra (once revenue justifies)
- **Phase 3 labour**: founder + contractor + optional BD person for enterprise outreach
- **Infrastructure (Phase 2)**: single VPS (~$20–40/month), Stripe for billing, Cloudflare for edge/DDoS

---

## 9. Risks

| Risk | Likelihood | Mitigation |
|---|---|---|
| MCP standard fragmentation | Medium | Support both stdio and SSE transports; monitor Anthropic roadmap |
| QuantLib scaling ceiling | Medium | Addressed in Milestone 1 via ProcessPoolExecutor + BSM fast path |
| Low paid conversion from free | Medium | Gate extended models (barriers, vol surface) to paid tier |
| Employer compliance objection | Low | OBA disclosure before any revenue; pure analytics positioning |
| Larger player enters niche | Low (near-term) | First-mover registry presence + community moat |

---

## 10. Success Milestones

| Milestone | Target Date | KPI |
|---|---|---|
| M1: MCP-ready, registry listed | Month 1 | PyPI live; mcp.so + awesome-mcp-servers submitted; Smithery deferred (MCPB) |
| M2: Community traction | Month 3 | 200 GitHub stars, 50 Smithery installs |
| M3: Hosted beta | Month 6 | 10 paying Pro users |
| M4: Sustainable revenue | Month 12 | $500 MRR |
| M5: Enterprise pipeline | Year 2 | 1 enterprise contract signed |
