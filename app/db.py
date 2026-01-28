from sqlalchemy.ext.asyncio import create_async_engine, async_sessionmaker

from app.settings import settings

engine = create_async_engine(
    settings.database_url,
    echo=False,
    pool_size=5,
    max_overflow=5,
    pool_timeout=30,
)

SessionLocal = async_sessionmaker(
    engine,
    expire_on_commit=False,
)
