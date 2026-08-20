# ============================================================
# CAET 数据库层 — 异步 SQLAlchemy (asyncpg)
# 所有 DB 操作都在函数内部执行，模块导入阶段不会连接数据库。
# ============================================================
from collections.abc import AsyncGenerator

from sqlalchemy import JSON
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker, create_async_engine
from sqlalchemy.orm import DeclarativeBase

from .config import settings

# 使用 SQLAlchemy.JSON 以兼容 PostgreSQL JSONB
JsonType = JSON

engine = create_async_engine(settings.DATABASE_URL, echo=False, future=True)
SessionLocal = async_sessionmaker(engine, class_=AsyncSession, expire_on_commit=False)


class Base(DeclarativeBase):
    pass


async def get_db() -> AsyncGenerator[AsyncSession, None]:
    async with SessionLocal() as session:
        yield session


def row_to_dict(row) -> dict:
    """将 ORM 行对象转换为可 JSON 序列化的字典。"""
    if row is None:
        return None
    out = {}
    for col in row.__table__.columns:
        val = getattr(row, col.name)
        out[col.name] = val
    return out
