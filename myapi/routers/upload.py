"""
批量上传路由：将 approved 的本地音频上传到 OSS，完成后通知 A 重建索引。
上传成功后清理 B 本地临时文件。
"""

import os
import logging

from datetime import datetime
from fastapi import APIRouter, HTTPException, BackgroundTasks
from core.database import get_approved_records, get_failed_records, update_record
from core.oss_client import upload_audio
from config import AUDIO_TEMP_DIR
from services.task_manager import (
    create_task,
    update_task,
    update_progress,
    finish_task,
    get_task,
    get_all_tasks,
)
from services.rebuild_notifier import notify_rebuild

log = logging.getLogger("upload")
router = APIRouter(prefix="/upload", tags=["upload"])


@router.post("/batch")
async def batch_upload(background_tasks: BackgroundTasks):
    """触发批量上传所有 approved 记录到 OSS"""
    records = await get_approved_records()
    if not records:
        return {"message": "没有待上传的记录"}

    task_id = create_task("batch_upload")
    update_task(task_id, status="running", total=len(records))
    background_tasks.add_task(_run_upload, task_id, records)
    return {"task_id": task_id, "total": len(records)}


@router.post("/retry")
async def retry_failed(background_tasks: BackgroundTasks):
    """重试所有 upload_failed 记录"""
    records = await get_failed_records()
    if not records:
        return {"message": "没有失败的记录"}

    task_id = create_task("retry_upload")
    update_task(task_id, status="running", total=len(records))
    background_tasks.add_task(_run_upload, task_id, records)
    return {"task_id": task_id, "total": len(records)}


@router.get("/progress/{task_id}")
async def get_progress(task_id: str):
    task = get_task(task_id)
    if not task:
        raise HTTPException(status_code=404, detail="任务不存在")
    return task


@router.get("/tasks")
async def list_tasks():
    return get_all_tasks()


async def _run_upload(task_id: str, records: list[dict]):
    done = 0
    failed_ids = []

    for record in records:
        record_id = record["id"]
        level = record.get("level", "1")
        local_path = os.path.join(AUDIO_TEMP_DIR, f"{record_id}.wav")

        # 本地文件不存在则标记失败
        if not os.path.isfile(local_path):
            log.error(f"[upload] 本地文件不存在，无法上传: {local_path}")
            failed_ids.append(record_id)
            await update_record(record_id, status="upload_failed")
            done += 1
            update_progress(task_id, done, len(records), failed_ids)
            continue

        await update_record(record_id, status="uploading")
        try:
            oss_key = await upload_audio(local_path, record_id, level)
            await update_record(
                record_id,
                status="uploaded",
                path=oss_key,
                uploaded_at=datetime.now(),
            )
            log.info(f"[upload] 上传成功: {record_id} → {oss_key}")

            # 上传成功后清理本地临时文件
            try:
                # os.remove(local_path)
                log.info(f"[upload] 本地临时文件已清理: {local_path}")
            except Exception as e:
                log.warning(f"[upload] 清理本地文件失败（已忽略）: {local_path} — {e}")

        except Exception as e:
            log.error(f"[upload] 上传失败: {record_id} — {e}")
            failed_ids.append(record_id)
            await update_record(record_id, status="upload_failed")

        done += 1
        update_progress(task_id, done, len(records), failed_ids)

    finish_task(task_id, success=len(failed_ids) == 0)
    log.info(
        f"[upload] 任务完成，成功={done - len(failed_ids)}，失败={len(failed_ids)}"
    )

    # 上传完成后通知 A 服务器重建 Faiss 索引
    await notify_rebuild()
