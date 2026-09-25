from __future__ import annotations

import base64
import hashlib
import json
import secrets
import time
from typing import Any


def issue_approval_token(plan: dict[str, Any], *, user: str, site: str, ttl_seconds: int = 300) -> str:
    payload = {
        "version": "v1",
        "plan_hash": str(plan.get("plan_hash") or ""),
        "user": user,
        "site": site,
        "expires_at": int(time.time()) + max(1, min(ttl_seconds, 900)),
        "nonce": secrets.token_urlsafe(24),
    }
    return _encode(payload)


def validate_approval_token(token: str, *, plan_hash: str, user: str, site: str) -> dict[str, Any]:
    try:
        payload = json.loads(base64.urlsafe_b64decode(str(token or "") + "=" * (-len(str(token or "")) % 4)))
    except (ValueError, TypeError, json.JSONDecodeError, UnicodeDecodeError) as error:
        raise ValueError("Invalid approval token") from error
    if not isinstance(payload, dict):
        raise ValueError("Invalid approval token")
    if (
        payload.get("version") != "v1"
        or not payload.get("nonce")
        or payload.get("plan_hash") != plan_hash
        or payload.get("user") != user
        or payload.get("site") != site
    ):
        raise ValueError("Approval token scope does not match this plan")
    if int(payload.get("expires_at") or 0) < int(time.time()):
        raise ValueError("Approval token has expired")
    return payload


def hash_approval_token(token: str) -> str:
    return hashlib.sha256(str(token or "").encode("utf-8")).hexdigest()


def _encode(payload: dict[str, Any]) -> str:
    return base64.urlsafe_b64encode(json.dumps(payload, separators=(",", ":"), sort_keys=True).encode()).decode().rstrip("=")
