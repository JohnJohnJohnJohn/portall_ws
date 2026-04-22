"""XML and JSON response serializers."""

import json
import math
import re
from typing import Any

import xmltodict

# XML 1.0 does not allow control characters, surrogates, or non-characters
_ILLEGAL_XML_CHARS_RE = re.compile(
    "[\x00-\x08\x0b\x0c\x0e-\x1f\x7f-\x9f\ud800-\udfff\ufffe-\uffff]"
)


def _sanitize_for_xml(v: Any) -> Any:
    if isinstance(v, str):
        return _ILLEGAL_XML_CHARS_RE.sub("", v)
    if isinstance(v, dict):
        safe = {}
        for k, val in v.items():
            safe_key = _ILLEGAL_XML_CHARS_RE.sub("", str(k))
            safe[safe_key] = _sanitize_for_xml(val)
        return safe
    if isinstance(v, list):
        return [_sanitize_for_xml(x) for x in v]
    return v


def _to_xml(payload: dict[str, Any]) -> str:
    safe = _sanitize_for_xml(payload)
    try:
        return '<?xml version="1.0" encoding="UTF-8"?>\n' + xmltodict.unparse(
            safe, pretty=True, full_document=False
        )
    except Exception:
        # Absolute fallback — never let an XML serialization glitch return a 500
        return (
            '<?xml version="1.0" encoding="UTF-8"?>\n'
            "<error><code>XML_SERIALIZATION_ERROR</code>"
            "<message>Failed to serialize response to XML</message></error>"
        )


def use_json_from_request(request) -> bool:
    """Determine whether to return JSON based on Accept header or query param."""
    accept = request.headers.get("accept", "")
    for mt in accept.split(","):
        mt = mt.strip()
        if not mt:
            continue
        parts = [p.strip() for p in mt.split(";")]
        mime = parts[0].lower()
        q = 1.0
        for p in parts[1:]:
            if p.startswith("q="):
                try:
                    q = float(p[2:])
                except ValueError:
                    q = 1.0
                break
        if mime == "application/json" and q != 0:
            return True
    return request.query_params.get("format") == "json"


def _clean_value(v: Any) -> Any:
    if isinstance(v, float):
        if not math.isfinite(v):
            return None
        # 9 decimals preserves small Greeks (e.g. charm ~1e-7)
        # while cleaning up float noise from QuantLib
        cleaned = round(v, 9)
        # Normalize -0.0 to 0.0 so it doesn't leak into JSON/XML as -0
        if cleaned == 0.0:
            cleaned = 0.0
        return cleaned
    if isinstance(v, dict):
        return {k: _clean_value(val) for k, val in v.items()}
    if isinstance(v, (list, tuple, set)):
        return [_clean_value(x) for x in v]
    return v


def serialize_error(
    code: str, message: str, field: str | None = None, json_format: bool = False
) -> str:
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
    payload = {"health": {"status": status, "uptime_seconds": _clean_value(uptime_seconds)}}
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
    cleaned_legs = [_clean_value(leg) for leg in legs]
    if json_format:
        payload: dict[str, Any] = {
            "portfolio": {
                "meta": meta,
                "legs": cleaned_legs,
                "aggregate": _clean_value(aggregate),
            }
        }
        return json.dumps(payload, indent=2)

    payload = {
        "portfolio": {
            "meta": meta,
            "legs": {"leg": cleaned_legs},
            "aggregate": _clean_value(aggregate),
        }
    }
    return _to_xml(payload)


def serialize_pnl_attribution(
    meta: dict[str, Any],
    inputs: dict[str, Any],
    outputs: dict[str, Any],
    json_format: bool = False,
) -> str:
    """Single-leg PnL attribution serializer matching greeks/impliedvol shape."""
    payload: dict[str, Any] = {
        "pnl_attribution": {
            "meta": meta,
            "inputs": inputs,
            "outputs": _clean_value(outputs),
        }
    }
    if json_format:
        return json.dumps(payload, indent=2)
    return _to_xml(payload)
