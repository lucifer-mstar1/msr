from __future__ import annotations

from pathlib import Path
from typing import Dict, Optional

from aiogram import Router
from aiogram.filters import Command
from aiogram.fsm.context import FSMContext
from aiogram.fsm.state import State, StatesGroup
from aiogram.types import CallbackQuery, Message

from app.db import SessionLocal
from app.keyboards import (
    admin_menu_kb,
    admin_menu_reply_kb,
    tests_list_kb,
    answer_choice_kb,
    finish_kb,
    confirm_kb,
    categories_kb,
    CATEGORIES,
    webapp_open_kb,
)
from app.settings import settings
from app.services.repo import (
    list_tests_by_category,
    create_test,
    replace_test_pdf,
    replace_test_answers,
    delete_test,
    get_test,
    ensure_baseline_users,
    count_baseline_submissions,
    save_submission,
    get_correct_answers,
)
from app.services.scoring import simple_check

router = Router()
DATA_DIR = Path("data")
TESTS_DIR = DATA_DIR / "tests"
TESTS_DIR.mkdir(parents=True, exist_ok=True)


# ==========================
# SIMPLE ADMIN PANEL (Reply buttons)
# ==========================

class SimpleAdminFlow(StatesGroup):
    creating_category = State()
    creating_name = State()
    creating_num = State()
    creating_pdf = State()

    editing_category = State()
    editing_pick = State()
    editing_newname = State()
    editing_newpdf = State()


def _is_admin(tg_id: int) -> bool:
    return tg_id in set(settings.admin_tg_ids or [])


def _cat_key_from_label(label: str) -> Optional[str]:
    for k, lab in CATEGORIES:
        if lab == label:
            return k
    return None


def _is_rasch_category(cat_key: str) -> bool:
    return cat_key in {"milliy", "sat"}


@router.message(lambda m: (m.text or "").strip() == "Test yaratish")
async def simple_admin_create_entry(message: Message, state: FSMContext) -> None:
    if not message.from_user or not _is_admin(message.from_user.id):
        return
    await state.clear()
    await state.set_state(SimpleAdminFlow.creating_category)
    await message.answer("Kategoriya tanlang:", reply_markup=categories_kb(back=True))


@router.message(SimpleAdminFlow.creating_category)
async def simple_admin_create_category(message: Message, state: FSMContext) -> None:
    if not message.from_user or not _is_admin(message.from_user.id):
        return
    label = (message.text or "").strip()
    if label in {"⬅️ Ortga", "⬅️ Orqaga", "🏠 Asosiy sahifa", "🏠 Asosiy"}:
        await state.clear()
        # Home/back from within flow returns to admin menu
        await message.answer("Admin menyu:", reply_markup=admin_menu_reply_kb())
        return
    cat = _cat_key_from_label(label)
    if not cat:
        await message.answer("Iltimos, kategoriya tugmasidan tanlang.", reply_markup=categories_kb(back=True))
        return
    await state.update_data(category=cat)
    await state.set_state(SimpleAdminFlow.creating_name)
    await message.answer("Test nomini kiriting (kategoriya ichida unique bo'lishi kerak):")


@router.message(SimpleAdminFlow.creating_name)
async def simple_admin_create_name(message: Message, state: FSMContext) -> None:
    if not message.from_user or not _is_admin(message.from_user.id):
        return
    name = (message.text or "").strip()
    if not name:
        await message.answer("Test nomi bo'sh bo'lmasin. Qayta kiriting:")
        return
    await state.update_data(name=name)
    await state.set_state(SimpleAdminFlow.creating_num)
    await message.answer("Savollar sonini kiriting (masalan: 40):")


@router.message(SimpleAdminFlow.creating_num)
async def simple_admin_create_num(message: Message, state: FSMContext) -> None:
    if not message.from_user or not _is_admin(message.from_user.id):
        return
    try:
        n = int((message.text or "").strip())
    except Exception:
        await message.answer("Iltimos, son kiriting (1..300):")
        return
    if n < 1 or n > 300:
        await message.answer("Savollar soni 1..300 oralig'ida bo'lsin.")
        return
    await state.update_data(num_questions=n)
    await state.set_state(SimpleAdminFlow.creating_pdf)
    await message.answer("Endi test PDF faylini yuboring (document sifatida).")


@router.message(SimpleAdminFlow.creating_pdf)
async def simple_admin_create_pdf(message: Message, state: FSMContext) -> None:
    if not message.from_user or not _is_admin(message.from_user.id):
        return
    if not message.document:
        await message.answer("PDF yuboring (Telegram 'document' sifatida).")
        return
    doc = message.document
    if not (doc.mime_type or "").lower().endswith("pdf") and not (doc.file_name or "").lower().endswith(".pdf"):
        await message.answer("Bu PDFga o'xshamaydi. Iltimos, PDF yuboring.")
        return

    data = await state.get_data()
    cat = str(data.get("category"))
    name = str(data.get("name"))
    num_questions = int(data.get("num_questions"))
    is_rasch = _is_rasch_category(cat)

    # download to temp
    tmp_path = TESTS_DIR / f"tmp_{message.from_user.id}.pdf"
    await message.bot.download(doc, destination=tmp_path)

    async with SessionLocal() as session:
        try:
            t = await create_test(
                session,
                category=cat,
                name=name,
                num_questions=num_questions,
                pdf_path=str(tmp_path),
                correct_answers={},
                is_rasch=is_rasch,
            )
        except Exception:
            # likely unique constraint
            try:
                await session.rollback()
            except Exception:
                pass
            await message.answer("Bu nomli test allaqachon bor. Boshqa nom tanlang.")
            return

        final_path = TESTS_DIR / f"test_{t.id}.pdf"
        final_path.parent.mkdir(parents=True, exist_ok=True)
        try:
            tmp_path.replace(final_path)
        except Exception:
            final_path.write_bytes(tmp_path.read_bytes())
            tmp_path.unlink(missing_ok=True)
        await replace_test_pdf(session, t.id, str(final_path))

    await state.clear()

    url = f"{settings.effective_miniapp_url}/?mode=admin&test_id={t.id}"
    await message.answer(
        "✅ Test yaratildi.\n\n"
        "1) Mini App'ni oching\n"
        "2) 'To‘g‘ri javoblar' tabida javoblarni saqlang\n"
        "3) Agar Rasch bo'lsa — 'Baseline' tabida 10 ta fake user javoblarini kiriting\n\n"
        "Shundan keyin test userlarga ko'rinadi.",
        reply_markup=webapp_open_kb(url=url, label="Mini App (Admin)"),
    )
    await message.answer("Admin menyu:", reply_markup=admin_menu_reply_kb())


@router.message(lambda m: (m.text or "").strip() == "Test edit")
async def simple_admin_edit_entry(message: Message, state: FSMContext) -> None:
    if not message.from_user or not _is_admin(message.from_user.id):
        return
    await state.clear()
    await state.set_state(SimpleAdminFlow.editing_category)
    await message.answer("Kategoriya tanlang:", reply_markup=categories_kb(back=True))


@router.message(SimpleAdminFlow.editing_category)
async def simple_admin_edit_category(message: Message, state: FSMContext) -> None:
    if not message.from_user or not _is_admin(message.from_user.id):
        return
    label = (message.text or "").strip()
    if label in {"⬅️ Ortga", "⬅️ Orqaga", "🏠 Asosiy sahifa", "🏠 Asosiy"}:
        await state.clear()
        await message.answer("Admin menyu:", reply_markup=admin_menu_reply_kb())
        return
    cat = _cat_key_from_label(label)
    if not cat:
        await message.answer("Iltimos, kategoriya tugmasidan tanlang.", reply_markup=categories_kb(back=True))
        return
    async with SessionLocal() as session:
        rows = await list_tests_by_category(session, cat)
    if not rows:
        await message.answer("Bu kategoriyada test yo'q.", reply_markup=categories_kb(back=True))
        return
    await state.update_data(category=cat)
    await state.set_state(SimpleAdminFlow.editing_pick)
    await message.answer("Tahrirlash uchun testni tanlang:", reply_markup=tests_list_kb(rows, prefix="editpick", include_back=True))


@router.callback_query(lambda c: (c.data or "").startswith("editpick:"))
async def simple_admin_edit_pick(callback: CallbackQuery, state: FSMContext) -> None:
    if not callback.message or not callback.from_user or not _is_admin(callback.from_user.id):
        return
    await callback.answer()
    if callback.data == "editpick:back":
        await state.set_state(SimpleAdminFlow.editing_category)
        await callback.message.answer("Kategoriya tanlang:", reply_markup=categories_kb(back=True))
        return
    test_id = int(callback.data.split(":", 1)[1])
    await state.update_data(test_id=test_id)

    from aiogram.utils.keyboard import InlineKeyboardBuilder
    b = InlineKeyboardBuilder()
    b.button(text="Mini App (Javob/Baseline)", callback_data="edit:open")
    b.button(text="Nomini o'zgartirish", callback_data="edit:name")
    b.button(text="PDFni almashtirish", callback_data="edit:pdf")
    b.button(text="⬅️ Orqaga", callback_data="edit:back")
    b.adjust(1)
    await callback.message.answer("Nimani tahrirlaysiz?", reply_markup=b.as_markup())


@router.callback_query(lambda c: (c.data or "") in {"edit:open", "edit:name", "edit:pdf", "edit:back"})
async def simple_admin_edit_action(callback: CallbackQuery, state: FSMContext) -> None:
    if not callback.message or not callback.from_user or not _is_admin(callback.from_user.id):
        return
    await callback.answer()
    data = await state.get_data()
    test_id = int(data.get("test_id") or 0)
    if not test_id:
        await callback.message.answer("Test tanlanmagan.")
        return

    if callback.data == "edit:back":
        # go back to tests list in same category
        cat = str(data.get("category") or "")
        async with SessionLocal() as session:
            rows = await list_tests_by_category(session, cat)
        await state.set_state(SimpleAdminFlow.editing_pick)
        await callback.message.answer("Tahrirlash uchun testni tanlang:", reply_markup=tests_list_kb(rows, prefix="editpick", include_back=True))
        return

    if callback.data == "edit:open":
        url = f"{settings.effective_miniapp_url}/?mode=admin&test_id={test_id}"
        await callback.message.answer("Mini App (Admin) ni oching:", reply_markup=webapp_open_kb(url=url, label="Mini App (Admin)"))
        return

    if callback.data == "edit:name":
        await state.set_state(SimpleAdminFlow.editing_newname)
        await callback.message.answer("Yangi nomni kiriting:")
        return

    if callback.data == "edit:pdf":
        await state.set_state(SimpleAdminFlow.editing_newpdf)
        await callback.message.answer("Yangi PDF yuboring (document sifatida).")
        return


@router.message(SimpleAdminFlow.editing_newname)
async def simple_admin_edit_newname(message: Message, state: FSMContext) -> None:
    if not message.from_user or not _is_admin(message.from_user.id):
        return
    new_name = (message.text or "").strip()
    if not new_name:
        await message.answer("Nom bo'sh bo'lmasin. Qayta kiriting:")
        return
    data = await state.get_data()
    test_id = int(data.get("test_id") or 0)
    if not test_id:
        await message.answer("Test tanlanmagan.")
        return
    from app.services.repo import replace_test_name
    async with SessionLocal() as session:
        try:
            await replace_test_name(session, test_id, new_name)
        except Exception:
            try:
                await session.rollback()
            except Exception:
                pass
            await message.answer("Bu nomli test allaqachon bor. Boshqa nom tanlang.")
            return
    await state.set_state(SimpleAdminFlow.editing_pick)
    await message.answer("✅ Nomi yangilandi.")
    # re-show edit options
    from aiogram.utils.keyboard import InlineKeyboardBuilder
    b = InlineKeyboardBuilder()
    b.button(text="Mini App (Javob/Baseline)", callback_data="edit:open")
    b.button(text="Nomini o'zgartirish", callback_data="edit:name")
    b.button(text="PDFni almashtirish", callback_data="edit:pdf")
    b.button(text="⬅️ Orqaga", callback_data="edit:back")
    b.adjust(1)
    await message.answer("Nimani tahrirlaysiz?", reply_markup=b.as_markup())


@router.message(SimpleAdminFlow.editing_newpdf)
async def simple_admin_edit_newpdf(message: Message, state: FSMContext) -> None:
    if not message.from_user or not _is_admin(message.from_user.id):
        return
    if not message.document:
        await message.answer("PDF yuboring (document sifatida).")
        return
    doc = message.document
    if not (doc.mime_type or "").lower().endswith("pdf") and not (doc.file_name or "").lower().endswith(".pdf"):
        await message.answer("Bu PDFga o'xshamaydi. Iltimos, PDF yuboring.")
        return
    data = await state.get_data()
    test_id = int(data.get("test_id") or 0)
    if not test_id:
        await message.answer("Test tanlanmagan.")
        return

    tmp_path = TESTS_DIR / f"tmp_replace_{message.from_user.id}.pdf"
    await message.bot.download(doc, destination=tmp_path)
    final_path = TESTS_DIR / f"test_{test_id}.pdf"
    try:
        tmp_path.replace(final_path)
    except Exception:
        final_path.write_bytes(tmp_path.read_bytes())
        tmp_path.unlink(missing_ok=True)

    async with SessionLocal() as session:
        await replace_test_pdf(session, test_id, str(final_path))

    await state.set_state(SimpleAdminFlow.editing_pick)
    await message.answer("✅ PDF yangilandi. (Userlar endi qayta tekshirishi mumkin)")

    from aiogram.utils.keyboard import InlineKeyboardBuilder
    b = InlineKeyboardBuilder()
    b.button(text="Mini App (Javob/Baseline)", callback_data="edit:open")
    b.button(text="Nomini o'zgartirish", callback_data="edit:name")
    b.button(text="PDFni almashtirish", callback_data="edit:pdf")
    b.button(text="⬅️ Orqaga", callback_data="edit:back")
    b.adjust(1)
    await message.answer("Nimani tahrirlaysiz?", reply_markup=b.as_markup())


def _is_admin(tg_id: int) -> bool:
    return tg_id in set(settings.admin_tg_ids or [])


def _cat_key_from_label(label: str) -> Optional[str]:
    for k, lab in CATEGORIES:
        if lab == label:
            return k
    return None


class AdminFlow(StatesGroup):
    menu = State()

    # create
    create_choose_category = State()
    create_name = State()
    create_num = State()
    create_pdf = State()
    create_answers = State()          # q loop
    create_answers_finish = State()

    # replace
    replace_choose_category = State()
    replace_choose_test = State()
    replace_pdf = State()
    replace_answers = State()

    # delete
    delete_choose_category = State()
    delete_choose_test = State()
    delete_confirm = State()

    # baseline
    baseline_choose_category = State()
    baseline_choose_test = State()
    baseline_fake_user = State()      # 1..10
    baseline_answers = State()        # q loop
    baseline_finish = State()


@router.message(Command("admin"))
async def admin_entry(message: Message, state: FSMContext) -> None:
    if not _is_admin(message.from_user.id):
        await message.answer("Siz admin emassiz.")
        return
    await state.set_state(AdminFlow.menu)
    await message.answer("🛠 Admin panel:", reply_markup=admin_menu_kb())


@router.callback_query(lambda c: (c.data or "") == "admin:menu")
async def admin_menu_cb(callback: CallbackQuery, state: FSMContext) -> None:
    if not callback.message:
        return
    if not _is_admin(callback.from_user.id):
        return
    await callback.answer()
    await state.set_state(AdminFlow.menu)
    await callback.message.answer("🛠 Admin panel:", reply_markup=admin_menu_kb())


# ---------------- CREATE ----------------

@router.callback_query(lambda c: (c.data or "") == "admin:create")
async def admin_create_start(callback: CallbackQuery, state: FSMContext) -> None:
    if not callback.message:
        return
    await callback.answer()
    if not _is_admin(callback.from_user.id):
        return
    await state.set_state(AdminFlow.create_choose_category)
    await callback.message.answer("Kategoriya tanlang (test qaysi bo‘limga tegishli?):", reply_markup=categories_kb(back=True))


@router.message(AdminFlow.create_choose_category)
async def admin_create_cat(message: Message, state: FSMContext) -> None:
    if not _is_admin(message.from_user.id):
        return
    if (message.text or "").strip() in {"⬅️ Ortga", "⬅️ Orqaga", "🏠 Asosiy sahifa", "🏠 Asosiy"}:
        await state.set_state(AdminFlow.menu)
        await message.answer("🛠 Admin panel:", reply_markup=admin_menu_kb())
        return
    cat_key = _cat_key_from_label((message.text or "").strip())
    if not cat_key:
        await message.answer("Kategoriya tugmasidan tanlang.", reply_markup=categories_kb(back=True))
        return
    await state.update_data(category=cat_key)
    await state.set_state(AdminFlow.create_name)
    await message.answer("Test nomini kiriting. Masalan: Test 1")


@router.message(AdminFlow.create_name)
async def admin_create_name(message: Message, state: FSMContext) -> None:
    if not _is_admin(message.from_user.id):
        return
    name = (message.text or "").strip()
    if not name:
        await message.answer("Iltimos, test nomini kiriting.")
        return
    await state.update_data(name=name)
    await state.set_state(AdminFlow.create_num)
    await message.answer("Savollar sonini kiriting (masalan: 52).")


@router.message(AdminFlow.create_num)
async def admin_create_num(message: Message, state: FSMContext) -> None:
    if not _is_admin(message.from_user.id):
        return
    try:
        n = int((message.text or "").strip())
        if n <= 0 or n > 300:
            raise ValueError()
    except Exception:
        await message.answer("Noto‘g‘ri son. Masalan: 52")
        return
    await state.update_data(num_questions=n)
    await state.set_state(AdminFlow.create_pdf)
    await message.answer("Endi PDF faylni yuboring (document sifatida).")


@router.message(AdminFlow.create_pdf)
async def admin_create_pdf(message: Message, state: FSMContext) -> None:
    if not _is_admin(message.from_user.id):
        return
    if not message.document:
        await message.answer("Iltimos, PDF faylni *document* qilib yuboring.", parse_mode="Markdown")
        return
    if (message.document.mime_type or "") != "application/pdf":
        await message.answer("Iltimos, aynan PDF yuboring.")
        return

    data = await state.get_data()
    category = data["category"]
    name = data["name"]
    n = int(data["num_questions"])

    # vaqtinchalik nom; test_id yaratilgach qayta saqlaymiz
    tmp_path = TESTS_DIR / f"tmp_{message.document.file_id}.pdf"
    await message.bot.download(message.document, destination=tmp_path)

    await state.update_data(tmp_pdf=str(tmp_path))
    await state.update_data(answers={}, q=1)

    await state.set_state(AdminFlow.create_answers)
    await message.answer(
        f"✅ PDF qabul qilindi.\nEndi to‘g‘ri javoblarni kiriting.\nSavol 1/{n}:",
        reply_markup=answer_choice_kb("aa", include_back=True, include_finish=False),
    )


@router.callback_query(AdminFlow.create_answers, lambda c: (c.data or "").startswith("aa:"))
async def admin_create_answer_cb(callback: CallbackQuery, state: FSMContext) -> None:
    if not callback.message:
        return
    await callback.answer()
    if not _is_admin(callback.from_user.id):
        return

    action = (callback.data or "").split(":", 1)[1]
    if action == "back":
        await state.set_state(AdminFlow.menu)
        await callback.message.answer("🛠 Admin panel:", reply_markup=admin_menu_kb())
        return

    data = await state.get_data()
    q = int(data["q"])
    n = int(data["num_questions"])
    answers: Dict[int, str] = dict(data.get("answers", {}))
    ans = "" if action == "_" else action
    answers[q] = ans

    q_next = q + 1
    if q_next <= n:
        await state.update_data(q=q_next, answers=answers)
        await callback.message.answer(
            f"Savol {q_next}/{n}:",
            reply_markup=answer_choice_kb("aa", include_back=True, include_finish=False),
        )
    else:
        await state.update_data(answers=answers)
        await state.set_state(AdminFlow.create_answers_finish)
        await callback.message.answer("✅ Hammasi tayyor. *Upload* qilish uchun tasdiqlang.", parse_mode="Markdown", reply_markup=confirm_kb("acreate", yes_label="📤 Upload", no_label="❌ Bekor"))


@router.callback_query(AdminFlow.create_answers_finish, lambda c: (c.data or "").startswith("acreate:"))
async def admin_create_finish(callback: CallbackQuery, state: FSMContext) -> None:
    if not callback.message:
        return
    await callback.answer()
    if not _is_admin(callback.from_user.id):
        return
    choice = callback.data.split(":")[1]
    if choice == "no":
        await state.set_state(AdminFlow.menu)
        await callback.message.answer("Bekor qilindi.", reply_markup=admin_menu_kb())
        return

    data = await state.get_data()
    category = data["category"]
    name = data["name"]
    n = int(data["num_questions"])
    answers: Dict[int, str] = dict(data.get("answers", {}))
    tmp_pdf = Path(data["tmp_pdf"])

    is_rasch = category in {"sat", "milliy"}

    async with SessionLocal() as session:
        t = await create_test(
            session,
            category=category,
            name=name,
            num_questions=n,
            pdf_path="",  # hozircha
            correct_answers=answers,
            is_rasch=is_rasch,
        )

        final_pdf = TESTS_DIR / f"test_{t.id}.pdf"
        tmp_pdf.replace(final_pdf)
        await replace_test_pdf(session, t.id, str(final_pdf))

    await state.set_state(AdminFlow.menu)
    msg = f"✅ Test yaratildi: *{name}* (ID: {t.id})."
    if is_rasch:
        msg += "\n\n⚠️ Bu Rasch test. Endi *Rasch bazasi (10 ta)* bo‘limida 10 ta baseline javoblarini kiriting."
    await callback.message.answer(msg, parse_mode="Markdown", reply_markup=admin_menu_kb())


# ---------------- REPLACE ----------------

@router.callback_query(lambda c: (c.data or "") == "admin:replace")
async def admin_replace_start(callback: CallbackQuery, state: FSMContext) -> None:
    if not callback.message:
        return
    await callback.answer()
    if not _is_admin(callback.from_user.id):
        return
    await state.set_state(AdminFlow.replace_choose_category)
    await callback.message.answer("Qaysi kategoriyadagi testni yangilaysiz?", reply_markup=categories_kb(back=True))


@router.message(AdminFlow.replace_choose_category)
async def admin_replace_cat(message: Message, state: FSMContext) -> None:
    if not _is_admin(message.from_user.id):
        return
    if (message.text or "").strip() in {"⬅️ Ortga", "⬅️ Orqaga", "🏠 Asosiy sahifa", "🏠 Asosiy"}:
        await state.set_state(AdminFlow.menu)
        await message.answer("🛠 Admin panel:", reply_markup=admin_menu_kb())
        return
    cat_key = _cat_key_from_label((message.text or "").strip())
    if not cat_key:
        await message.answer("Kategoriya tugmasidan tanlang.", reply_markup=categories_kb(back=True))
        return
    async with SessionLocal() as session:
        rows = await list_tests_by_category(session, cat_key)
    if not rows:
        await message.answer("Bu kategoriyada test yo‘q.", reply_markup=admin_menu_kb())
        await state.set_state(AdminFlow.menu)
        return
    await state.update_data(category=cat_key)
    await state.set_state(AdminFlow.replace_choose_test)
    await message.answer("Testni tanlang:", reply_markup=tests_list_kb(rows, prefix="rpick", include_back=True))


@router.callback_query(AdminFlow.replace_choose_test, lambda c: (c.data or "").startswith("rpick:"))
async def admin_replace_pick(callback: CallbackQuery, state: FSMContext) -> None:
    if not callback.message:
        return
    await callback.answer()
    if callback.data == "rpick:back":
        await state.set_state(AdminFlow.menu)
        await callback.message.answer("🛠 Admin panel:", reply_markup=admin_menu_kb())
        return
    test_id = int(callback.data.split(":")[1])
    await state.update_data(test_id=test_id)
    await state.set_state(AdminFlow.replace_pdf)
    await callback.message.answer("Yangi PDF yuboring (yoki /skip deb yozing — PDF o‘zgarmaydi).")


@router.message(AdminFlow.replace_pdf)
async def admin_replace_pdf(message: Message, state: FSMContext) -> None:
    if not _is_admin(message.from_user.id):
        return
    if (message.text or "").strip().lower() == "/skip":
        await state.set_state(AdminFlow.replace_answers)
        await message.answer("Javoblarni yangilamoqchimisiz? (Agar yo‘q bo‘lsa /skip yozing)")
        return

    if not message.document or (message.document.mime_type or "") != "application/pdf":
        await message.answer("PDF yuboring yoki /skip.")
        return

    data = await state.get_data()
    test_id = int(data["test_id"])

    tmp_path = TESTS_DIR / f"tmp_replace_{message.document.file_id}.pdf"
    await message.bot.download(message.document, destination=tmp_path)

    async with SessionLocal() as session:
        final_pdf = TESTS_DIR / f"test_{test_id}.pdf"
        tmp_path.replace(final_pdf)
        await replace_test_pdf(session, test_id, str(final_pdf))

    await state.set_state(AdminFlow.replace_answers)
    await message.answer("✅ PDF yangilandi.\nEndi javoblarni yangilamoqchimisiz? (Agar yo‘q bo‘lsa /skip yozing)")


@router.message(AdminFlow.replace_answers)
async def admin_replace_answers(message: Message, state: FSMContext) -> None:
    if not _is_admin(message.from_user.id):
        return
    if (message.text or "").strip().lower() == "/skip":
        await state.set_state(AdminFlow.menu)
        await message.answer("✅ Yangilash yakunlandi.", reply_markup=admin_menu_kb())
        return

    # Javoblarni qayta kiritish: savol sonini testdan olamiz, keyin inline orqali
    data = await state.get_data()
    test_id = int(data["test_id"])
    async with SessionLocal() as session:
        t = await get_test(session, test_id)

    await state.update_data(num_questions=t.num_questions, answers={}, q=1)
    await state.set_state(AdminFlow.create_answers)  # reuse aa callbacks, but we need separate prefix
    # Hack: prefix har xil bo‘lishi uchun statega flag qo‘yamiz
    await state.update_data(_replace_mode=True)
    await message.answer(
        f"Javoblarni yangilash:\nSavol 1/{t.num_questions}:",
        reply_markup=answer_choice_kb("aa2", include_back=True, include_finish=False),
    )


@router.callback_query(lambda c: (c.data or "").startswith("aa2:"))
async def admin_replace_answer_cb(callback: CallbackQuery, state: FSMContext) -> None:
    if not callback.message:
        return
    await callback.answer()
    if not _is_admin(callback.from_user.id):
        return
    action = (callback.data or "").split(":", 1)[1]
    if action == "back":
        await state.set_state(AdminFlow.menu)
        await callback.message.answer("🛠 Admin panel:", reply_markup=admin_menu_kb())
        return

    data = await state.get_data()
    if "test_id" not in data:
        return
    q = int(data["q"])
    n = int(data["num_questions"])
    answers: Dict[int, str] = dict(data.get("answers", {}))
    ans = "" if action == "_" else action
    answers[q] = ans
    q_next = q + 1
    if q_next <= n:
        await state.update_data(q=q_next, answers=answers)
        await callback.message.answer(f"Savol {q_next}/{n}:", reply_markup=answer_choice_kb("aa2", include_back=True, include_finish=False))
    else:
        test_id = int(data["test_id"])
        async with SessionLocal() as session:
            await replace_test_answers(session, test_id, answers)
        await state.set_state(AdminFlow.menu)
        await callback.message.answer("✅ Javoblar yangilandi.", reply_markup=admin_menu_kb())


# ---------------- DELETE ----------------

@router.callback_query(lambda c: (c.data or "") == "admin:delete")
async def admin_delete_start(callback: CallbackQuery, state: FSMContext) -> None:
    if not callback.message:
        return
    await callback.answer()
    if not _is_admin(callback.from_user.id):
        return
    await state.set_state(AdminFlow.delete_choose_category)
    await callback.message.answer("Qaysi kategoriyadan o‘chirasiz?", reply_markup=categories_kb(back=True))


@router.message(AdminFlow.delete_choose_category)
async def admin_delete_cat(message: Message, state: FSMContext) -> None:
    if not _is_admin(message.from_user.id):
        return
    if (message.text or "").strip() in {"⬅️ Ortga", "⬅️ Orqaga", "🏠 Asosiy sahifa", "🏠 Asosiy"}:
        await state.set_state(AdminFlow.menu)
        await message.answer("🛠 Admin panel:", reply_markup=admin_menu_kb())
        return
    cat_key = _cat_key_from_label((message.text or "").strip())
    if not cat_key:
        await message.answer("Kategoriya tugmasidan tanlang.", reply_markup=categories_kb(back=True))
        return
    async with SessionLocal() as session:
        rows = await list_tests_by_category(session, cat_key)
    if not rows:
        await state.set_state(AdminFlow.menu)
        await message.answer("Bu kategoriyada test yo‘q.", reply_markup=admin_menu_kb())
        return
    await state.set_state(AdminFlow.delete_choose_test)
    await message.answer("O‘chiriladigan testni tanlang:", reply_markup=tests_list_kb(rows, prefix="dpick", include_back=True))


@router.callback_query(AdminFlow.delete_choose_test, lambda c: (c.data or "").startswith("dpick:"))
async def admin_delete_pick(callback: CallbackQuery, state: FSMContext) -> None:
    if not callback.message:
        return
    await callback.answer()
    if callback.data == "dpick:back":
        await state.set_state(AdminFlow.menu)
        await callback.message.answer("🛠 Admin panel:", reply_markup=admin_menu_kb())
        return
    test_id = int(callback.data.split(":")[1])
    async with SessionLocal() as session:
        t = await get_test(session, test_id)
    await state.update_data(test_id=test_id)
    await state.set_state(AdminFlow.delete_confirm)
    await callback.message.answer(f"❗️ Rostdan ham *{t.name}* testini o‘chirmoqchimisiz?", parse_mode="Markdown", reply_markup=confirm_kb("dconf", yes_label="🗑 O‘chirish", no_label="Bekor"))


@router.callback_query(AdminFlow.delete_confirm, lambda c: (c.data or "").startswith("dconf:"))
async def admin_delete_confirm(callback: CallbackQuery, state: FSMContext) -> None:
    if not callback.message:
        return
    await callback.answer()
    if not _is_admin(callback.from_user.id):
        return
    choice = callback.data.split(":")[1]
    if choice == "no":
        await state.set_state(AdminFlow.menu)
        await callback.message.answer("Bekor qilindi.", reply_markup=admin_menu_kb())
        return
    data = await state.get_data()
    test_id = int(data["test_id"])
    async with SessionLocal() as session:
        await delete_test(session, test_id)
    # pdf ni ham o‘chirishga urinib ko‘ramiz
    pdf = TESTS_DIR / f"test_{test_id}.pdf"
    if pdf.exists():
        try:
            pdf.unlink()
        except Exception:
            pass
    await state.set_state(AdminFlow.menu)
    await callback.message.answer("✅ Test o‘chirildi.", reply_markup=admin_menu_kb())


# ---------------- BASELINE (Rasch) ----------------

@router.callback_query(lambda c: (c.data or "") == "admin:baseline")
async def admin_baseline_start(callback: CallbackQuery, state: FSMContext) -> None:
    if not callback.message:
        return
    await callback.answer()
    if not _is_admin(callback.from_user.id):
        return
    await state.set_state(AdminFlow.baseline_choose_category)
    await callback.message.answer("Rasch bazasi qaysi kategoriya uchun? (SAT yoki Milliy)", reply_markup=categories_kb(back=True))


@router.message(AdminFlow.baseline_choose_category)
async def admin_baseline_cat(message: Message, state: FSMContext) -> None:
    if not _is_admin(message.from_user.id):
        return
    if (message.text or "").strip() in {"⬅️ Ortga", "⬅️ Orqaga", "🏠 Asosiy sahifa", "🏠 Asosiy"}:
        await state.set_state(AdminFlow.menu)
        await message.answer("🛠 Admin panel:", reply_markup=admin_menu_kb())
        return
    cat_key = _cat_key_from_label((message.text or "").strip())
    if cat_key not in {"sat", "milliy"}:
        await message.answer("Rasch faqat SAT yoki Milliy uchun. Iltimos, shu ikkisidan birini tanlang.")
        return
    async with SessionLocal() as session:
        rows = await list_tests_by_category(session, cat_key)
    if not rows:
        await state.set_state(AdminFlow.menu)
        await message.answer("Bu kategoriyada test yo‘q.", reply_markup=admin_menu_kb())
        return
    await state.set_state(AdminFlow.baseline_choose_test)
    await message.answer("Testni tanlang:", reply_markup=tests_list_kb(rows, prefix="bpick", include_back=True))


@router.callback_query(AdminFlow.baseline_choose_test, lambda c: (c.data or "").startswith("bpick:"))
async def admin_baseline_pick(callback: CallbackQuery, state: FSMContext) -> None:
    if not callback.message:
        return
    await callback.answer()
    if callback.data == "bpick:back":
        await state.set_state(AdminFlow.menu)
        await callback.message.answer("🛠 Admin panel:", reply_markup=admin_menu_kb())
        return
    test_id = int(callback.data.split(":")[1])

    async with SessionLocal() as session:
        t = await get_test(session, test_id)
        if not t.is_rasch:
            await callback.message.answer("Bu test Rasch emas.")
            return
        cnt = await count_baseline_submissions(session, test_id)
        if cnt >= 10:
            await callback.message.answer("✅ Bu test uchun baseline allaqachon 10 ta to‘ldirilgan.", reply_markup=admin_menu_kb())
            await state.set_state(AdminFlow.menu)
            return
        await ensure_baseline_users(session)

    await state.update_data(test_id=test_id, fake_user_index=1, answers={}, q=1)
    await state.set_state(AdminFlow.baseline_answers)
    await callback.message.answer(
        f"👤 Fake user 1/10\nSavol 1/{t.num_questions}:",
        reply_markup=answer_choice_kb("ba", include_back=True, include_finish=False),
    )


@router.callback_query(AdminFlow.baseline_answers, lambda c: (c.data or "").startswith("ba:"))
async def admin_baseline_answer_cb(callback: CallbackQuery, state: FSMContext) -> None:
    if not callback.message:
        return
    await callback.answer()
    if not _is_admin(callback.from_user.id):
        return
    action = (callback.data or "").split(":", 1)[1]
    if action == "back":
        await state.set_state(AdminFlow.menu)
        await callback.message.answer("🛠 Admin panel:", reply_markup=admin_menu_kb())
        return

    data = await state.get_data()
    test_id = int(data["test_id"])
    fake_i = int(data["fake_user_index"])
    q = int(data["q"])
    answers: Dict[int, str] = dict(data.get("answers", {}))

    async with SessionLocal() as session:
        t = await get_test(session, test_id)

    ans = "" if action == "_" else action
    answers[q] = ans

    q_next = q + 1
    if q_next <= t.num_questions:
        await state.update_data(q=q_next, answers=answers)
        await callback.message.answer(
            f"👤 Fake user {fake_i}/10\nSavol {q_next}/{t.num_questions}:",
            reply_markup=answer_choice_kb("ba", include_back=True, include_finish=False),
        )
        return

    # fake user yakunlandi -> DB ga submission yozamiz (tg_id=-fake_i)
    async with SessionLocal() as session:
        correct = await get_correct_answers(session, test_id)
        res_simple = simple_check(answers, correct, t.num_questions)
        await save_submission(
            session,
            tg_id=-fake_i,  # baseline user tg_id
            test_id=test_id,
            answers=answers,
            raw_correct=res_simple.raw_correct,
            total=res_simple.total,
            score=0.0,      # Rasch score keyin hisoblanadi (real user bilan birga)
            is_rasch=True,
        )

    if fake_i < 10:
        await state.update_data(fake_user_index=fake_i + 1, answers={}, q=1)
        await callback.message.answer(
            f"✅ Fake user {fake_i}/10 saqlandi.\n\n👤 Fake user {fake_i+1}/10\nSavol 1/{t.num_questions}:",
            reply_markup=answer_choice_kb("ba", include_back=True, include_finish=False),
        )
    else:
        await state.set_state(AdminFlow.menu)
        await callback.message.answer("✅ Baseline 10/10 to‘liq kiritildi.", reply_markup=admin_menu_kb())
