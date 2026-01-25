from __future__ import annotations

from pathlib import Path

from aiogram import Router, F
from aiogram.filters import CommandStart
from aiogram.types import Message, FSInputFile, CallbackQuery

from app.db import SessionLocal
from app.keyboards import (
    join_gate_kb,
    main_menu_kb,
    admin_menu_reply_kb,
    ceo_menu_kb,
    request_contact_kb,
)
from app.settings import settings
from app.services.repo import (
    get_or_create_user,
    get_setting,
    mark_registered,
    get_user,
)
from app.services.certificates_store import get_certificate_path

router = Router()


def _is_ceo(tg_id: int) -> bool:
    return tg_id in set(settings.ceo_tg_ids or [])


def _is_admin(tg_id: int) -> bool:
    return tg_id in set(settings.admin_tg_ids or [])


def _roles_for_tg(tg_id: int) -> set[str]:
    roles = {"user"}
    if _is_admin(tg_id):
        roles.add("admin")
    if _is_ceo(tg_id):
        roles.add("ceo")
    return roles


def _normalize_chat_ref(ref: str) -> str:
    r = (ref or "").strip()
    if r.startswith("https://t.me/"):
        r = r.replace("https://t.me/", "@", 1)
    return r


async def _get_required_channel() -> str:
    async with SessionLocal() as session:
        v = (await get_setting(session, "required_channel", settings.required_channel)).strip()
    return v


async def _get_required_group() -> str:
    async with SessionLocal() as session:
        v = (await get_setting(session, "required_group", settings.required_group)).strip()
    return v


async def _get_required_urls() -> tuple[str, str]:
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


async def _check_membership(message: Message) -> bool:
    ch = _normalize_chat_ref(await _get_required_channel())
    gr = _normalize_chat_ref(await _get_required_group())
    if not ch and not gr:
        return True

    async def is_member(chat_ref: str) -> bool:
        if not chat_ref:
            return True
        try:
            member = await message.bot.get_chat_member(chat_ref, message.from_user.id)
            return member.status in {"member", "administrator", "creator"}
        except Exception:
            return False

    return (await is_member(ch)) and (await is_member(gr))


@router.callback_query(F.data == "gate_check")
async def gate_check(callback: CallbackQuery) -> None:
    if not callback.message:
        return
    await callback.answer()
    ok = await _check_membership(callback.message)
    if ok:
        tg_id = callback.from_user.id if callback.from_user else 0
        await callback.message.answer("✅ Tasdiqlandi. Menyu:", reply_markup=main_menu_kb(_roles_for_tg(tg_id)))
    else:
        ch_url, gr_url = await _get_required_urls()
        await callback.message.answer(
            "❗️ Hali kanal/guruhga qo‘shilmagansiz. Iltimos, avval qo‘shiling.",
            reply_markup=join_gate_kb(ch_url, gr_url),
        )


@router.callback_query(F.data == "nav:home")
async def nav_home(callback: CallbackQuery) -> None:
    if not callback.message or not callback.from_user:
        return
    await callback.answer()
    await callback.message.answer(
        "🏠 Asosiy menyu:",
        reply_markup=main_menu_kb(_roles_for_tg(callback.from_user.id)),
    )


@router.message(F.text.in_({"Clear", "🧹 Clear"}))
async def clear_chat(message: Message) -> None:
    chat_id = message.chat.id
    start_id = message.message_id
    for mid in range(start_id, max(1, start_id - 200), -1):
        try:
            await message.bot.delete_message(chat_id, mid)
        except Exception:
            pass

    tg_id = message.from_user.id if message.from_user else 0
    try:
        await message.answer("✅ Tozalandi.", reply_markup=main_menu_kb(_roles_for_tg(tg_id)))
    except Exception:
        pass


# ✅ ENG MUHIM FIX: contact handler'ni F.contact bilan ushlash
@router.message(F.contact)
async def contact_received(message: Message) -> None:
    if not message.from_user or not message.contact:
        return

    # faqat o'z kontaktini qabul qilamiz (ba'zida user_id bo'lmaydi, shuning uchun ehtiyotkorlik bilan)
    if message.contact.user_id and message.contact.user_id != message.from_user.id:
        await message.answer("Iltimos, faqat o'zingizning kontaktingizni yuboring.")
        return

    phone = (message.contact.phone_number or "").strip()

    async with SessionLocal() as session:
        await get_or_create_user(
            session,
            tg_id=message.from_user.id,
            first_name=message.from_user.first_name or "",
            last_name=message.from_user.last_name or "",
            username=message.from_user.username or "",
        )
        await mark_registered(session, message.from_user.id, phone)

    kb = main_menu_kb(_roles_for_tg(message.from_user.id))
    # ixtiyoriy: contact keyboardni yopish uchun reply_markup=None ham qilish mumkin
    await message.answer("✅ Telefon raqamingiz saqlandi.", reply_markup=kb)


@router.message(F.text.in_({"🏠 Asosiy sahifa", "🏠 Asosiy"}))
async def go_home(message: Message) -> None:
    if not message.from_user:
        return
    await message.answer("🏠 Asosiy menyu:", reply_markup=main_menu_kb(_roles_for_tg(message.from_user.id)))


@router.message(F.text == "🛠 Admin panel")
async def open_admin_panel(message: Message) -> None:
    if not message.from_user:
        return
    if not _is_admin(message.from_user.id):
        await message.answer("⛔️ Ruxsat yo‘q.", reply_markup=main_menu_kb(_roles_for_tg(message.from_user.id)))
        return
    await message.answer("🛠 Admin panel:", reply_markup=admin_menu_reply_kb())


@router.message(F.text == "👑 CEO panel")
async def open_ceo_panel(message: Message) -> None:
    if not message.from_user:
        return
    if not _is_ceo(message.from_user.id):
        await message.answer("⛔️ Ruxsat yo‘q.", reply_markup=main_menu_kb(_roles_for_tg(message.from_user.id)))
        return
    await message.answer("👑 CEO panel:", reply_markup=ceo_menu_kb())


@router.message(F.text.in_({"⬅️ Orqaga", "⬅️ Ortga"}))
async def go_back_to_main(message: Message) -> None:
    if not message.from_user:
        return
    await message.answer("⬅️ Orqaga", reply_markup=main_menu_kb(_roles_for_tg(message.from_user.id)))


async def _handle_start_payload(message: Message, payload: str) -> bool:
    payload = (payload or "").strip()
    if not payload:
        return False

    if payload.startswith("pdf_"):
        try:
            test_id = int(payload.split("_", 1)[1])
        except Exception:
            return False

        from app.services.repo import get_test
        async with SessionLocal() as session:
            t = await get_test(session, test_id)

        fpath = Path(t.pdf_path or "")
        if not fpath.exists():
            await message.answer("PDF topilmadi. Admin qayta yuklashi kerak.")
            return True

        await message.answer_document(FSInputFile(str(fpath)), caption=f"📄 {t.name}")
        return True

    if payload.startswith("cert_"):
        try:
            cert_id = int(payload.split("_", 1)[1])
        except Exception:
            return False
        path = await get_certificate_path(cert_id)
        if not path:
            await message.answer("Sertifikat topilmadi.")
            return True
        await message.answer_document(FSInputFile(str(path)), caption="📄 Sertifikat")
        return True

    return False


@router.message(CommandStart())
async def start(message: Message) -> None:
    if not message.from_user:
        return

    async with SessionLocal() as session:
        await get_or_create_user(
            session,
            tg_id=message.from_user.id,
            first_name=message.from_user.first_name or "",
            last_name=message.from_user.last_name or "",
            username=message.from_user.username or "",
        )

    ok = await _check_membership(message)
    if not ok:
        ch_url, gr_url = await _get_required_urls()
        await message.answer(
            "Botdan foydalanish uchun avval kanal va guruhga qo'shiling, so'ng ✅ Tekshirib ko'rish tugmasini bosing.",
            reply_markup=join_gate_kb(ch_url, gr_url),
        )
        return

    # payload
    parts = (message.text or "").split(maxsplit=1)
    if len(parts) == 2:
        if await _handle_start_payload(message, parts[1]):
            return

    roles = _roles_for_tg(message.from_user.id)
    kb = main_menu_kb(roles)

    # registration (phone)
    async with SessionLocal() as session:
        u = await get_user(session, message.from_user.id)

    ceo_only = ("ceo" in roles) and ("admin" not in roles)
    if u and not u.is_registered and not ceo_only:
        await message.answer(
            f"✅ Tasdiq: *{', '.join(sorted(roles)).upper()}*\n\n📞 Davom etish uchun telefon raqamingizni yuboring.",
            parse_mode="Markdown",
            reply_markup=request_contact_kb(),
        )
        return

    await message.answer(
        f"✅ Tasdiq: *{', '.join(sorted(roles)).upper()}*\nMenyu:",
        parse_mode="Markdown",
        reply_markup=kb,
    )
