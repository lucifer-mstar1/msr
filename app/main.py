from __future__ import annotations

import asyncio
import logging
import os

from aiohttp import web
from aiogram import Bot, Dispatcher

from app.settings import settings
from app.db import engine
from app.models import Base
from app.handlers import common, admin, tests, ceo
from app.miniapp_server import start_miniapp


async def start_web_server():
    app = web.Application()

    async def health(request):
        return web.json_response({"ok": True})

    app.router.add_get("/", health)
    app.router.add_get("/health", health)

    port = int(os.environ.get("PORT", "8000"))
    runner = web.AppRunner(app)
    await runner.setup()
    site = web.TCPSite(runner, "0.0.0.0", port)
    await site.start()
    logging.info(f"WEB server running on 0.0.0.0:{port}")

    return runner


async def init_db() -> None:
    async with engine.begin() as conn:
        await conn.run_sync(Base.metadata.create_all)


async def main() -> None:
    logging.basicConfig(level=logging.INFO)

    # 1) Render port ochilsin
    web_runner = await start_web_server()

    # 2) DB init (yiqilsa ham app ishlayversin)
    try:
        await init_db()
    except Exception:
        logging.exception("DB init failed, continuing without DB")

    # 3) Bot
    if not settings.bot_token:
        raise RuntimeError("BOT_TOKEN is empty. Put it into .env")

    bot = Bot(token=settings.bot_token)
    dp = Dispatcher()

    dp.include_router(ceo.router)
    dp.include_router(admin.router)
    dp.include_router(tests.router)
    dp.include_router(common.router)

    # 4) Miniapp server
    miniapp_runner = await start_miniapp()

    try:
        await dp.start_polling(bot)
    finally:
        try:
            await miniapp_runner.cleanup()
        except Exception:
            pass
        try:
            await web_runner.cleanup()
        except Exception:
            pass


if __name__ == "__main__":
    asyncio.run(main())
