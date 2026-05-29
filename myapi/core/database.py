"""
数据库模块，基于项目现有 AsyncCHClient。
将你的 AsyncCHClient 实现放到 core/ch_client.py，
或修改下方 import 路径指向你公共库的实际位置。
"""

import uuid
import logging
from datetime import datetime

from config import (
    CLICKHOUSE_HOST,
    CLICKHOUSE_PORT,
    CLICKHOUSE_USER,
    CLICKHOUSE_PASSWORD,
    CLICKHOUSE_DB,
)
from core.ch_client import AsyncCHClient  # ← 替换为你项目实际导入路径

log = logging.getLogger("database")

# ──────────────────────────────────────────
# 全局连接池单例
# ──────────────────────────────────────────
_client: AsyncCHClient | None = None


def get_client() -> AsyncCHClient:
    global _client
    if _client is None:
        _client = AsyncCHClient(
            host=CLICKHOUSE_HOST,
            port=CLICKHOUSE_PORT,
            user=CLICKHOUSE_USER,
            password=CLICKHOUSE_PASSWORD,
            database=CLICKHOUSE_DB,
        )
    return _client


async def init_db():
    await get_client().init_pool()
    log.info("[db] ClickHouse 连接池初始化完成")


async def close_db():
    await get_client().close()
    log.info("[db] ClickHouse 连接池已关闭")


# ──────────────────────────────────────────
# 表结构常量
# status 取值：pending_review / approved / deleted /
#              uploading / uploaded / upload_failed
# level  取值：1 / 2 / 3（不存 default，default 由查全量代替）
# ──────────────────────────────────────────
TABLE = "audio_records"
COLS = [
    "id",
    "level",
    "text",
    "path",
    "master_path",
    "status",
    "batch_id",
    "reviewer",
    "reviewed_at",
    "uploaded_at",
    "created_at",
]
COL_STR = ", ".join(COLS)


def _row2dict(row: tuple) -> dict:
    return dict(zip(COLS, row))


# ──────────────────────────────────────────
# 写操作
# ──────────────────────────────────────────


async def insert_records(records: list[dict]):
    """
    批量写入，直接进入 pending_review 状态。
    records: [{ level, text, batch_id }, ...]
    """
    now = datetime.now()
    rows = [
        (
            str(uuid.uuid4()),
            r["level"],
            r["text"],
            "",
            "",
            "pending_review",
            r["batch_id"],
            "",
            None,
            None,
            now,
        )
        for r in records
    ]
    await get_client().insert_batch(TABLE, COLS, rows)
    log.info(f"[db] insert_records: {len(rows)} 条")


async def update_record(record_id: str, **kwargs):
    """
    状态变更：先查出当前行，合并字段后插入新行。
    ReplacingMergeTree 按 created_at 保留最新版本，查询时加 FINAL。
    """
    row = await get_record_by_id(record_id)
    if not row:
        raise ValueError(f"[db] 记录不存在: {record_id}")
    row.update(kwargs)
    row["created_at"] = datetime.now()
    await get_client().insert_batch(
        TABLE,
        COLS,
        [
            (
                row["id"],
                row["level"],
                row["text"],
                row["path"],
                row["master_path"],
                row["status"],
                row["batch_id"],
                row["reviewer"],
                row.get("reviewed_at"),
                row.get("uploaded_at"),
                row["created_at"],
            )
        ],
    )


# ──────────────────────────────────────────
# 读操作
# ──────────────────────────────────────────


async def get_records(
    status: str = None,
    level: str = None,
    batch_id: str = None,
    page: int = 1,
    page_size: int = 20,
) -> tuple[list[dict], int]:
    conditions = ["1=1"]
    params = {}  # 1. 容器改成字典形式

    # 2. 占位符全部改成 %(变量名)s 的形式
    if status:
        conditions.append("status = %(status)s")
        params["status"] = status
    if level:
        conditions.append("level = %(level)s")
        params["level"] = level
    if batch_id:
        conditions.append("batch_id = %(batch_id)s")
        params["batch_id"] = batch_id

    where = " AND ".join(conditions)
    offset = (page - 1) * page_size

    # 3. 查总数：传入过滤条件字典
    total_row = await get_client().fetch_one(
        f"SELECT count() FROM {TABLE} FINAL WHERE {where}",
        params if params else None,
    )
    total = int(total_row[0]) if total_row else 0

    # 4. 查列表：复制一份条件字典，把分页的参数塞进去
    query_params = params.copy()
    query_params["limit"] = page_size
    query_params["offset"] = offset

    # 5. SQL 中的 LIMIT 和 OFFSET 同样使用命名占位符
    rows = await get_client().fetch_all(
        f"SELECT {COL_STR} FROM {TABLE} FINAL "
        f"WHERE {where} ORDER BY created_at DESC "
        f"LIMIT %(limit)s OFFSET %(offset)s",
        query_params,
    )
    return [_row2dict(r) for r in rows], total


async def get_record_by_id(record_id: str) -> dict | None:
    row = await get_client().fetch_one(
        f"SELECT {COL_STR} FROM {TABLE} FINAL WHERE id = %(record_id)s",
        {"record_id": record_id},
    )
    return _row2dict(row) if row else None


async def get_approved_records() -> list[dict]:
    rows = await get_client().fetch_all(
        f"SELECT {COL_STR} FROM {TABLE} FINAL WHERE status = 'approved'"
    )
    return [_row2dict(r) for r in rows]


async def get_failed_records() -> list[dict]:
    rows = await get_client().fetch_all(
        f"SELECT {COL_STR} FROM {TABLE} FINAL WHERE status = 'upload_failed'"
    )
    return [_row2dict(r) for r in rows]


async def get_batches() -> list[dict]:
    rows = await get_client().fetch_all(
        f"SELECT batch_id, count() as cnt, min(created_at) as created_at "
        f"FROM {TABLE} FINAL "
        f"GROUP BY batch_id ORDER BY created_at DESC"
    )
    return [{"batch_id": r[0], "count": r[1], "created_at": str(r[2])} for r in rows]
