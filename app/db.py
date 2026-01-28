from __future__ import annotations

from sqlalchemy.ext.asyncio import create_async_engine, async_sessionmaker
from sqlalchemy.engine.url import make_url

from app.settings import settings


def _sanitize_asyncpg_url(raw: str):
    url = make_url(raw)
    q = dict(url.query)

    # asyncpg these libpq-style paramsni keyword sifatida qabul qilmaydi
    q.pop("sslmode", None)
    q.pop("channel_binding", None)

    # ba'zi linklarda bo'lishi mumkin (kerak bo'lmasa ham, xavfsiz tozalaymiz)
    q.pop("sslrootcert", None)
    q.pop("sslcert", None)
    q.pop("sslkey", None)
    q.pop("sslcrl", None)

    return url.set(query=q)


url = _sanitize_asyncpg_url(settings.database_url)

engine = create_async_engine(
    url,
    echo=False,
    pool_size=5,
    max_overflow=5,
    pool_timeout=30,
    pool_pre_ping=True,
    connect_args={"ssl": "require"},
)

SessionLocal = async_sessionmaker(
    engine,
    expire_on_commit=False,
)
