from __future__ import annotations

import hashlib
import hmac
import json
from typing import Any, Dict, Optional
from urllib.parse import parse_qsl

from app.settings import settings


def _parse_init_data(init_data: str) -> Dict[str, str]:
    try:
        pairs = parse_qsl(init_data, keep_blank_values=True, strict_parsing=False)
        return {k: v for k, v in pairs}
    except Exception:
        return {}


def _build_data_check_string(data: Dict[str, str]) -> str:
    items = []
    for k in sorted(data.keys()):
        if k == "hash":
            continue
        items.append(f"{k}={data[k]}")
    return "\n".join(items)


def verify_init_data(init_data: str) -> Dict[str, Any]:
    """Verify Telegram WebApp initData.

    Returns parsed user dict on success.
    Raises ValueError on failure.
    """
    if not init_data:
        raise ValueError("Missing initData")

    data = _parse_init_data(init_data)
    if not data or "hash" not in data:
        raise ValueError("Missing initData/hash")

    bot_token = settings.bot_token or ""
    if not bot_token:
        raise ValueError("BOT_TOKEN missing")

    received_hash = data.get("hash", "")
    data_check_string = _build_data_check_string(data)

    secret_key = hmac.new(b"WebAppData", bot_token.encode("utf-8"), hashlib.sha256).digest()
    computed_hash = hmac.new(secret_key, data_check_string.encode("utf-8"), hashlib.sha256).hexdigest()

    if not hmac.compare_digest(computed_hash, received_hash):
        raise ValueError("Invalid initData signature")

    user_raw = data.get("user", "")
    try:
        user = json.loads(user_raw) if user_raw else {}
    except Exception:
        user = {}

    user["_auth_date"] = data.get("auth_date")
    user["_query_id"] = data.get("query_id")
    return user


def extract_init_data(headers: Dict[str, str], query: Dict[str, str], body: Optional[Dict[str, Any]] = None) -> str:
    # 1) query
    init_data = (query or {}).get("initData")
    if init_data:
        return init_data

    # 2) headers
    for h in [
        "X-Telegram-Init-Data",
        "X-Telegram-InitData",
        "X-TG-INITDATA",
    ]:
        if h in headers and headers[h]:
            return headers[h]

    # 3) body
    if body and isinstance(body, dict):
        v = body.get("initData")
        if isinstance(v, str) and v:
            return v

    return ""
