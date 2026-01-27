from __future__ import annotations

from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker, create_async_engine
from app.settings import settings


def _to_async_driver(url: str) -> str:
    u = (url or "").strip()
    if u.startswith("postgresql://"):
        return u.replace("postgresql://", "postgresql+asyncpg://", 1)
    if u.startswith("postgres://"):
        return u.replace("postgres://", "postgresql+asyncpg://", 1)
    return u


url = settings.sql_url
if not url:
    raise RuntimeError("No DB url. Set DATABASE_URL or SQLITE_PATH.")

engine = create_async_engine(
    _to_async_driver(url),
    echo=False,
    pool_pre_ping=True,
    future=True,
)

SessionLocal: async_sessionmaker[AsyncSession] = async_sessionmaker(
    bind=engine,
    expire_on_commit=False,
)
