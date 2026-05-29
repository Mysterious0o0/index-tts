import logging
import asyncio
import alibabacloud_oss_v2 as oss
from alibabacloud_oss_v2 import credentials
from config import (
    OSS_REGION,
    OSS_ACCESS_KEY_ID,
    OSS_ACCESS_KEY_SECRET,
    OSS_ENDPOINT,
    OSS_BUCKET,
    OSS_AUDIO_PREFIX,
)

log = logging.getLogger("oss")


def _get_client() -> oss.Client:
    cred_provider = credentials.StaticCredentialsProvider(
        OSS_ACCESS_KEY_ID, OSS_ACCESS_KEY_SECRET
    )
    cfg = oss.config.load_default()
    cfg.credentials_provider = cred_provider
    cfg.endpoint = OSS_ENDPOINT
    cfg.region = OSS_REGION
    return oss.Client(cfg)


async def upload_audio(local_path: str, record_id: str, level: str) -> str:
    oss_key = f"{OSS_AUDIO_PREFIX}level{level}/{record_id}.wav"

    def _upload():
        client = _get_client()
        with open(local_path, "rb") as f:
            client.put_object(
                oss.PutObjectRequest(
                    bucket=OSS_BUCKET,
                    key=oss_key,
                    body=f,
                )
            )
        log.info(f"[oss] 上传成功: {oss_key}")
        return oss_key

    return await asyncio.to_thread(_upload)


async def delete_audio(oss_key: str):
    def _delete():
        client = _get_client()
        client.delete_object(
            oss.DeleteObjectRequest(
                bucket=OSS_BUCKET,
                key=oss_key,
            )
        )
        log.info(f"[oss] 删除成功: {oss_key}")

    try:
        await asyncio.to_thread(_delete)
    except Exception as e:
        log.warning(f"[oss] 删除失败（已忽略）: {oss_key} — {e}")


async def get_audio_url(oss_key: str, expires: int = 3600) -> str:
    def _presign():
        client = _get_client()
        result = client.presign(
            oss.PresignRequest(
                bucket=OSS_BUCKET,
                key=oss_key,
                expires=expires,
            )
        )
        return result.url

    return await asyncio.to_thread(_presign)
