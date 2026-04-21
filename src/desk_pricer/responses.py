"""XML and JSON response serializers."""

import json
import re
from typing import Any

import xmltodict

# XML 1.0 does not allow certain control characters
_ILLEGAL_XML_CHARS_RE = re.compile(
    "[\x00-\x08\x0b\x0c\x0e-\x1f\x7f-\x84\x86-\x9f]"
)


def _sanitize_for_xml(v: Any) -> Any:
    if isinstance(v, str):
        return _ILLEGAL_XML_CHARS_RE.sub("", v)
    if isinstance(v, dict):
        return {k: _sanitize_for_xml(val) for k, val in v.items()}
    if isinstance(v, list):
        return [_sanitize_for_xml(x) for x in v]
    return v


def _to_xml(payload: dict[str, Any]) -> str:
    safe = _sanitize_for_xml(payload)
    return xmltodict.unparse(safe, pretty=True, full_document=False)


def use_json_from_request(request) -> bool:
    """Determine whether to return JSON based on Accept header or query param."""
    accept = request.headers.get("accept", "")
    media_types = [
        mt.strip().split(";")[0].strip().lower()
        for mt in accept.split(",")
        if mt.strip()
    ]
    if "application/json" in media_types:
        return True
    if request.query_params.get("format") == "json":
        return True
    return False


def _clean_value(v: Any) -> Any:
    if isinstance(v, float):
        # 9 decimals preserves small Greeks (e.g. charm ~1e-7)
        # while cleaning up float noise from QuantLib
        return round(v, 9)
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

    return _to_xml(payload)


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

    return _to_xml(payload)


def serialize_impliedvol(
    meta: dict[str, Any],
    inputs: dict[str, Any],
    outputs: dict[str, Any],
    json_format: bool = False,
) -> str:
    payload: dict[str, Any] = {
        "impliedvol": {
            "meta": meta,
            "inputs": inputs,
            "outputs": _clean_value(outputs),
        }
    }

    if json_format:
        return json.dumps(payload, indent=2)

    return _to_xml(payload)


def serialize_health(status: str, uptime_seconds: float, json_format: bool = False) -> str:
    payload = {"health": {"status": status, "uptime_seconds": uptime_seconds}}
    if json_format:
        return json.dumps(payload, indent=2)
    return _to_xml(payload)


def serialize_version(version_info: dict[str, str], json_format: bool = False) -> str:
    payload = {"version": version_info}
    if json_format:
        return json.dumps(payload, indent=2)
    return _to_xml(payload)


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

    return _to_xml(payload)
