"""
从 A 服务器拉取日志文件，解析后写入 ClickHouse。
"""

import uuid
import httpx
import logging
import posixpath
from datetime import datetime
from fastapi import APIRouter, HTTPException
from pydantic import BaseModel
from core.database import insert_records
from config import LOG_FETCH_URL

log = logging.getLogger("logs")
router = APIRouter(prefix="/logs", tags=["logs"])


class FetchLogsRequest(BaseModel):
    date: str | None = None  # 指定日期 YYYY-MM-DD，不填默认今天


@router.post("/fetch")
async def fetch_logs(req: FetchLogsRequest):
    """
    拉取 A 服务器当天（或指定日期）的日志文件。
    文件名格式：merged_depthVoice_YYYY-MM-DD.txt
    每行格式：text||level，level 只允许 1 / 2 / 3，其余跳过。
    """
    date_str = req.date or datetime.now().strftime("%Y-%m-%d")
    file_name = f"merged_depthVoice_{date_str}.txt"
    full_url = posixpath.join(LOG_FETCH_URL, "depthVoice", file_name)

    try:
        async with httpx.AsyncClient(timeout=30) as client:
            resp = await client.get(full_url)
            resp.raise_for_status()
            raw_lines = [
                line.strip() for line in resp.text.splitlines() if line.strip()
            ]
    except Exception as e:
        raise HTTPException(status_code=502, detail=f"拉取日志失败: {e}")

    if not raw_lines:
        return {"inserted": 0, "skipped": 0, "message": "日志为空"}

    batch_id = date_str + str(uuid.uuid4())
    records = []
    skipped = 0

    for line in raw_lines:
        parts = line.split("||")
        if len(parts) != 2:
            log.warning(f"[logs] 格式错误，跳过: {line!r}")
            skipped += 1
            continue

        text = parts[0].strip()
        level = parts[1].strip()

        if level not in ("1", "2", "3"):
            log.warning(f"[logs] 未知 level={level!r}，跳过: {line!r}")
            skipped += 1
            continue

        if not text:
            skipped += 1
            continue

        records.append({"level": level, "text": text, "batch_id": batch_id})

    if not records:
        return {"inserted": 0, "skipped": skipped, "message": "解析后无有效记录"}

    await insert_records(records)
    log.info(f"[logs] 写入 {len(records)} 条，跳过 {skipped} 条，batch_id={batch_id}")

    return {
        "batch_id": batch_id,
        "inserted": len(records),
        "skipped": skipped,
        "date": date_str,
    }
