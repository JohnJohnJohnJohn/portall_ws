"""XML and JSON response serializers."""

import json
from typing import Any

import xmltodict


def _clean_value(v: Any) -> Any:
    if isinstance(v, float):
        return round(v, 6)
    if isinstance(v, dict):
        return {k: _clean_value(val) for k, val in v.items()}
    if isinstance(v, list):
        return [_clean_value(x) for x in v]
    return v


def serialize_error(code: str, message: str, field: str | None = None, json_format: bool = False) -> str:
    payload: dict[str, Any] = {
        "error": {
            "code": code,
            "message": message,
        }
    }
    if field is not None:
        payload["error"]["field"] = field

    if json_format:
        return json.dumps(payload, indent=2)

    return xmltodict.unparse(payload, pretty=True, full_document=False)


def serialize_greeks(
    meta: dict[str, Any],
    inputs: dict[str, Any],
    outputs: dict[str, Any],
    json_format: bool = False,
) -> str:
    payload: dict[str, Any] = {
        "greeks": {
            "meta": meta,
            "inputs": inputs,
            "outputs": _clean_value(outputs),
        }
    }

    if json_format:
        return json.dumps(payload, indent=2)

    return xmltodict.unparse(payload, pretty=True, full_document=False)


def serialize_health(status: str, uptime_seconds: float, json_format: bool = False) -> str:
    payload = {"health": {"status": status, "uptime_seconds": uptime_seconds}}
    if json_format:
        return json.dumps(payload, indent=2)
    return xmltodict.unparse(payload, pretty=True, full_document=False)


def serialize_version(version_info: dict[str, str], json_format: bool = False) -> str:
    payload = {"version": version_info}
    if json_format:
        return json.dumps(payload, indent=2)
    return xmltodict.unparse(payload, pretty=True, full_document=False)


def serialize_portfolio(
    meta: dict[str, Any],
    legs: list[dict[str, Any]],
    aggregate: dict[str, Any],
    json_format: bool = False,
) -> str:
    payload: dict[str, Any] = {
        "portfolio": {
            "meta": meta,
            "legs": {"leg": legs},
            "aggregate": _clean_value(aggregate),
        }
    }

    if json_format:
        return json.dumps(payload, indent=2)

    return xmltodict.unparse(payload, pretty=True, full_document=False)
