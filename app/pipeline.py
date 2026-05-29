import asyncio
import os
import re

from app.draft import build_jumpcut_draft
from app.probe import probe_media
from app.silence import compute_keep_segments, detect_silence

DRAFT_ROOT = os.path.expanduser(
    "~/Movies/CapCut/User Data/Projects/com.lveditor.draft"
)
MIN_STEP_SECONDS = 0.5  # 캐시 hit으로 즉시 끝나도 스테퍼 애니메이션이 보이도록 최소 지연


def safe_draft_name(filename: str) -> str:
    stem = os.path.splitext(os.path.basename(filename))[0]
    stem = re.sub(r"[^0-9A-Za-z가-힣_-]+", "_", stem).strip("_")
    return f"capcut_agent_{stem or 'draft'}"


async def _pad(t0: float):
    elapsed = asyncio.get_event_loop().time() - t0
    if elapsed < MIN_STEP_SECONDS:
        await asyncio.sleep(MIN_STEP_SECONDS - elapsed)


async def run_pipeline(video_path: str, draft_name: str, opts: dict | None = None):
    """영상 1개 처리. SSE용 이벤트 dict를 yield. (2단: asr/filler는 아직 stub)"""
    opts = opts or {}
    noise = opts.get("noise", -30.0)
    min_silence = opts.get("min_silence", 0.3)
    min_keep = opts.get("min_keep", 0.2)
    loop = asyncio.get_event_loop()

    try:
        # 1) 무음 검출
        yield {"step": "silence", "status": "running"}
        t0 = loop.time()
        info = await asyncio.to_thread(probe_media, video_path)
        silences = await asyncio.to_thread(
            detect_silence, video_path, noise, min_silence
        )
        keeps = compute_keep_segments(info["duration"], silences, min_keep)
        await _pad(t0)
        yield {"step": "silence", "status": "done",
               "stats": {"n_silence": len(silences), "n_keep": len(keeps)}}

        # 2) 음성 인식 (3단에서 구현)
        yield {"step": "asr", "status": "running"}
        t0 = loop.time()
        await _pad(t0)
        yield {"step": "asr", "status": "skipped"}

        # 3) 잔말·NG (4단에서 구현)
        yield {"step": "filler", "status": "running"}
        t0 = loop.time()
        await _pad(t0)
        yield {"step": "filler", "status": "skipped"}

        # 4) 드래프트 (+자막은 3단)
        yield {"step": "draft", "status": "running"}
        t0 = loop.time()
        draft_path = await asyncio.to_thread(
            build_jumpcut_draft, video_path, draft_name, keeps,
            DRAFT_ROOT, info["width"], info["height"], info["fps"],
        )
        await _pad(t0)
        yield {"step": "draft", "status": "done"}

        output_sec = sum(e - s for s, e in keeps)
        yield {"step": "result", "status": "done", "result": {
            "input_sec": round(info["duration"], 2),
            "output_sec": round(output_sec, 2),
            "cut_sec": round(info["duration"] - output_sec, 2),
            "n_cuts": len(silences),
            "draft_name": draft_name,
            "draft_path": draft_path,
        }}
    except Exception as e:
        yield {"step": "error", "status": "error", "message": str(e)}
