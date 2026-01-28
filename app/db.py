from __future__ import annotations

from sqlalchemy.ext.asyncio import create_async_engine, async_sessionmaker
from sqlalchemy.engine.url import make_url

from app.settings import settings


def _build_engine():
    url = make_url(settings.database_url)

    # asyncpg DOES NOT accept sslmode=... as a kwarg, so remove it from URL query
    q = dict(url.query)
    q.pop("sslmode", None)
    url = url.set(query=q)

    # Tell asyncpg to require TLS
    engine = create_async_engine(
        url,
        echo=False,
        pool_size=5,
        max_overflow=5,
        pool_timeout=30,
        pool_pre_ping=True,
        connect_args={"ssl": "require"},
    )
    return engine


engine = _build_engine()

SessionLocal = async_sessionmaker(
    engine,
    expire_on_commit=False,
)
