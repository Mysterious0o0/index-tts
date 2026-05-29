"""
上传完成后通知 A 服务器重建 Faiss 索引。
"""

import logging
import httpx
from config import SERVER_A_REBUILD_URL, SERVER_A_REBUILD_TOKEN

log = logging.getLogger("rebuild")


async def notify_rebuild(level: str = None):
    """
    通知 A 服务器重建 Faiss 索引。
    level: 指定 level 则只重建该 level，不填则重建全部。
    失败不抛出异常，不影响上传结果。
    """
    payload = {}
    if level:
        payload["level"] = level
    try:
        async with httpx.AsyncClient(timeout=10) as client:
            resp = await client.post(
                SERVER_A_REBUILD_URL,
                json=payload,
                headers={"Authorization": f"Bearer {SERVER_A_REBUILD_TOKEN}"},
            )
            resp.raise_for_status()
            log.info(f"[rebuild] 触发成功: {resp.json()}")
    except Exception as e:
        log.warning(f"[rebuild] 触发失败（不影响上传结果）: {e}")
