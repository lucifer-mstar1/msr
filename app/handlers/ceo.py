from __future__ import annotations

from datetime import datetime
from pathlib import Path
from typing import List, Tuple

from aiogram import Router
from aiogram.filters import Command
from aiogram.types import Message, FSInputFile
from reportlab.lib.pagesizes import A4
from reportlab.lib.units import mm
from reportlab.pdfgen import canvas
from sqlalchemy import select

from app.db import SessionLocal
from app.models import User
from app.settings import settings
from app.keyboards import ceo_menu_kb


router = Router()

DATA_DIR = Path("data")
REPORTS_DIR = DATA_DIR / "reports"
REPORTS_DIR.mkdir(parents=True, exist_ok=True)


def _is_ceo(tg_id: int) -> bool:
    return tg_id in set(settings.ceo_tg_ids or [])


async def _fetch_users() -> List[Tuple[int, str, str, str, str, str, str]]:
    """Returns rows: (tg_id, full_name, username, phone, registered, baseline, created_at_str)."""
    async with SessionLocal() as session:
        res = await session.execute(select(User).order_by(User.created_at.asc(), User.id.asc()))
        users = res.scalars().all()

    out: List[Tuple[int, str, str, str, str, str, str]] = []
    for u in users:
        full = (f"{u.first_name or ''} {u.last_name or ''}").strip() or "-"
        uname = (u.username or "").strip()
        uname = f"@{uname}" if uname and not uname.startswith("@") else (uname or "-")
        phone = (u.phone or "-").strip() or "-"
        reg = "Ha" if u.is_registered else "Yo'q"
        base = "Ha" if u.is_baseline else "Yo'q"
        created = (u.created_at or datetime.utcnow()).strftime("%Y-%m-%d %H:%M")
        out.append((int(u.tg_id), full, uname, phone, reg, base, created))
    return out


def _render_users_pdf(rows: List[Tuple[int, str, str, str, str, str, str]]) -> Path:
    ts = datetime.utcnow().strftime("%Y%m%d_%H%M%S")
    out = REPORTS_DIR / f"msr_users_{ts}.pdf"

    c = canvas.Canvas(str(out), pagesize=A4)
    w, h = A4
    margin = 14 * mm

    # Header
    c.setTitle("MSR Users Report")
    c.setFont("Helvetica-Bold", 15)
    c.drawString(margin, h - margin, "MSR — Userlar hisobot")
    c.setFont("Helvetica", 10)
    c.drawString(margin, h - margin - 14, f"Yaratilgan: {datetime.utcnow().strftime('%Y-%m-%d %H:%M UTC')}")
    c.drawRightString(w - margin, h - margin - 14, f"Jami: {len(rows)}")

    # Columns
    y = h - margin - 34
    line_h = 10
    col = {
        "tg": margin,
        "name": margin + 44 * mm,
        "user": margin + 110 * mm,
        "phone": margin + 142 * mm,
        "reg": margin + 172 * mm,
        "created": margin + 188 * mm,
    }

    def header_row():
        nonlocal y
        c.setFont("Helvetica-Bold", 9)
        c.setFillGray(0)
        c.drawString(col["tg"], y, "TG_ID")
        c.drawString(col["name"], y, "Ism Familiya")
        c.drawString(col["user"], y, "Username")
        c.drawString(col["phone"], y, "Telefon")
        c.drawString(col["reg"], y, "Reg")
        c.drawString(col["created"], y, "Qo'shilgan")
        y -= line_h
        c.setLineWidth(0.6)
        c.setStrokeGray(0.75)
        c.line(margin, y, w - margin, y)
        y -= 6

    def new_page():
        nonlocal y
        c.showPage()
        c.setFont("Helvetica-Bold", 15)
        c.drawString(margin, h - margin, "MSR — Userlar hisobot")
        c.setFont("Helvetica", 10)
        c.drawString(margin, h - margin - 14, f"Davom etadi — {datetime.utcnow().strftime('%Y-%m-%d %H:%M UTC')}")
        y = h - margin - 34
        header_row()

    header_row()

    c.setFont("Helvetica", 8.5)
    c.setFillGray(0)

    for i, (tg_id, full, uname, phone, reg, base, created) in enumerate(rows, start=1):
        if y < margin + 18:
            new_page()

        # TG id
        c.drawString(col["tg"], y, str(tg_id))

        # Name (truncate gently)
        name_txt = (full[:42] + "…") if len(full) > 43 else full
        c.drawString(col["name"], y, name_txt)

        # Username
        u_txt = (uname[:18] + "…") if len(uname) > 19 else uname
        c.drawString(col["user"], y, u_txt)

        # Phone
        p_txt = (phone[:16] + "…") if len(phone) > 17 else phone
        c.drawString(col["phone"], y, p_txt)

        # Registered + baseline mark
        r_txt = reg
        if base == "Ha":
            r_txt = f"{reg}*"
        c.drawString(col["reg"], y, r_txt)

        # Created
        c.drawString(col["created"], y, created)

        y -= line_h

        # Subtle row lines
        if i % 2 == 0:
            c.setStrokeGray(0.92)
            c.line(margin, y + 2, w - margin, y + 2)
            c.setStrokeGray(0.75)

    # Footer note
    if y < margin + 40:
        new_page()
    c.setFont("Helvetica", 8)
    c.setFillGray(0.35)
    c.drawString(margin, margin + 10, "* Baseline = Rasch bazasi uchun fake user")

    c.save()
    return out


@router.message(Command("ceo"))
async def ceo_entry(message: Message) -> None:
    if not message.from_user:
        return
    if not _is_ceo(message.from_user.id):
        await message.answer("Bu bo'lim faqat CEO uchun.")
        return
    await message.answer("👑 CEO menyu:", reply_markup=ceo_menu_kb())


@router.message(lambda m: (m.text or "").strip() in {"Userlar ro'yxatini olish (pdf)", "📥 Userlar PDF"})
async def ceo_users_pdf(message: Message) -> None:
    if not message.from_user:
        return
    if not _is_ceo(message.from_user.id):
        return

    rows = await _fetch_users()
    pdf_path = _render_users_pdf(rows)
    caption = f"📄 Userlar hisobot (jami {len(rows)})"
    await message.answer_document(FSInputFile(str(pdf_path)), caption=caption)
