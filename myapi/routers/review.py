"""
审核路由：列表查询、通过、删除。

流程：
  生成音频 → 存 B 本地（AUDIO_TEMP_DIR）
  → 审核员从 B 本地直接播放试听
  → 通过（approved）→ 等待批量上传到 OSS
  → 删除 → 只删 B 本地文件（尚未上传 OSS）
"""

import os
import logging
from datetime import datetime
from fastapi import APIRouter, HTTPException, Query, Request
from pydantic import BaseModel
from core.database import get_records, get_record_by_id, update_record, get_batches
from config import AUDIO_TEMP_DIR

log = logging.getLogger("review")
router = APIRouter(prefix="/review", tags=["review"])


def _local_audio_url(request: Request, record_id: str) -> str | None:
    """
    拼接 B 本地音频的访问 URL。
    文件存在时返回 URL，不存在返回 None。
    """
    filename = f"{record_id}.wav"
    local_path = os.path.join(AUDIO_TEMP_DIR, filename)
    if os.path.isfile(local_path):
        proto = request.headers.get("x-forwarded-proto", request.url.scheme)
        host = request.headers.get("host", request.url.netloc)
        return f"{proto}://{host}/genVoice/audio/{filename}"

    return None


@router.get("/list")
async def list_records(
    request: Request,
    status: str = Query(None),
    level: str = Query(None),
    batch_id: str = Query(None),
    page: int = Query(1, ge=1),
    page_size: int = Query(20, ge=1, le=100),
):
    """审核 / 记录列表，audio_url 指向 B 本地文件"""
    records, total = await get_records(
        status=status,
        level=level,
        batch_id=batch_id,
        page=page,
        page_size=page_size,
    )
    # 为已上传 OSS 的记录生成临时播放 URL
    for r in records:
        # approved 之前：播放 B 本地文件
        # uploaded 之后：本地文件可能已清理，audio_url 为 None（记录页不需要播放）
        r["audio_url"] = _local_audio_url(request, r["id"])

    return {"total": total, "page": page, "page_size": page_size, "records": records}


@router.get("/batches")
async def list_batches():
    """批次列表，用于前端下拉筛选"""
    return await get_batches()


class ApproveRequest(BaseModel):
    reviewer: str = "admin"


@router.post("/{record_id}/approve")
async def approve(record_id: str, req: ApproveRequest):
    """
    审核通过 → approved。
    此时音频仍在 B 本地，等待批量上传到 OSS。
    """
    record = await get_record_by_id(record_id)
    if not record:
        raise HTTPException(status_code=404, detail="记录不存在")
    if record["status"] != "pending_review":
        raise HTTPException(
            status_code=400, detail=f"当前状态 {record['status']} 不可审核"
        )

    await update_record(
        record_id,
        status="approved",
        reviewer=req.reviewer,
        reviewed_at=datetime.now(),
    )
    return {"message": "已通过", "id": record_id}


@router.delete("/{record_id}")
async def delete_record(record_id: str, reviewer: str = Query("admin")):
    """
    删除音频（终态）：
    - 只删 B 本地临时文件（此时还未上传 OSS）
    - 软删除：status → deleted
    """
    record = await get_record_by_id(record_id)
    if not record:
        raise HTTPException(status_code=404, detail="记录不存在")

    # 删除 B 本地临时文件
    local_path = os.path.join(AUDIO_TEMP_DIR, f"{record_id}.wav")
    if os.path.isfile(local_path):
        try:
            os.remove(local_path)
            log.info(f"[review] 本地文件已删除: {local_path}")
        except Exception as e:
            log.warning(f"[review] 删除本地文件失败（已忽略）: {local_path} — {e}")

    await update_record(
        record_id,
        status="deleted",
        reviewer=reviewer,
        reviewed_at=datetime.now(),
    )
    return {"message": "已删除", "id": record_id}
