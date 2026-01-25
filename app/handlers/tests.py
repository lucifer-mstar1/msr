from __future__ import annotations

from pathlib import Path
from typing import Optional

from aiogram import Router
from aiogram.fsm.context import FSMContext
from aiogram.fsm.state import State, StatesGroup
from aiogram.types import CallbackQuery, Message, FSInputFile

from app.db import SessionLocal
from app.keyboards import (
    CATEGORIES,
    categories_kb,
    main_menu_kb,
    tests_list_kb,
    webapp_open_kb,
)
from app.services.repo import list_tests_by_category, get_test
from app.settings import settings

router = Router()


def _is_ceo(tg_id: int) -> bool:
    return tg_id in set(settings.ceo_tg_ids or [])


def _cat_key_from_label(label: str) -> Optional[str]:
    for k, lab in CATEGORIES:
        if lab == label:
            return k
    return None


class Flow(StatesGroup):
    choosing_category = State()  # mode


def _is_admin(tg_id: int) -> bool:
    return tg_id in set(settings.admin_tg_ids or [])


def _roles_for_tg(tg_id: int) -> set[str]:
    roles = {"user"}
    if _is_admin(tg_id):
        roles.add("admin")
    if _is_ceo(tg_id):
        roles.add("ceo")
    return roles


def _menu_for(tg_id: int):
    from app.keyboards import main_menu_kb
    return main_menu_kb(_roles_for_tg(tg_id))


@router.message(lambda m: (m.text or "").strip() in {"⬅️ Ortga", "⬅️ Orqaga"})
async def go_back(message: Message, state: FSMContext) -> None:
    await state.clear()
    await message.answer("Asosiy menyu:", reply_markup=_menu_for(message.from_user.id))


@router.message(lambda m: (m.text or "").strip() in {"Test ishlash", "📄 Test PDF olish"})
async def pdf_entry(message: Message, state: FSMContext) -> None:
    await state.set_state(Flow.choosing_category)
    await state.update_data(mode="pdf")
    await message.answer("Kategoriya tanlang:", reply_markup=categories_kb(back=True))


@router.message(lambda m: (m.text or "").strip() == "Test Tekshirish")
async def check_entry(message: Message, state: FSMContext) -> None:
    await state.set_state(Flow.choosing_category)
    await state.update_data(mode="check")
    await message.answer("Kategoriya tanlang:", reply_markup=categories_kb(back=True))


@router.message(Flow.choosing_category)
async def choose_category(message: Message, state: FSMContext) -> None:
    label = (message.text or "").strip()
    if label in {"⬅️ Ortga", "⬅️ Orqaga", "🏠 Asosiy sahifa", "🏠 Asosiy"}:
        await state.clear()
        await message.answer("Asosiy menyu:", reply_markup=_menu_for(message.from_user.id))
        return

    cat_key = _cat_key_from_label(label)
    if not cat_key:
        await message.answer("Iltimos, kategoriya tugmasidan tanlang.", reply_markup=categories_kb(back=True))
        return

    async with SessionLocal() as session:
        rows = await list_tests_by_category(session, cat_key)

    if not rows:
        await message.answer("Hozircha bu kategoriyada test yo'q.", reply_markup=categories_kb(back=True))
        return

    data = await state.get_data()
    mode = (data.get("mode") or "pdf").strip()
    if mode == "check":
        await message.answer(
            "Testni tanlang (Tekshirish):",
            reply_markup=tests_list_kb(rows, prefix="check", include_back=True),
        )
    else:
        await message.answer(
            "Testni tanlang (PDF):",
            reply_markup=tests_list_kb(rows, prefix="pdf", include_back=True),
        )


@router.callback_query(lambda c: (c.data or "").startswith("pdf:"))
async def send_pdf(callback: CallbackQuery, state: FSMContext) -> None:
    if not callback.message:
        return
    await callback.answer()

    if callback.data == "pdf:back":
        await callback.message.answer("Kategoriya tanlang:", reply_markup=categories_kb(back=True))
        return

    test_id = int(callback.data.split(":")[1])
    async with SessionLocal() as session:
        t = await get_test(session, test_id)

    fpath = Path(t.pdf_path or "")
    if not fpath.exists():
        await callback.message.answer("PDF fayl topilmadi. Admin qayta yuklashi kerak.")
        return

    await state.clear()
    await callback.message.answer_document(FSInputFile(str(fpath)), caption=f"📄 {t.name}")


@router.callback_query(lambda c: (c.data or "").startswith("check:"))
async def open_check_webapp(callback: CallbackQuery, state: FSMContext) -> None:
    if not callback.message or not callback.from_user:
        return
    await callback.answer()
    if callback.data == "check:back":
        await callback.message.answer("Kategoriya tanlang:", reply_markup=categories_kb(back=True))
        return
    test_id = int(callback.data.split(":")[1])
    url = f"{settings.effective_miniapp_url}/?mode=user&test_id={test_id}"
    await state.clear()
    await callback.message.answer(
        "Mini App orqali javoblarni kiriting va tekshiring.",
        reply_markup=webapp_open_kb(url=url, label="Mini App"),
    )

