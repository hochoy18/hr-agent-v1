"""LangGraph 检查点器：AsyncPostgresSaver。

thread_id 使用 conversation_id，会话状态（含累积 artifacts）持久化到 PostgreSQL，
支持 interrupt 后跨请求 resume。
psycopg 连接池与业务侧 asyncpg 池相互独立，注意两者合计不要超过 PG max_connections。
"""
import logging
from typing import Optional

from langgraph.checkpoint.postgres.aio import AsyncPostgresSaver
from psycopg_pool import AsyncConnectionPool

from app.core.config import settings

logger = logging.getLogger(__name__)

_pool: Optional[AsyncConnectionPool] = None
_checkpointer: Optional[AsyncPostgresSaver] = None


async def init_checkpointer() -> AsyncPostgresSaver:
    """应用启动时初始化检查点器并执行 setup()（幂等建表）。"""
    global _pool, _checkpointer
    if _checkpointer is not None:
        return _checkpointer
    _pool = AsyncConnectionPool(
        conninfo=settings.DATABASE_URL,
        min_size=1,
        max_size=settings.DATABASE_POOL_SIZE,
        kwargs={"autocommit": True, "prepare_threshold": 0},
        open=False,
    )
    await _pool.open(wait=True, timeout=30)
    _checkpointer = AsyncPostgresSaver(_pool)
    await _checkpointer.setup()
    logger.info("LangGraph checkpointer 初始化成功（AsyncPostgresSaver）")
    return _checkpointer


async def close_checkpointer() -> None:
    """应用关闭时释放 psycopg 连接池。"""
    global _pool, _checkpointer
    _checkpointer = None
    if _pool is not None:
        await _pool.close()
        _pool = None
        logger.info("LangGraph checkpointer 已关闭")


def get_checkpointer() -> Optional[AsyncPostgresSaver]:
    return _checkpointer
