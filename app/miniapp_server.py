from __future__ import annotations

import json
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
    if not ch_url and ch.startswith("@"):  # public
        ch_url = f"https://t.me/{ch[1:]}"
    if not gr_url and gr.startswith("@"):  # public
        gr_url = f"https://t.me/{gr[1:]}"
    return ch_url, gr_url


async def _tg_is_member(tg_id: int, chat_ref: str) -> bool:
    chat_ref = _normalize_chat_ref(chat_ref)
    if not chat_ref:
        return True
    token = settings.bot_token
    if not token:
        # if bot token missing, fail closed
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
    # dev bypass for local browser testing
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


async def handle_categories(request: web.Request) -> web.Response:
    body: Dict[str, Any] = {}
    try:
        user = _user_from_request(request, body)
    except Exception as e:
        return web.json_response({"error": str(e)}, status=401)

    tg_id = int(user.get("id", 0) or 0)
    if not tg_id:
        return web.json_response({"error": "invalid tg user"}, status=401)

    if not await _check_membership(tg_id):
        ch_url, gr_url = await _get_required_urls()
        return web.json_response(
            {
                "join_required": True,
                "message": "Avval kanal va guruhga qo‘shiling, so‘ng qayta urinib ko‘ring.",
                "channel_url": ch_url,
                "group_url": gr_url,
            },
            status=403,
        )

    return web.json_response({"categories": [{"key": k, "label": lab} for k, lab in CATEGORIES]})


async def handle_tests(request: web.Request) -> web.Response:
    body: Dict[str, Any] = {}
    try:
        user = _user_from_request(request, body)
    except Exception as e:
        return web.json_response({"error": str(e)}, status=401)

    tg_id = int(user.get("id", 0) or 0)
    if not tg_id:
        return web.json_response({"error": "invalid tg user"}, status=401)

    if not await _check_membership(tg_id):
        ch_url, gr_url = await _get_required_urls()
        return web.json_response(
            {
                "join_required": True,
                "message": "Avval kanal va guruhga qo‘shiling, so‘ng qayta urinib ko‘ring.",
                "channel_url": ch_url,
                "group_url": gr_url,
            },
            status=403,
        )

    cat = (request.query.get("category") or "").strip()
    if not cat:
        return web.json_response({"error": "missing category"}, status=400)

    for_check = (request.query.get("for_check") or "").strip() in {"1", "true", "yes"}

    async with SessionLocal() as session:
        rows = await list_tests_by_category(session, cat)
        out = []
        for tid, name in rows:
            t = await get_test(session, tid)
            baseline_ready = True
            if t.is_rasch:
                baseline_ready = (await count_baseline_submissions(session, tid)) >= 10
                if for_check and not baseline_ready:
                    continue
            out.append(
                {
                    "id": t.id,
                    "name": t.name,
                    "num_questions": t.num_questions,
                    "is_rasch": bool(t.is_rasch),
                    "baseline_ready": bool(baseline_ready),
                }
            )

    return web.json_response({"tests": out})


async def handle_submit(request: web.Request) -> web.Response:
    body = await _json(request)

    try:
        user = _user_from_request(request, body)
    except Exception as e:
        return web.json_response({"error": str(e)}, status=401)

    try:
        test_id = int(body.get("test_id"))
    except Exception:
        return web.json_response({"error": "invalid test_id"}, status=400)

    answers_raw = body.get("answers")
    if not isinstance(answers_raw, dict):
        return web.json_response({"error": "answers must be an object like {\"1\":\"A\"}"}, status=400)

    answers: Dict[int, str] = {}
    for k, v in answers_raw.items():
        try:
            q = int(k)
        except Exception:
            continue
        spec = normalize_to_spec(v)
        answers[q] = encode_for_storage(spec) if (spec.choices or spec.manual) else ""

    tg_id = int(user.get("id", 0))
    if not tg_id:
        return web.json_response({"error": "invalid tg user"}, status=400)

    if not await _check_membership(tg_id):
        ch_url, gr_url = await _get_required_urls()
        return web.json_response(
            {
                "join_required": True,
                "message": "Avval kanal va guruhga qo‘shiling, so‘ng qayta urinib ko‘ring.",
                "channel_url": ch_url,
                "group_url": gr_url,
            },
            status=403,
        )

    full_name = (str(user.get("first_name", "")) + " " + str(user.get("last_name", ""))).strip() or "Ism Familiya"

    async with SessionLocal() as session:
        # upsert user
        await get_or_create_user(
            session,
            tg_id=tg_id,
            first_name=str(user.get("first_name", ""))[:120],
            last_name=str(user.get("last_name", ""))[:120],
            username=str(user.get("username", ""))[:120],
        )

        t = await get_test(session, test_id)

        # one attempt rule (except baseline users)
        prev = await get_latest_submission(session, tg_id, test_id)
        if prev is not None:
            return web.json_response(
                {
                    "error": "Bu test allaqachon tekshirilgan. Admin testni edit qilsa, qayta tekshirishingiz mumkin.",
                    "already_submitted": True,
                },
                status=409,
            )
        if t.is_rasch:
            cnt = await count_baseline_submissions(session, test_id)
            if cnt < 10:
                return web.json_response(
                    {
                        "error": "Rasch test uchun admin hali 10 ta baseline javoblarini kiritmagan.",
                        "baseline_needed": 10,
                        "baseline_have": cnt,
                    },
                    status=409,
                )

        correct = await get_correct_answers(session, test_id)
        res_simple = simple_check(answers, correct, t.num_questions)

        if t.is_rasch:
            mats = await list_answer_matrices_for_test(session, test_id)
            mats2 = mats + [res_simple.per_question_correct]
            score = rasch_percentile_score(mats2, target_index=len(mats2) - 1)
            sub = await save_submission(
                session,
                tg_id=tg_id,
                test_id=test_id,
                answers=answers,
                raw_correct=res_simple.raw_correct,
                total=res_simple.total,
                score=score,
                is_rasch=True,
            )
        else:
            score = res_simple.score
            sub = await save_submission(
                session,
                tg_id=tg_id,
                test_id=test_id,
                answers=answers,
                raw_correct=res_simple.raw_correct,
                total=res_simple.total,
                score=score,
                is_rasch=False,
            )

    # certificate render
    CERT_DIR.mkdir(parents=True, exist_ok=True)
    issued = datetime.utcnow()
    out_path = CERT_DIR / f"{tg_id}_{test_id}_{sub.id}.pdf"

    score_text = f"{score:.1f}%"
    extra: Dict[str, Any] = {}

    if t.category == "sat":
        sat_score = sat_scaled_from_percentile(score)
        score_text = str(sat_score)
        render_sat_style_certificate(out_path, CertificateData(full_name=full_name, test_name=t.name, score_text=score_text, issued_at=issued))
        extra["sat_math"] = sat_score
    elif t.category == "milliy":
        level = _milliy_level(score)
        render_milliy_certificate(out_path, full_name=full_name, test_name=t.name, percent=score, level=level, issued_at=issued)
        extra["milliy_level"] = level
    else:
        render_simple_certificate(out_path, CertificateData(full_name=full_name, test_name=t.name, score_text=score_text, issued_at=issued))

    cert_id = await create_certificate_record(tg_id=tg_id, test_id=test_id, pdf_path=str(out_path), score_text=score_text)

    bot_username = settings.bot_username.strip().lstrip("@")
    deeplink_base = f"https://t.me/{bot_username}?start=" if bot_username else ""

    return web.json_response(
        {
            "ok": True,
            "test": {"id": t.id, "name": t.name, "category": t.category, "num_questions": t.num_questions, "is_rasch": bool(t.is_rasch)},
            "result": {
                "raw_correct": res_simple.raw_correct,
                "total": res_simple.total,
                "score": round(float(score), 2),
                "score_text": score_text,
                **extra,
            },
            "deeplinks": {
                "pdf": f"{deeplink_base}pdf_{test_id}" if deeplink_base else None,
                "certificate": f"{deeplink_base}cert_{cert_id}" if deeplink_base else None,
            },
            "certificate_id": cert_id,
        }
    )


def _roles_for_tg(tg_id: int) -> list[str]:
    roles: list[str] = ["user"]
    if tg_id in set(settings.admin_tg_ids or []):
        roles.append("admin")
    if tg_id in set(settings.ceo_tg_ids or []):
        roles.append("ceo")
    # unique + stable
    out: list[str] = []
    for r in roles:
        if r not in out:
            out.append(r)
    return out


async def handle_me(request: web.Request) -> web.Response:
    try:
        user = _user_from_request(request, {})
    except Exception as e:
        return web.json_response({"error": str(e)}, status=401)
    tg_id = int(user.get("id", 0) or 0)
    if not tg_id:
        return web.json_response({"error": "invalid tg user"}, status=400)
    return web.json_response({"ok": True, "roles": _roles_for_tg(tg_id), "tg_id": tg_id})


async def handle_test_detail(request: web.Request) -> web.Response:
    try:
        test_id = int(request.query.get("test_id", "0"))
    except Exception:
        return web.json_response({"error": "invalid test_id"}, status=400)
    async with SessionLocal() as session:
        t = await get_test(session, test_id)
        cnt = await count_baseline_submissions(session, test_id)
        return web.json_response(
            {
                "ok": True,
                "test": {
                    "id": t.id,
                    "name": t.name,
                    "category": t.category,
                    "num_questions": t.num_questions,
                    "is_rasch": bool(t.is_rasch),
                    "baseline_ready": (cnt >= 10) if t.is_rasch else True,
                },
            }
        )


async def handle_admin_save_answers(request: web.Request) -> web.Response:
    body = await _json(request)
    try:
        user = _user_from_request(request, body)
    except Exception as e:
        return web.json_response({"error": str(e)}, status=401)
    tg_id = int(user.get("id", 0) or 0)
    roles = set(_roles_for_tg(tg_id))
    if not (roles & {"admin", "ceo"}):
        return web.json_response({"error": "admin only"}, status=403)

    try:
        test_id = int(body.get("test_id"))
    except Exception:
        return web.json_response({"error": "invalid test_id"}, status=400)

    answers_raw = body.get("answers")
    if not isinstance(answers_raw, dict):
        return web.json_response({"error": "answers must be an object"}, status=400)

    async with SessionLocal() as session:
        t = await get_test(session, test_id)

        answers: Dict[int, str] = {}
        for i in range(1, t.num_questions + 1):
            v = answers_raw.get(str(i), "")
            spec = normalize_to_spec(v)
            answers[i] = encode_for_storage(spec) if (spec.choices or spec.manual) else ""

        await replace_test_answers(session, test_id, answers)

    return web.json_response({"ok": True})


async def handle_admin_baseline_submit(request: web.Request) -> web.Response:
    body = await _json(request)
    try:
        user = _user_from_request(request, body)
    except Exception as e:
        return web.json_response({"error": str(e)}, status=401)
    tg_id = int(user.get("id", 0) or 0)
    roles = set(_roles_for_tg(tg_id))
    if not (roles & {"admin", "ceo"}):
        return web.json_response({"error": "admin only"}, status=403)

    try:
        test_id = int(body.get("test_id"))
        idx = int(body.get("baseline_index"))
    except Exception:
        return web.json_response({"error": "invalid params"}, status=400)
    if idx < 1 or idx > 10:
        return web.json_response({"error": "baseline_index must be 1..10"}, status=400)

    answers_raw = body.get("answers")
    if not isinstance(answers_raw, dict):
        return web.json_response({"error": "answers must be an object"}, status=400)

    baseline_tg = -idx

    async with SessionLocal() as session:
        t = await get_test(session, test_id)
        if not t.is_rasch:
            return web.json_response({"error": "baseline faqat Rasch testlar uchun"}, status=400)
        await ensure_baseline_users(session)

        # delete previous baseline submission for this baseline user
        await delete_submissions_for_user_test(session, baseline_tg, test_id)

        answers: Dict[int, str] = {}
        for i in range(1, t.num_questions + 1):
            v = answers_raw.get(str(i), "")
            spec = normalize_to_spec(v)
            answers[i] = encode_for_storage(spec) if (spec.choices or spec.manual) else ""

        correct = await get_correct_answers(session, test_id)
        res_simple = simple_check(answers, correct, t.num_questions)
        await save_submission(
            session,
            tg_id=baseline_tg,
            test_id=test_id,
            answers=answers,
            raw_correct=res_simple.raw_correct,
            total=res_simple.total,
            score=0.0,
            is_rasch=True,
        )

        done = await list_baseline_done_indices(session, test_id)
        return web.json_response({"ok": True, "done": done, "have": len(done), "need": 10})


async def handle_admin_baseline_status(request: web.Request) -> web.Response:
    try:
        user = _user_from_request(request, {})
    except Exception as e:
        return web.json_response({"error": str(e)}, status=401)
    tg_id = int(user.get("id", 0) or 0)
    roles = set(_roles_for_tg(tg_id))
    if not (roles & {"admin", "ceo"}):
        return web.json_response({"error": "admin only"}, status=403)
    try:
        test_id = int(request.query.get("test_id", "0"))
    except Exception:
        return web.json_response({"error": "invalid test_id"}, status=400)
    async with SessionLocal() as session:
        done = await list_baseline_done_indices(session, test_id)
    return web.json_response({"ok": True, "done": done, "have": len(done), "need": 10})


async def _tg_send_document(*, tg_id: int, file_path: Path, caption: str = "") -> bool:
    """Send a document to user chat via Bot API."""
    token = settings.bot_token
    if not token:
        return False
    url = f"https://api.telegram.org/bot{token}/sendDocument"
    try:
        data = aiohttp.FormData()
        data.add_field("chat_id", str(tg_id))
        if caption:
            data.add_field("caption", caption)
        data.add_field(
            "document",
            file_path.open("rb"),
            filename=file_path.name,
            content_type="application/pdf",
        )
        async with aiohttp.ClientSession(timeout=aiohttp.ClientTimeout(total=20)) as s:
            async with s.post(url, data=data) as resp:
                js = await resp.json(content_type=None)
        return bool(isinstance(js, dict) and js.get("ok"))
    except Exception:
        return False


async def handle_send_certificate(request: web.Request) -> web.Response:
    """MiniApp button: sends the last certificate PDF to bot chat."""
    body = await _json(request)
    try:
        user = _user_from_request(request, body)
    except Exception as e:
        return web.json_response({"error": str(e)}, status=401)

    tg_id = int(user.get("id", 0) or 0)
    if not tg_id:
        return web.json_response({"error": "invalid tg user"}, status=400)

    try:
        cert_id = int(body.get("certificate_id") or 0)
    except Exception:
        cert_id = 0
    if cert_id <= 0:
        return web.json_response({"error": "missing certificate_id"}, status=400)

    p = await get_certificate_path_for_user(cert_id=cert_id, tg_id=tg_id)
    if not p:
        return web.json_response({"error": "certificate not found"}, status=404)

    ok = await _tg_send_document(tg_id=tg_id, file_path=p, caption="🏅 Sertifikat")
    if not ok:
        return web.json_response({"error": "send failed"}, status=500)
    return web.json_response({"ok": True})


async def create_app() -> web.Application:
    app = web.Application()
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

    # static assets folder (optional)
    static_dir = MINIAPP_DIR / "static"
    if static_dir.exists():
        app.router.add_static("/static", static_dir)

    return app

async def health(request):
    return web.json_response({"ok": True})

app.router.add_get("/health", health)
app.router.add_get("/", health)


async def start_miniapp() -> web.AppRunner:
    app = await create_app()
    runner = web.AppRunner(app)
    await runner.setup()
    site = web.TCPSite(runner, host=settings.miniapp_host, port=int(settings.miniapp_port))
    await site.start()
    return runner
