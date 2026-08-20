# ============================================================
# CAET 启动自举脚本（幂等）
# 由 Docker 容器 CMD 在 uvicorn 之前执行：
#   1) 启用 uuid-ossp 扩展
#   2) 执行 database/schema.sql（全部 IF NOT EXISTS / CREATE OR REPLACE）
#   3) 执行 database/seed.sql（含去重保护）
#   4) 若配置了 INIT_ADMIN_*，创建/复用管理员
# 确保 `docker compose up -d` 后平台即可用（可部署、可运行）。
# ============================================================
from __future__ import annotations

import asyncio
import logging
import os
from pathlib import Path

import asyncpg

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger("caet.db_init")

DB_URL = os.getenv("DATABASE_URL", "")
if not DB_URL:
    raise RuntimeError("DATABASE_URL must be provided through the deployment environment")
# asyncpg 原始驱动不接受 +asyncpg 方言后缀
RAW_URL = DB_URL.replace("postgresql+asyncpg://", "postgresql://")

INIT_ADMIN_EMAIL = os.getenv("INIT_ADMIN_EMAIL", "")
INIT_ADMIN_PASSWORD = os.getenv("INIT_ADMIN_PASSWORD", "")
INIT_ADMIN_NAME = os.getenv("INIT_ADMIN_NAME", "管理员")

BASE_DIR = Path(__file__).resolve().parent.parent
SCHEMA_SQL = (BASE_DIR / "database" / "schema.sql").read_text(encoding="utf-8")
SEED_SQL = (BASE_DIR / "database" / "seed.sql").read_text(encoding="utf-8")


def _strip_comments(sql: str) -> str:
    out = []
    for line in sql.splitlines():
        s = line.strip()
        if s.startswith("--"):
            continue
        out.append(line)
    return "\n".join(out)


async def init() -> None:
    logger.info("连接数据库: %s", RAW_URL.split("@")[-1])
    conn = await asyncpg.connect(RAW_URL)
    try:
        await conn.execute('CREATE EXTENSION IF NOT EXISTS "uuid-ossp";')
        logger.info("执行 schema.sql ...")
        await conn.execute(_strip_comments(SCHEMA_SQL))
        logger.info("执行 seed.sql ...")
        await conn.execute(_strip_comments(SEED_SQL))

        if INIT_ADMIN_EMAIL and INIT_ADMIN_PASSWORD:
            # 延迟导入避免循环依赖与早期 DB 连接
            from app.security import hash_password

            exists = await conn.fetchval(
                "SELECT 1 FROM profiles WHERE email=$1", INIT_ADMIN_EMAIL
            )
            if not exists:
                await conn.execute(
                    "INSERT INTO profiles (email, password_hash, display_name, role) "
                    "VALUES ($1,$2,$3,'admin')",
                    INIT_ADMIN_EMAIL,
                    hash_password(INIT_ADMIN_PASSWORD),
                    INIT_ADMIN_NAME,
                )
                logger.info("已创建管理员: %s", INIT_ADMIN_EMAIL)
            else:
                logger.info("管理员已存在，跳过: %s", INIT_ADMIN_EMAIL)

        logger.info("db_init 完成 ✅")
    finally:
        await conn.close()


if __name__ == "__main__":
    asyncio.run(init())
