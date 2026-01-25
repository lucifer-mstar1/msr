from __future__ import annotations

import asyncio
import logging

from aiogram import Bot, Dispatcher

from app.settings import settings
from app.db import engine
from app.models import Base
from app.handlers import common, admin, tests
from app.handlers import ceo
from app.miniapp_server import start_miniapp


async def init_db() -> None:
    # Safety: ensure tables exist even if alembic not run.
    async with engine.begin() as conn:
        await conn.run_sync(Base.metadata.create_all)


async def main() -> None:
    logging.basicConfig(level=logging.INFO)

    await init_db()

    if not settings.bot_token:
        raise RuntimeError("BOT_TOKEN is empty. Put it into .env")

    bot = Bot(token=settings.bot_token)
    dp = Dispatcher()
    # Order matters: more specific routers first, common fallbacks last
    dp.include_router(ceo.router)
    dp.include_router(admin.router)
    dp.include_router(tests.router)
    dp.include_router(common.router)

    # Start miniapp server (aiohttp) in the same process
    runner = await start_miniapp()
    try:
        await dp.start_polling(bot)
    finally:
        try:
            await runner.cleanup()
        except Exception:
            pass


if __name__ == "__main__":
    asyncio.run(main())
