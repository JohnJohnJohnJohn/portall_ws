"""MCP server tool registration, dispatch, and spec-compliance tests."""

import asyncio
import json
from datetime import date
from importlib.metadata import entry_points

import pytest

from deskpricer.mcp_server import build_tools, create_mcp_server, execute_mcp_tool
from deskpricer.mcp_tools import TOOL_SPECS, input_schema
from deskpricer.responses import serialize_greeks
from deskpricer.schemas import GreeksRequest
from deskpricer.services.pricing_service import run_greeks


class TestMcpSpecCompliance:
    def test_console_script_entrypoint(self):
        scripts = entry_points(group="console_scripts")
        ep = next((e for e in scripts if e.name == "deskpricer-mcp"), None)
        assert ep is not None
        assert ep.value == "deskpricer.mcp_server:main"

    @pytest.mark.parametrize("spec", TOOL_SPECS, ids=[s["name"] for s in TOOL_SPECS])
    def test_input_schema_matches_pydantic(self, spec):
        tool = next(t for t in build_tools() if t.name == spec["name"])
        assert tool.inputSchema == input_schema(spec["model"])

    def test_success_payload_is_text_content_json(self):
        result = asyncio.run(
            execute_mcp_tool(
                "price_option",
                {
                    "s": 100.0,
                    "k": 100.0,
                    "t": 0.25,
                    "r": 0.05,
                    "q": 0.0,
                    "v": 0.20,
                    "type": "call",
                    "style": "european",
                    "calendar": "null",
                    "valuation_date": "2026-04-20",
                },
            )
        )
        assert not result.isError
        assert len(result.content) == 1
        assert result.content[0].type == "text"
        json.loads(result.content[0].text)

    def test_mcp_greeks_response_matches_http_serializer(self):
        params = GreeksRequest(
            s=100.0,
            k=105.0,
            t=0.25,
            r=0.05,
            q=0.02,
            v=0.20,
            type="call",
            style="european",
            calendar="null",
            valuation_date=date(2026, 4, 20),
        )
        meta, inputs, outputs = asyncio.run(run_greeks(params))
        expected = serialize_greeks(meta, inputs, outputs, json_format=True)
        result = asyncio.run(
            execute_mcp_tool(
                "price_option",
                {
                    "s": 100.0,
                    "k": 105.0,
                    "t": 0.25,
                    "r": 0.05,
                    "q": 0.02,
                    "v": 0.20,
                    "type": "call",
                    "style": "european",
                    "calendar": "null",
                    "valuation_date": "2026-04-20",
                },
            )
        )
        assert not result.isError
        assert result.content[0].text == expected

    def test_error_payload_matches_http_error_shape(self):
        result = asyncio.run(execute_mcp_tool("price_option", {"s": -1}))
        assert result.isError
        body = json.loads(result.content[0].text)
        assert set(body.keys()) == {"error"}
        assert {"code", "message"} <= set(body["error"].keys())


class TestMcpToolCatalog:
    def test_tool_count_and_names(self):
        tools = build_tools()
        assert [t.name for t in tools] == [
            "price_option",
            "implied_volatility",
            "pnl_attribution",
            "portfolio_greeks",
        ]

    @pytest.mark.parametrize("name", [spec["name"] for spec in TOOL_SPECS])
    def test_tool_descriptions_cover_http_and_units(self, name: str):
        tool = next(t for t in build_tools() if t.name == name)
        assert "HTTP equivalent" in tool.description
        assert "decimal" in tool.description.lower() or "decimals" in tool.description.lower()
        assert tool.inputSchema.get("type") == "object"
        assert tool.inputSchema.get("properties")

    def test_create_mcp_server_registers_handlers(self):
        server = create_mcp_server()
        assert server.name == "deskpricer"
        assert server.instructions


class TestMcpToolExecution:
    def _run(self, coro):
        return asyncio.run(coro)

    def test_price_option_european_call(self):
        result = self._run(
            execute_mcp_tool(
                "price_option",
                {
                    "s": 100.0,
                    "k": 105.0,
                    "t": 0.25,
                    "r": 0.05,
                    "q": 0.02,
                    "v": 0.20,
                    "type": "call",
                    "style": "european",
                    "calendar": "null",
                },
            )
        )
        assert not result.isError
        payload = json.loads(result.content[0].text)
        outputs = payload["greeks"]["outputs"]
        assert outputs["price"] > 0
        assert 0 < outputs["delta"] < 1

    def test_implied_volatility_round_trip(self):
        price_result = self._run(
            execute_mcp_tool(
                "price_option",
                {
                    "s": 100.0,
                    "k": 100.0,
                    "t": 1.0,
                    "r": 0.05,
                    "q": 0.02,
                    "v": 0.25,
                    "type": "call",
                    "style": "european",
                    "calendar": "null",
                },
            )
        )
        target_price = json.loads(price_result.content[0].text)["greeks"]["outputs"]["price"]
        iv_result = self._run(
            execute_mcp_tool(
                "implied_volatility",
                {
                    "s": 100.0,
                    "k": 100.0,
                    "t": 1.0,
                    "r": 0.05,
                    "q": 0.02,
                    "price": target_price,
                    "type": "call",
                    "style": "european",
                    "calendar": "null",
                },
            )
        )
        assert not iv_result.isError
        implied = json.loads(iv_result.content[0].text)["impliedvol"]["outputs"]["implied_vol"]
        assert abs(implied - 0.25) < 1e-4

    def test_pnl_attribution_delta_move(self):
        result = self._run(
            execute_mcp_tool(
                "pnl_attribution",
                {
                    "s_t_minus_1": 100.0,
                    "s_t": 102.0,
                    "k": 100.0,
                    "t_t_minus_1": 0.25,
                    "t_t": 0.24,
                    "r_t_minus_1": 0.05,
                    "r_t": 0.05,
                    "q_t_minus_1": 0.0,
                    "q_t": 0.0,
                    "v_t_minus_1": 0.20,
                    "v_t": 0.20,
                    "type": "call",
                    "style": "european",
                    "calendar": "null",
                },
            )
        )
        assert not result.isError
        outputs = json.loads(result.content[0].text)["pnl_attribution"]["outputs"]
        assert outputs["delta_pnl"] != 0.0
        assert "residual_pnl" in outputs

    def test_portfolio_greeks_aggregate(self):
        result = self._run(
            execute_mcp_tool(
                "portfolio_greeks",
                {
                    "valuation_date": "2026-04-20",
                    "legs": [
                        {
                            "id": "L1",
                            "qty": 2.0,
                            "s": 100.0,
                            "k": 100.0,
                            "t": 0.25,
                            "r": 0.05,
                            "q": 0.0,
                            "v": 0.20,
                            "type": "call",
                            "style": "european",
                            "calendar": "null",
                        },
                        {
                            "id": "L2",
                            "qty": -1.0,
                            "s": 100.0,
                            "k": 100.0,
                            "t": 0.25,
                            "r": 0.05,
                            "q": 0.0,
                            "v": 0.20,
                            "type": "put",
                            "style": "european",
                            "calendar": "null",
                        },
                    ],
                },
            )
        )
        assert not result.isError
        body = json.loads(result.content[0].text)["portfolio"]
        l1, l2 = body["legs"]
        agg = body["aggregate"]
        assert agg["delta"] == pytest.approx(2 * l1["delta"] - 1 * l2["delta"])

    def test_unknown_tool(self):
        result = self._run(execute_mcp_tool("not_a_tool", {}))
        assert result.isError
        err = json.loads(result.content[0].text)["error"]
        assert err["code"] == "NOT_FOUND"

    def test_validation_error(self):
        result = self._run(execute_mcp_tool("price_option", {"s": -1}))
        assert result.isError
        err = json.loads(result.content[0].text)["error"]
        assert err["code"] == "INVALID_INPUT"
