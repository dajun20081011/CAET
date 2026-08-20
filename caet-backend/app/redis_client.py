# ============================================================
# CAET Redis 轻量接入
# 用途（按确认路线）：
#   1) 用户会话（JWT 的 jti -> 会话载荷，支持登出/吊销）
#   2) 简单缓存（任务列表、热点数据，TTL 受控）
#   3) AI 任务扩展预留（后续讯飞/通义异步任务队列占位）
# 设计原则：Redis 不可用时优雅降级——所有写/读静默 no-op，
#           核心链路（JWT 自包含）不因此中断。
# ============================================================
from __future__ import annotations

import json
import logging
import os
from typing import Any, Optional

import redis.asyncio as aioredis

logger = logging.getLogger("caet.redis")

REDIS_URL = os.getenv("REDIS_URL", "redis://caet-redis:6379/0")
CACHE_TTL = int(os.getenv("CACHE_TTL_SECONDS", "300"))

_pool: Optional[aioredis.ConnectionPool] = None
_available: Optional[bool] = None


def _get_pool() -> Optional[aioredis.ConnectionPool]:
    """惰性创建连接池；失败返回 None（降级）。"""
    global _pool, _available
    if _pool is not None:
        return _pool
    if _available is False:
        return None
    try:
        _pool = aioredis.ConnectionPool.from_url(
            REDIS_URL, decode_responses=True, max_connections=20
        )
        _available = True
        logger.info("Redis 连接池已建立: %s", REDIS_URL)
    except Exception as e:  # noqa: BLE001
        _available = False
        logger.warning("Redis 不可用，降级为无缓存模式: %s", e)
    return _pool


async def ping() -> bool:
    """健康检查：Redis 可达返回 True，否则 False（不抛异常）。"""
    pool = _get_pool()
    if pool is None:
        return False
    try:
        async with aioredis.Redis(connection_pool=pool) as r:
            return bool(await r.ping())
    except Exception:  # noqa: BLE001
        return False


# ---------------- 通用缓存 ----------------
async def cache_set(key: str, value: Any, ttl: int = CACHE_TTL) -> None:
    pool = _get_pool()
    if pool is None:
        return
    try:
        async with aioredis.Redis(connection_pool=pool) as r:
            await r.set(key, json.dumps(value, ensure_ascii=False), ex=ttl)
    except Exception:  # noqa: BLE001
        pass


async def cache_get(key: str) -> Optional[Any]:
    pool = _get_pool()
    if pool is None:
        return None
    try:
        async with aioredis.Redis(connection_pool=pool) as r:
            raw = await r.get(key)
            return json.loads(raw) if raw is not None else None
    except Exception:  # noqa: BLE001
        return None


async def cache_delete(key: str) -> None:
    pool = _get_pool()
    if pool is None:
        return
    try:
        async with aioredis.Redis(connection_pool=pool) as r:
            await r.delete(key)
    except Exception:  # noqa: BLE001
        pass


def cache_key(*parts: str) -> str:
    return "caet:" + ":".join(parts)


# ---------------- 用户会话（JWT jti） ----------------
async def session_set(jti: str, payload: dict, ttl: int = CACHE_TTL * 288) -> None:
    """将 JWT 会话载荷存入 Redis，支持登出吊销。ttl 默认约 24h。"""
    await cache_set(f"session:{jti}", payload, ttl)


async def session_get(jti: str) -> Optional[dict]:
    return await cache_get(f"session:{jti}")


async def session_delete(jti: str) -> None:
    await cache_delete(f"session:{jti}")


# ---------------- AI 任务扩展预留 ----------------
async def ai_task_push(queue: str, task: dict) -> None:
    """预留：将 AI 异步任务推入 Redis 列表，供后续 worker 消费。"""
    pool = _get_pool()
    if pool is None:
        return
    try:
        async with aioredis.Redis(connection_pool=pool) as r:
            await r.rpush(f"aiq:{queue}", json.dumps(task, ensure_ascii=False))
    except Exception:  # noqa: BLE001
        pass
