from __future__ import annotations

from aiogram.types import Message


async def show_menu_message(message: Message, text: str, reply_markup=None, **kwargs) -> None:
    # Keep UI stable (edit if possible, otherwise send)
    try:
        await message.answer(text, reply_markup=reply_markup, **kwargs)
    except Exception:
        await message.answer(text)
