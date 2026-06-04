from sqlalchemy.ext.asyncio import create_async_engine, AsyncSession, async_sessionmaker
from sqlalchemy.orm import DeclarativeBase
from .config import settings
import re


def get_async_db_url(url: str) -> str:
    """Конвертирует postgres:// в postgresql+asyncpg:// и убирает sslmode."""
    if url.startswith("postgresql://"):
        url = url.replace("postgresql://", "postgresql+asyncpg://", 1)
    elif url.startswith("postgres://"):
        url = url.replace("postgres://", "postgresql+asyncpg://", 1)
    url = re.sub(r"[?&]sslmode=[^&]*", "", url)
    url = re.sub(r"[?&]$", "", url)
    return url


def get_connect_args(url: str) -> dict:
    """Возвращает connect_args с SSL если оригинальный URL требовал sslmode."""
    if "sslmode=require" in url or "sslmode=verify" in url:
        return {"ssl": True}
    return {}


_raw_url = settings.database_url
_db_url = get_async_db_url(_raw_url)
_connect_args = get_connect_args(_raw_url)

engine = create_async_engine(
    _db_url,
    echo=False,
    pool_size=10,
    max_overflow=20,
    connect_args=_connect_args,
)

AsyncSessionFactory = async_sessionmaker(
    engine, class_=AsyncSession, expire_on_commit=False
)


class Base(DeclarativeBase):
    pass


async def get_session() -> AsyncSession:
    async with AsyncSessionFactory() as session:
        yield session
