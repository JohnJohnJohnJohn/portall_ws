"""MCP stdio server exposing DeskPricer pricing tools to AI agents."""

from __future__ import annotations

import asyncio
import logging
from typing import Any

from mcp.server import Server
from mcp.server.stdio import stdio_server
from mcp.types import CallToolResult, TextContent, Tool
from pydantic import ValidationError

from deskpricer import __version__ as service_version
from deskpricer.errors import DeskPricerError
from deskpricer.mcp_tools import TOOL_SPECS, input_schema
from deskpricer.responses import (
    serialize_error,
    serialize_greeks,
    serialize_impliedvol,
    serialize_pnl_attribution,
    serialize_portfolio,
)
from deskpricer.schemas import (
    GreeksRequest,
    ImpliedVolRequest,
    PnLAttributionGETRequest,
    PortfolioRequest,
)
from deskpricer.services import pricing_service

_logger = logging.getLogger("deskpricer")

SERVER_INSTRUCTIONS = (
    "DeskPricer prices vanilla European and American equity options with deterministic, "
    "auditable outputs (no LLM estimation of prices). "
    "Tools mirror the HTTP API: price_option, implied_volatility, pnl_attribution, "
    "portfolio_greeks. "
    "All rates/yields/vol/borrow are decimals; Greek outputs are per one contract. "
    "See each tool description for required fields and response JSON shape."
)

_TOOL_BY_NAME = {spec["name"]: spec for spec in TOOL_SPECS}


def build_tools() -> list[Tool]:
    return [
        Tool(
            name=spec["name"],
            description=spec["description"],
            inputSchema=input_schema(spec["model"]),
        )
        for spec in TOOL_SPECS
    ]


def _text_result(text: str, *, is_error: bool) -> CallToolResult:
    return CallToolResult(
        content=[TextContent(type="text", text=text)],
        isError=is_error,
    )


def _error_result(code: str, message: str, field: str | None = None) -> CallToolResult:
    return _text_result(serialize_error(code, message, field, json_format=True), is_error=True)


def _success_result(payload_json: str) -> CallToolResult:
    return _text_result(payload_json, is_error=False)


async def execute_mcp_tool(name: str, arguments: dict[str, Any] | None) -> CallToolResult:
    """Dispatch a tool call to the pricing service (testable without stdio transport)."""
    if name not in _TOOL_BY_NAME:
        return _error_result("NOT_FOUND", f"Unknown tool: {name}")

    args = arguments or {}
    try:
        if name == "price_option":
            params = GreeksRequest.model_validate(args)
            meta, inputs, outputs = await pricing_service.run_greeks(params)
            return _success_result(
                serialize_greeks(meta, inputs, outputs, json_format=True)
            )

        if name == "implied_volatility":
            params = ImpliedVolRequest.model_validate(args)
            meta, inputs, outputs = await pricing_service.run_impliedvol(params)
            return _success_result(
                serialize_impliedvol(meta, inputs, outputs, json_format=True)
            )

        if name == "pnl_attribution":
            params = PnLAttributionGETRequest.model_validate(args)
            meta, inputs, outputs = await pricing_service.run_pnl_attribution(params)
            return _success_result(
                serialize_pnl_attribution(meta, inputs, outputs, json_format=True)
            )

        if name == "portfolio_greeks":
            payload = PortfolioRequest.model_validate(args)
            meta, legs_out, aggregate = await pricing_service.run_portfolio(payload)
            return _success_result(
                serialize_portfolio(meta, legs_out, aggregate, json_format=True)
            )

        return _error_result("NOT_FOUND", f"Unhandled tool: {name}")

    except ValidationError as exc:
        errors = exc.errors()
        if errors:
            first = errors[0]
            loc = first.get("loc", ())
            field = ".".join(str(x) for x in loc) if loc else None
            message = first.get("msg", "Validation error")
        else:
            field = None
            message = "Validation error"
        return _error_result("INVALID_INPUT", message, field)

    except DeskPricerError as exc:
        return _error_result(exc.code, exc.message, exc.field)

    except Exception as exc:
        _logger.exception("MCP tool %s failed", name)
        return _error_result("PRICING_FAILURE", f"Internal pricing error: {exc}")


def create_mcp_server() -> Server:
    server = Server(
        "deskpricer",
        version=service_version,
        instructions=SERVER_INSTRUCTIONS,
    )

    @server.list_tools()
    async def list_tools() -> list[Tool]:
        return build_tools()

    @server.call_tool()
    async def call_tool(name: str, arguments: dict[str, Any] | None) -> CallToolResult:
        return await execute_mcp_tool(name, arguments)

    return server


async def _async_main() -> None:
    server = create_mcp_server()
    async with stdio_server() as (read_stream, write_stream):
        await server.run(
            read_stream,
            write_stream,
            server.create_initialization_options(),
        )


def main() -> None:
    """CLI entrypoint: deskpricer-mcp"""
    asyncio.run(_async_main())


if __name__ == "__main__":
    main()
