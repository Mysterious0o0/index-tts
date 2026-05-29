"""
音频生成路由：触发批量 TTS，异步执行并追踪进度。
"""

import asyncio
import logging
from fastapi import APIRouter, HTTPException, BackgroundTasks
from pydantic import BaseModel
from core.database import get_records, update_record
from services.tts_service import batch_generate_audio
from services.task_manager import (
    create_task,
    update_task,
    update_progress,
    finish_task,
    get_task,
)

log = logging.getLogger("tts_router")
router = APIRouter(prefix="/tts", tags=["tts"])


class GenerateRequest(BaseModel):
    # 指定批次，不填则处理全部 pending_review 且 path 为空的记录
    batch_id: str | None = None
    # 可选，只处理某个 level
    level: str | None = None


@router.post("/generate")
async def trigger_generate(req: GenerateRequest, background_tasks: BackgroundTasks):
    """触发音频生成，异步执行"""
    filters = {"status": "pending_review"}
    if req.batch_id:
        filters["batch_id"] = req.batch_id
    if req.level:
        filters["level"] = req.level

    records, total = await get_records(**filters, page_size=10000)
    # 只处理还没有生成音频的（path 为空）
    records = [r for r in records if not r.get("path")]
    total = len(records)

    if not total:
        return {"message": "没有待生成的记录"}

    task_id = create_task("tts_generate")
    update_task(task_id, status="running", total=total)
    background_tasks.add_task(_run_generate, task_id, records)

    return {"task_id": task_id, "total": total}


async def _run_generate(task_id: str, records: list[dict]):
    done = 0
    failed_ids = []

    def progress_cb(d, t):
        nonlocal done
        done = d
        update_progress(task_id, done, t, failed_ids)

    try:
        results = await asyncio.to_thread(batch_generate_audio, records, progress_cb)
        for r in results:
            if r["success"]:
                await update_record(r["id"], path=r["local_path"])
            else:
                failed_ids.append(r["id"])
                # 生成失败保留 pending_review 状态，path 仍为空，可重新触发

        update_progress(task_id, len(results), len(results), failed_ids)
        finish_task(task_id, success=True)
        log.info(
            f"[tts] 生成完成，成功={len(results) - len(failed_ids)}，失败={len(failed_ids)}"
        )
    except Exception as e:
        log.error(f"[tts] 生成任务异常: {e}")
        finish_task(task_id, success=False, error=str(e))


@router.get("/progress/{task_id}")
async def get_generate_progress(task_id: str):
    task = get_task(task_id)
    if not task:
        raise HTTPException(status_code=404, detail="任务不存在")
    return task
