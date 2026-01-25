from __future__ import annotations

import asyncio
from pathlib import Path

from aiohttp import web

from app.db import SessionLocal
from app.settings import settings
from app.services.repo import create_test, list_tests_by_category, delete_test, replace_test_pdf, replace_test_answers

UPLOAD_DIR = Path("data/uploads")


def _require_token(request: web.Request) -> None:
    if not settings.admin_panel_token:
        return
    token = request.query.get("token", "")
    if token != settings.admin_panel_token:
        raise web.HTTPUnauthorized(text="Bad token")


async def index(request: web.Request) -> web.Response:
    _require_token(request)
    html = """<h2>Telegram Test Bot Admin</h2>
    <ul>
      <li><a href='/admin/create'>Create Test</a></li>
      <li><a href='/admin/list'>List/Delete Tests</a></li>
    </ul>"""
    return web.Response(text=html, content_type="text/html")


async def create_page(request: web.Request) -> web.Response:
    _require_token(request)
    html = """<h3>Create Test</h3>
    <form method='post' enctype='multipart/form-data'>
      <label>Category: <input name='category' placeholder='sat/milliy/dtm/prezident/mavzu'></label><br/>
      <label>Name: <input name='name' placeholder='Test 1'></label><br/>
      <label>Questions: <input name='num_questions' type='number' value='10'></label><br/>
      <label>PDF: <input name='pdf' type='file'></label><br/>
      <label>Correct answers (JSON like {"1":"A","2":"B"}):</label><br/>
      <textarea name='answers' rows='6' cols='60'>{}</textarea><br/>
      <button type='submit'>Create</button>
    </form>
    <p><a href='/admin'>Back</a></p>
    """.format("{}")
    return web.Response(text=html, content_type="text/html")


async def create_submit(request: web.Request) -> web.Response:
    _require_token(request)
    data = await request.post()
    category = (data.get("category") or "").strip()
    name = (data.get("name") or "").strip()
    num_questions = int(data.get("num_questions") or 0)
    answers_raw = (data.get("answers") or "{}").strip()
    try:
        import json
        ans = json.loads(answers_raw) if answers_raw else {}
        correct_answers = {int(k): str(v) for k, v in ans.items()}
    except Exception:
        return web.Response(text="Bad answers JSON", status=400)

    pdf_field = data.get("pdf")
    pdf_path = ""
    if pdf_field and hasattr(pdf_field, "filename"):
        UPLOAD_DIR.mkdir(parents=True, exist_ok=True)
        dest = UPLOAD_DIR / f"{category}_{name}_{pdf_field.filename}"
        content = pdf_field.file.read()
        dest.write_bytes(content)
        pdf_path = str(dest)

    is_rasch = category in {"sat", "milliy"}

    async with SessionLocal() as session:
        await create_test(
            session,
            category=category,
            name=name,
            num_questions=num_questions,
            pdf_path=pdf_path,
            correct_answers=correct_answers,
            is_rasch=is_rasch,
        )

    raise web.HTTPFound("/admin?ok=1")


async def list_page(request: web.Request) -> web.Response:
    _require_token(request)
    import html
    rows = []
    async with SessionLocal() as session:
        for cat in ["milliy", "sat", "dtm", "prezident", "mavzu"]:
            tests = await list_tests_by_category(session, cat)
            if not tests:
                continue
            rows.append(f"<h4>{html.escape(cat)}</h4><ul>")
            for tid, name in tests:
                rows.append(f"<li>#{tid} {html.escape(name)} <a href='/admin/delete?id={tid}'>Delete</a></li>")
            rows.append("</ul>")
    body = "<h3>Tests</h3>" + "".join(rows) + "<p><a href='/admin'>Back</a></p>"
    return web.Response(text=body, content_type="text/html")


async def delete_test_handler(request: web.Request) -> web.Response:
    _require_token(request)
    tid = int(request.query.get("id", "0"))
    async with SessionLocal() as session:
        await delete_test(session, tid)
    raise web.HTTPFound("/admin/list")


async def start_admin_panel() -> None:
    app = web.Application()
    app.router.add_get("/admin", index)
    app.router.add_get("/admin/create", create_page)
    app.router.add_post("/admin/create", create_submit)
    app.router.add_get("/admin/list", list_page)
    app.router.add_get("/admin/delete", delete_test_handler)

    runner = web.AppRunner(app)
    await runner.setup()
    site = web.TCPSite(runner, host=settings.admin_panel_host, port=settings.admin_panel_port)
    await site.start()
