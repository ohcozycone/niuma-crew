"""Plain evidence documents; no SDK, execution state machine or separate ledger."""

import json
import re

_SECRET_KEYS = frozenset(
    {
        "apikey",
        "authorization",
        "cookie",
        "setcookie",
        "password",
        "accesstoken",
        "refreshtoken",
        "clientsecret",
        "encryptedapikey",
        "secretkey",
    }
)
_BEARER = re.compile(r"(?i)\bBearer\s+[^\s\"'<>]+")


def redact(value):
    """Redact recognized credential fields without altering actual execution input."""
    if isinstance(value, dict):
        return {
            str(key): "[已脱敏]"
            if re.sub(r"[^a-z]", "", str(key).lower()) in _SECRET_KEYS
            else redact(item)
            for key, item in value.items()
        }
    if isinstance(value, list):
        return [redact(item) for item in value]
    if isinstance(value, str):
        if value.lstrip().startswith(("{", "[")):
            try:
                parsed = json.loads(value)
                if isinstance(parsed, (dict, list)):
                    cleaned = redact(parsed)
                    return value if cleaned == parsed else json.dumps(cleaned, ensure_ascii=False)
            except ValueError:
                pass
        return _BEARER.sub("Bearer [已脱敏]", value)
    return value


def document(stage: str, payload: dict) -> dict:
    return {
        "schema_version": 1,
        "capture_stage": stage,
        "redaction": "credential-fields-v1",
        "payload": redact(payload),
    }
