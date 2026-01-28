from __future__ import annotations

import asyncio
import logging

from aiogram import Bot, Dispatcher

from app.settings import settings
from app.db import engine
from app.models import Base
from app.handlers import common, admin, tests, ceo
from app.miniapp_server import start_miniapp


async def init_db() -> None:
    async with engine.begin() as conn:
        await conn.run_sync(Base.metadata.create_all)


async def main() -> None:
    logging.basicConfig(level=logging.INFO)

    # DB ishlamasa ham app yi yiqitib yubormaymiz
    try:
        await init_db()
    except Exception:
        logging.exception("DB init failed, continuing without DB")

    bot = Bot(token=settings.bot_token)
    dp = Dispatcher()

    dp.include_router(ceo.router)
    dp.include_router(admin.router)
    dp.include_router(tests.router)
    dp.include_router(common.router)

    runner = await start_miniapp()
    try:
        await dp.start_polling(bot)
    finally:
        await runner.cleanup()


if __name__ == "__main__":
    asyncio.run(main())
