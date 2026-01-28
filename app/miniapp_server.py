from __future__ import annotations

import json
import os
from datetime import datetime
from pathlib import Path
from typing import Any, Dict

import aiohttp
from aiohttp import web

from app.db import SessionLocal
from app.keyboards import CATEGORIES
from app.settings import settings
from app.services.telegram_webapp import extract_init_data, verify_init_data
from app.services.repo import (
    list_tests_by_category,
    get_test,
    get_correct_answers,
    save_submission,
    list_answer_matrices_for_test,
    count_baseline_submissions,
    get_or_create_user,
    get_latest_submission,
    replace_test_answers,
    ensure_baseline_users,
    delete_submissions_for_user_test,
    list_baseline_done_indices,
)
from app.services.scoring import simple_check, rasch_percentile_score, sat_scaled_from_percentile
from app.services.answers import normalize_to_spec, encode_for_storage
from app.services.certificates import (
    CertificateData,
    render_simple_certificate,
    render_sat_style_certificate,
    render_milliy_certificate,
)
from app.services.certificates_store import create_certificate_record
from app.services.certificates_store import get_certificate_path_for_user

DATA_DIR = Path("data")
CERT_DIR = DATA_DIR / "certificates"
MINIAPP_DIR = Path(__file__).resolve().parent.parent / "miniapp"


def _normalize_chat_ref(ref: str) -> str:
    r = (ref or "").strip()
    if r.startswith("https://t.me/"):
        r = r.replace("https://t.me/", "@", 1)
    return r


async def _get_required_channel() -> str:
    from app.services.repo import get_setting
    async with SessionLocal() as session:
        return (await get_setting(session, "required_channel", settings.required_channel)).strip()


async def _get_required_group() -> str:
    from app.services.repo import get_setting
    async with SessionLocal() as session:
        return (await get_setting(session, "required_group", settings.required_group)).strip()


async def _get_required_urls() -> tuple[str, str]:
    from app.services.repo import get_setting
    async with SessionLocal() as session:
        ch_url = (await get_setting(session, "required_channel_url", settings.required_channel_url)).strip()
        gr_url = (await get_setting(session, "required_group_url", settings.required_group_url)).strip()

    ch = _normalize_chat_ref(await _get_required_channel())
    gr = _normalize_chat_ref(await _get_required_group())
    if not ch_url and ch.startswith("@"):
        ch_url = f"https://t.me/{ch[1:]}"
    if not gr_url and gr.startswith("@"):
        gr_url = f"https://t.me/{gr[1:]}"
    return ch_url, gr_url


async def _tg_is_member(tg_id: int, chat_ref: str) -> bool:
    chat_ref = _normalize_chat_ref(chat_ref)
    if not chat_ref:
        return True
    token = settings.bot_token
    if not token:
        return False

    url = f"https://api.telegram.org/bot{token}/getChatMember"
    params = {"chat_id": chat_ref, "user_id": str(tg_id)}
    try:
        async with aiohttp.ClientSession(timeout=aiohttp.ClientTimeout(total=8)) as s:
            async with s.get(url, params=params) as resp:
                data = await resp.json(content_type=None)
        if not isinstance(data, dict) or not data.get("ok"):
            return False
        status = (((data.get("result") or {}).get("status")) or "").strip()
        return status in {"member", "administrator", "creator"}
    except Exception:
        return False


async def _check_membership(tg_id: int) -> bool:
    ch = _normalize_chat_ref(await _get_required_channel())
    gr = _normalize_chat_ref(await _get_required_group())
    return (await _tg_is_member(tg_id, ch)) and (await _tg_is_member(tg_id, gr))


def _milliy_level(percent: float) -> str:
    p = percent
    if 50 <= p <= 59.999:
        return "C"
    if 60 <= p <= 69.999:
        return "C+"
    if 70 <= p <= 79.999:
        return "B"
    if 80 <= p <= 89.999:
        return "B+"
    if 90 <= p <= 94.999:
        return "A"
    if 95 <= p <= 100:
        return "A+"
    return "-"


async def _json(request: web.Request) -> Dict[str, Any]:
    try:
        return await request.json()
    except Exception:
        return {}


def _user_from_request(request: web.Request, body: Dict[str, Any]) -> Dict[str, Any]:
    if settings.miniapp_dev_bypass:
        dev_id = request.query.get("dev_tg_id") or (body.get("dev_tg_id") if isinstance(body, dict) else None)
        if dev_id and str(dev_id).lstrip("-").isdigit():
            return {"id": int(dev_id), "first_name": "DEV", "username": "dev"}

    init_data = extract_init_data(dict(request.headers), dict(request.query), body)
    return verify_init_data(init_data)


async def handle_index(request: web.Request) -> web.Response:
    index = MINIAPP_DIR / "index.html"
    if not index.exists():
        return web.Response(text="miniapp/index.html missing", status=500)
    return web.FileResponse(path=index)


async def health(request: web.Request) -> web.Response:
    return web.json_response({"ok": True})


# ---- sizning qolgan handlerlaringiz (handle_categories, handle_tests, ...) O'ZGARMAGAN ----
# (bu yerda siz bergan kodning qolgan qismi o'sha-o'sha qoladi)


async def create_app() -> web.Application:
    app = web.Application()

    # health doim birinchi bo'lsin
    app.router.add_get("/health", health)

    # miniapp entry
    app.router.add_get("/", handle_index)

    app.router.add_get("/api/me", handle_me)
    app.router.add_get("/api/categories", handle_categories)
    app.router.add_get("/api/tests", handle_tests)
    app.router.add_get("/api/test", handle_test_detail)
    app.router.add_post("/api/admin/save_answers", handle_admin_save_answers)
    app.router.add_post("/api/admin/baseline_submit", handle_admin_baseline_submit)
    app.router.add_get("/api/admin/baseline_status", handle_admin_baseline_status)
    app.router.add_post("/api/submit", handle_submit)
    app.router.add_post("/api/send_certificate", handle_send_certificate)

    static_dir = MINIAPP_DIR / "static"
    if static_dir.exists():
        app.router.add_static("/static", static_dir)

    return app


async def start_miniapp() -> web.AppRunner:
    app = await create_app()
    runner = web.AppRunner(app)
    await runner.setup()

    # Render: PORT ni settings already oladi, ammo fallback ham qoldiramiz
    port = int(os.getenv("PORT") or str(settings.miniapp_port or 8000))
    host = settings.miniapp_host or "0.0.0.0"

    site = web.TCPSite(runner, host, port)
    await site.start()

    return runner
