"""
TTS 服务，复用原有批量生成逻辑：
- cache/gen/ 目录下有 level1.WAV / level2.WAV / level3.WAV
- 按 level 对应同名 prompt wav 生成音频
- 记录按 level 分组后分配给对应 prompt wav
"""

import os
import logging
from pathlib import Path

import numpy as np

from config import TTS_CFG_PATH, TTS_MODEL_DIR, TTS_PROMPT_WAV_DIR, AUDIO_TEMP_DIR

log = logging.getLogger("tts")

# ──────────────────────────────────────────
# 单例 TTS 模型（懒加载，首次调用时初始化）
# ──────────────────────────────────────────
_tts = None


def get_tts():
    global _tts
    if _tts is None:
        from indextts.infer_v2 import IndexTTS2

        _tts = IndexTTS2(
            cfg_path=TTS_CFG_PATH,
            model_dir=TTS_MODEL_DIR,
            use_fp16=True,
            use_cuda_kernel=True,
            use_deepspeed=True,
        )
        log.info("[tts] 模型加载完成")
    return _tts


def _get_prompt_wav(level: str) -> str:
    """
    根据 level 返回对应的 prompt wav 路径。
    cache/gen/level1.WAV → level=1
    cache/gen/level2.WAV → level=2
    cache/gen/level3.WAV → level=3
    """
    wav_dir = Path(TTS_PROMPT_WAV_DIR)
    # 兼容大小写
    for ext in (".WAV", ".wav"):
        p = wav_dir / f"level{level}{ext}"
        if p.exists():
            return str(p)
    raise FileNotFoundError(f"[tts] 找不到 level{level} 对应的 prompt wav: {wav_dir}")


def _get_all_prompt_wavs() -> list[str]:
    """返回目录下所有 prompt wav，按文件名排序"""
    wav_dir = Path(TTS_PROMPT_WAV_DIR)
    wavs = sorted(
        [str(p) for p in wav_dir.glob("*.wav")]
        + [str(p) for p in wav_dir.glob("*.WAV")]
    )
    if not wavs:
        raise FileNotFoundError(f"[tts] prompt wav 目录为空: {TTS_PROMPT_WAV_DIR}")
    return wavs


# ──────────────────────────────────────────
# 批量生成（同步，在线程池中调用）
# ──────────────────────────────────────────


def batch_generate_audio(
    records: list[dict],
    progress_callback=None,
) -> list[dict]:
    """
    批量生成音频，复用原有逻辑：
    - 按 level 分组，每组使用对应 prompt wav（level1.WAV / level2.WAV / level3.WAV）
    - 同一 level 内有多条记录时，全部使用该 level 的 prompt wav
    - 若某条记录找不到对应 level wav，fallback 到全部 prompt wav 均分逻辑

    records: [{ id, text, level }, ...]
    返回:    [{ id, text, level, local_path, success, error? }, ...]
    """
    os.makedirs(AUDIO_TEMP_DIR, exist_ok=True)
    tts = get_tts()
    results = []
    total = len(records)
    done = 0

    # 按 level 分组
    from collections import defaultdict

    level_groups: dict[str, list[dict]] = defaultdict(list)
    for r in records:
        level_groups[r["level"]].append(r)

    for level, group in level_groups.items():
        # 获取该 level 对应的 prompt wav
        try:
            prompt_wav = _get_prompt_wav(level)
        except FileNotFoundError:
            # fallback：均分到所有 prompt wav
            log.warning(f"[tts] level{level} 无对应 prompt wav，fallback 到均分模式")
            all_wavs = _get_all_prompt_wavs()
            chunks = np.array_split(group, len(all_wavs))
            for wav, chunk in zip(all_wavs, chunks):
                for record in chunk:
                    res = _infer_one(tts, record, wav)
                    results.append(res)
                    done += 1
                    if progress_callback:
                        progress_callback(done, total)
            continue

        # 正常路径：整组用同一个 prompt wav
        for record in group:
            res = _infer_one(tts, record, prompt_wav)
            results.append(res)
            done += 1
            if progress_callback:
                progress_callback(done, total)

    return results


def _infer_one(tts, record: dict, prompt_wav: str) -> dict:
    """单条推理，返回结果字典"""
    rid = record["id"]
    text = record["text"]
    out_path = os.path.join(AUDIO_TEMP_DIR, f"{rid}.wav")
    try:
        if not os.path.isfile(out_path):
            tts.infer(
                spk_audio_prompt=prompt_wav,
                text=text,
                output_path=out_path,
                verbose=False,
            )
        log.info(f"[tts] 生成完成: {out_path}")
        return {
            "id": rid,
            "text": text,
            "level": record["level"],
            "local_path": out_path,
            "success": True,
        }
    except Exception as e:
        log.error(f"[tts] 生成失败 id={rid}: {e}")
        return {
            "id": rid,
            "text": text,
            "level": record["level"],
            "local_path": "",
            "success": False,
            "error": str(e),
        }
