"""MCP tool definitions: schemas and agent-facing descriptions."""

from pydantic import BaseModel

from deskpricer.schemas import (
    GreeksRequest,
    ImpliedVolRequest,
    PnLAttributionGETRequest,
    PortfolioRequest,
)

# Shared unit conventions surfaced to agents (see CONVENTIONS.md).
_UNITS = (
    "Units: rates/q/v/b are decimals (0.05 = 5%, 0.20 = 20% vol). "
    "t is ACT/365 years (floored to 1 calendar day). "
    "Outputs are per 1 option contract (qty=1). "
    "vega and rho are per 1% point; theta and charm are per 1 calendar day."
)

_ENGINE_SUPPORT = (
    "Engines: european requires engine=analytic (default). "
    "american uses binomial_crr (default) or binomial_jr. "
    "Americans economically equal to Europeans are auto-priced via closed-form BSM "
    "(calls when |q+b|≤1e-8; puts when |r|≤1e-8)."
)

_CALENDARS = (
    "Calendars: hong_kong (default), us_nyse, us_settlement, united_kingdom, null."
)


def input_schema(model: type[BaseModel]) -> dict:
    """Return a JSON Schema suitable for MCP tool inputSchema."""
    return model.model_json_schema()


TOOL_SPECS: list[dict] = [
    {
        "name": "price_option",
        "model": GreeksRequest,
        "description": (
            "Price one vanilla equity option and return price plus full Greeks.\n\n"
            "HTTP equivalent: GET /v1/greeks\n\n"
            "Pricing: europeans (and equivalent americans) use closed-form BSM; "
            "other americans use QuantLib binomial CRR/JR.\n\n"
            "Use when marking a single call/put, checking sensitivities, or as input "
            "to your own risk logic. For multi-leg books use portfolio_greeks.\n\n"
            f"{_UNITS}\n"
            f"{_ENGINE_SUPPORT}\n"
            f"{_CALENDARS}\n\n"
            "Required: s (spot), k (strike), t, r, q, v (vol), type (call|put), "
            "style (european|american).\n"
            "Optional: b (borrow cost, default 0), engine, steps (american tree, "
            "default 500), valuation_date (ISO, default today), calendar, "
            "bump_spot_rel / bump_vol_abs / bump_rate_abs (american bump-and-revalue only).\n\n"
            "Returns JSON: "
            '{"greeks":{"meta":{service_version, quantlib_version, engine, valuation_date}, '
            '"inputs":{...}, "outputs":{price, delta, gamma, vega, theta, rho, charm}}}.'
        ),
    },
    {
        "name": "implied_volatility",
        "model": ImpliedVolRequest,
        "description": (
            "Solve for Black implied volatility given an observed option market price.\n\n"
            "HTTP equivalent: GET /v1/impliedvol\n\n"
            "Use to back out vol from a quoted premium. IV solving uses QuantLib "
            "(analytic for european, binomial for american). Reprices at the "
            "solved vol when verify_reprice=true (default).\n\n"
            f"{_UNITS}\n"
            f"{_ENGINE_SUPPORT}\n"
            f"{_CALENDARS}\n\n"
            "Required: s, k, t, r, q, price (observed premium), type, style.\n"
            "Optional: b, engine, steps, valuation_date, calendar, accuracy, "
            "max_iterations, verify_reprice.\n\n"
            "Returns JSON: "
            '{"impliedvol":{"meta":{...}, "inputs":{...}, '
            '"outputs":{implied_vol, npv_at_iv}}}.'
        ),
    },
    {
        "name": "pnl_attribution",
        "model": PnLAttributionGETRequest,
        "description": (
            "Decompose option PnL between two market snapshots into Greek buckets.\n\n"
            "HTTP equivalent: GET /v1/pnl_attribution\n\n"
            "Use after a move in spot, vol, rates, or time to explain actual PnL vs "
            "delta/gamma/vega/theta/rho (and optional vanna/volga). All outputs are "
            "per unit; multiply by qty yourself for position size.\n\n"
            f"{_UNITS}\n"
            f"{_ENGINE_SUPPORT}\n"
            f"{_CALENDARS}\n\n"
            "Required: s_t_minus_1, s_t, k, t_t_minus_1, t_t (must not increase), "
            "r/q/v at both dates, type, style.\n"
            "Optional: b_t_minus_1, b_t, engine, steps, qty (default 1, reporting only), "
            "valuation_date_t_minus_1 / valuation_date_t (ISO; both or neither — default "
            "today with 1 calendar day elapsed), method (backward|average for vega/rho), "
            "cross_greeks (add vanna/volga buckets), calendar, bump_*.\n\n"
            "Theta PnL = theta × calendar_days between valuation dates. "
            "Vega/rho use vol/rate changes in percentage points.\n\n"
            "Returns JSON: "
            '{"pnl_attribution":{"meta":{..., calendar_days, method}, "inputs":{...}, '
            '"outputs":{price_t_minus_1, price_t, actual_pnl, delta_pnl, gamma_pnl, '
            "vega_pnl, theta_pnl, rho_pnl, vanna_pnl, volga_pnl, explained_pnl, "
            'residual_pnl}}}.'
        ),
    },
    {
        "name": "portfolio_greeks",
        "model": PortfolioRequest,
        "description": (
            "Price up to 500 option legs and return per-leg Greeks plus qty-weighted aggregate.\n\n"
            "HTTP equivalent: POST /v1/portfolio/greeks\n\n"
            "Use for spreads, baskets, or any multi-leg structure. Each leg carries its "
            "own spot/strike/vol and optional qty (negative for short). Leg outputs are "
            "unit Greeks; aggregate sums qty × greek across legs.\n\n"
            f"{_UNITS}\n"
            f"{_ENGINE_SUPPORT}\n"
            f"{_CALENDARS}\n\n"
            "Required: legs[] — each leg needs id, qty, s, k, t, r, q, v, type, style "
            "(plus optional b, engine, steps, calendar, underlying_id, bump_*).\n"
            "Optional: valuation_date (ISO, default today).\n\n"
            "Warns (does not fail) if legs sharing underlying_id have spot prices "
            "diverging by >5%.\n\n"
            "Returns JSON: "
            '{"portfolio":{"meta":{service_version, quantlib_version, valuation_date}, '
            '"legs":[{id, engine, price, delta, ...}], '
            '"aggregate":{price, delta, gamma, vega, theta, rho, charm}}}.'
        ),
    },
]
