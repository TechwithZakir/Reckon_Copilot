from __future__ import annotations

import base64
import hashlib
import hmac
import json
import time
from typing import Any


def issue_approval_token(plan: dict[str, Any], *, user: str, site: str, secret: str, ttl_seconds: int = 300) -> str:
    payload = {
        "version": "v1",
        "plan_hash": str(plan.get("plan_hash") or ""),
        "user": user,
        "site": site,
        "expires_at": int(time.time()) + max(1, min(ttl_seconds, 900)),
    }
    encoded = _encode(payload)
    signature = hmac.new(secret.encode(), encoded.encode(), hashlib.sha256).hexdigest()
    return f"{encoded}.{signature}"


def validate_approval_token(token: str, *, plan_hash: str, user: str, site: str, secret: str) -> dict[str, Any]:
    try:
        encoded, signature = str(token or "").split(".", 1)
        expected = hmac.new(secret.encode(), encoded.encode(), hashlib.sha256).hexdigest()
        if not hmac.compare_digest(signature, expected):
            raise ValueError("Invalid approval signature")
        payload = json.loads(base64.urlsafe_b64decode(encoded + "=" * (-len(encoded) % 4)))
    except (ValueError, TypeError, json.JSONDecodeError, UnicodeDecodeError) as error:
        raise ValueError("Invalid approval token") from error
    if payload.get("plan_hash") != plan_hash or payload.get("user") != user or payload.get("site") != site:
        raise ValueError("Approval token scope does not match this plan")
    if int(payload.get("expires_at") or 0) < int(time.time()):
        raise ValueError("Approval token has expired")
    return payload


def _encode(payload: dict[str, Any]) -> str:
    return base64.urlsafe_b64encode(json.dumps(payload, separators=(",", ":"), sort_keys=True).encode()).decode().rstrip("=")
