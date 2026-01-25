from __future__ import annotations

from aiogram.types import (
    InlineKeyboardButton,
    InlineKeyboardMarkup,
    KeyboardButton,
    ReplyKeyboardMarkup,
    WebAppInfo,
)
from aiogram.utils.keyboard import InlineKeyboardBuilder, ReplyKeyboardBuilder

from app.settings import settings


# 5 ta kategoriya (talab bo'yicha)
CATEGORIES = [
    ("milliy", "🇺🇿 Milliy Sertifikat tayyorlov"),
    ("sat", "🧮 SAT tayyorlov"),
    ("dtm", "📚 DTM tayyorlov"),
    ("prezident", "🏫 Prezident maktabiga tayyorlov"),
    ("mavzu", "🧩 Mavzulashtirilgan testlar"),
]


def user_menu_kb() -> ReplyKeyboardMarkup:
    """User panel: 3 tugma (talab bo'yicha)."""
    kb = ReplyKeyboardBuilder()
    kb.add(KeyboardButton(text="Test ishlash"))
    kb.add(KeyboardButton(text="Test Tekshirish"))
    kb.add(KeyboardButton(text="Clear"))
    kb.adjust(2, 1)
    return kb.as_markup(resize_keyboard=True)


def admin_menu_reply_kb() -> ReplyKeyboardMarkup:
    """Admin panel: 3 tugma (talab bo'yicha)."""
    kb = ReplyKeyboardBuilder()
    kb.add(KeyboardButton(text="Test yaratish"))
    kb.add(KeyboardButton(text="Test edit"))
    kb.add(KeyboardButton(text="⬅️ Orqaga"))
    kb.add(KeyboardButton(text="🏠 Asosiy sahifa"))
    kb.add(KeyboardButton(text="Clear"))
    kb.adjust(2, 2, 1)
    return kb.as_markup(resize_keyboard=True)


def request_contact_kb() -> ReplyKeyboardMarkup:
    kb = ReplyKeyboardBuilder()
    kb.add(KeyboardButton(text="📞 Telefon raqamni ulashish", request_contact=True))
    kb.add(KeyboardButton(text="Clear"))
    kb.adjust(1)
    return kb.as_markup(resize_keyboard=True)


def webapp_open_kb(url: str, label: str = "🔗 Mini App") -> InlineKeyboardMarkup:
    b = InlineKeyboardBuilder()
    b.add(InlineKeyboardButton(text=label, web_app=WebAppInfo(url=url)))
    b.adjust(1)
    return b.as_markup()


def main_menu_kb(roles: set[str] | None = None) -> ReplyKeyboardMarkup:
    """Main menu that can show multiple role panels.

    - Always shows user actions.
    - If roles include admin and/or ceo, shows buttons to open those panels.
    """
    roles = roles or {"user"}
    kb = ReplyKeyboardBuilder()

    # User actions
    kb.add(KeyboardButton(text="Test ishlash"))
    kb.add(KeyboardButton(text="Test Tekshirish"))

    # Role panels
    if "admin" in roles:
        kb.add(KeyboardButton(text="🛠 Admin panel"))
    if "ceo" in roles:
        kb.add(KeyboardButton(text="👑 CEO panel"))

    kb.add(KeyboardButton(text="Clear"))
    # Layout: keep compact
    kb.adjust(2, 2, 1)
    return kb.as_markup(resize_keyboard=True)


def ceo_menu_kb() -> ReplyKeyboardMarkup:
    """CEO menyusi: faqat userlar ro'yxati PDF.

    CEO test yaratmaydi ham, test ishlamaydi ham.
    """
    kb = ReplyKeyboardBuilder()
    kb.add(KeyboardButton(text="Userlar ro'yxatini olish (pdf)"))
    kb.add(KeyboardButton(text="⬅️ Orqaga"))
    kb.add(KeyboardButton(text="🏠 Asosiy sahifa"))
    kb.add(KeyboardButton(text="Clear"))
    kb.adjust(2, 2)
    return kb.as_markup(resize_keyboard=True)


def categories_kb(back: bool = True) -> ReplyKeyboardMarkup:
    kb = ReplyKeyboardBuilder()
    for _, label in CATEGORIES:
        kb.add(KeyboardButton(text=label))
    if back:
        kb.add(KeyboardButton(text="⬅️ Orqaga"))
        kb.add(KeyboardButton(text="🏠 Asosiy sahifa"))
    kb.adjust(1)
    return kb.as_markup(resize_keyboard=True)


def back_reply_kb() -> ReplyKeyboardMarkup:
    kb = ReplyKeyboardBuilder()
    kb.add(KeyboardButton(text="⬅️ Orqaga"))
    kb.add(KeyboardButton(text="🏠 Asosiy sahifa"))
    return kb.as_markup(resize_keyboard=True)


def join_gate_kb(channel_url: str, group_url: str) -> InlineKeyboardMarkup:
    b = InlineKeyboardBuilder()
    if channel_url:
        b.add(InlineKeyboardButton(text="➡️ Kanalga qo'shilish", url=channel_url))
    if group_url:
        b.add(InlineKeyboardButton(text="➡️ Guruhga qo'shilish", url=group_url))
    b.add(InlineKeyboardButton(text="✅ Tekshirib ko'rish", callback_data="gate_check"))
    b.adjust(1)
    return b.as_markup()


def tests_list_kb(test_rows: list[tuple[int, str]], prefix: str, include_back: bool = True) -> InlineKeyboardMarkup:
    b = InlineKeyboardBuilder()
    for tid, name in test_rows:
        b.add(InlineKeyboardButton(text=name, callback_data=f"{prefix}:{tid}"))
    if include_back:
        b.add(InlineKeyboardButton(text="⬅️ Orqaga", callback_data=f"{prefix}:back"))
        b.add(InlineKeyboardButton(text="🏠 Asosiy sahifa", callback_data="nav:home"))
    b.adjust(1)
    return b.as_markup()


def confirm_kb(prefix: str, yes_label: str = "✅ Ha", no_label: str = "❌ Yo'q") -> InlineKeyboardMarkup:
    b = InlineKeyboardBuilder()
    b.add(InlineKeyboardButton(text=yes_label, callback_data=f"{prefix}:yes"))
    b.add(InlineKeyboardButton(text=no_label, callback_data=f"{prefix}:no"))
    b.adjust(2)
    return b.as_markup()


def answer_choice_kb(prefix: str, *, include_back: bool = True, include_finish: bool = False) -> InlineKeyboardMarkup:
    """Javob tanlash uchun inline tugmalar.

    prefix: callback_data prefiksi (masalan: "ua" yoki "aa")
    """
    b = InlineKeyboardBuilder()
    for a in ["A", "B", "C", "D", "E"]:
        b.add(InlineKeyboardButton(text=a, callback_data=f"{prefix}:{a}"))
    b.add(InlineKeyboardButton(text="—", callback_data=f"{prefix}:_"))  # bo'sh
    if include_finish:
        b.add(InlineKeyboardButton(text="✅ Tekshirish", callback_data=f"{prefix}:finish"))
    if include_back:
        b.add(InlineKeyboardButton(text="⬅️ Ortga", callback_data=f"{prefix}:back"))
    b.adjust(5, 1, 1, 1)
    return b.as_markup()


def after_result_kb(prefix: str, test_id: int) -> InlineKeyboardMarkup:
    b = InlineKeyboardBuilder()
    b.add(InlineKeyboardButton(text="📄 Sertifikatni olish", callback_data=f"{prefix}:cert:{test_id}"))
    b.add(InlineKeyboardButton(text="⬅️ Ortga", callback_data="nav:back"))
    b.adjust(1)
    return b.as_markup()


def admin_menu_kb() -> InlineKeyboardMarkup:
    b = InlineKeyboardBuilder()
    b.add(InlineKeyboardButton(text="➕ Yangi test yaratish", callback_data="admin:create"))
    b.add(InlineKeyboardButton(text="♻️ Testni yangilash (PDF/Javob)", callback_data="admin:replace"))
    b.add(InlineKeyboardButton(text="🗑 Testni o'chirish", callback_data="admin:delete"))
    b.add(InlineKeyboardButton(text="📊 Rasch bazasi (10 ta)", callback_data="admin:baseline"))
    b.add(InlineKeyboardButton(text="⬅️ Ortga", callback_data="nav:back"))
    b.adjust(1)
    return b.as_markup()


def finish_kb(prefix: str) -> InlineKeyboardMarkup:
    b = InlineKeyboardBuilder()
    b.add(InlineKeyboardButton(text="✅ Tekshirish", callback_data=f"{prefix}:finish"))
    b.add(InlineKeyboardButton(text="⬅️ Ortga", callback_data=f"{prefix}:back"))
    b.adjust(1)
    return b.as_markup()
