import asyncio
import os
import re

from app.asr import transcribe
from app.draft import build_jumpcut_draft
from app.probe import probe_media
from app.script_edit import (
    find_filler_cuts,
    find_ng_candidates,
    strip_fillers,
    subtract_cuts,
)
from app.silence import compute_keep_segments, detect_silence

DRAFT_ROOT = os.path.expanduser(
    "~/Movies/CapCut/User Data/Projects/com.lveditor.draft"
)
MIN_STEP_SECONDS = 0.5  # 캐시 hit으로 즉시 끝나도 스테퍼 애니메이션이 보이도록 최소 지연

NOISE_DB = -30.0
MIN_SILENCE_DEFAULT = 0.5  # 이보다 긴 쉼만 컷(검토 화면 슬라이더로 조절)
MIN_KEEP = 0.2
KEEP_PAD = 0.15  # 컷 양옆 여유(말 끝소리·호흡 보존)


def safe_draft_name(filename: str) -> str:
    stem = os.path.splitext(os.path.basename(filename))[0]
    stem = re.sub(r"[^0-9A-Za-z가-힣_-]+", "_", stem).strip("_")
    return f"capcut_agent_{stem or 'draft'}"


async def _pad(t0: float):
    elapsed = asyncio.get_event_loop().time() - t0
    if elapsed < MIN_STEP_SECONDS:
        await asyncio.sleep(MIN_STEP_SECONDS - elapsed)


async def run_pipeline(video_path: str, opts: dict | None = None):
    """영상 분석(무음→ASR→잔말). 드래프트는 만들지 않고 ready 이벤트로 분석 결과를 넘긴다.
    실제 드래프트는 사용자가 검토 화면에서 보존 구간을 확정한 뒤 build_draft_from_keeps로 생성."""
    opts = opts or {}
    noise = opts.get("noise", NOISE_DB)
    min_silence = opts.get("min_silence", MIN_SILENCE_DEFAULT)
    min_keep = opts.get("min_keep", MIN_KEEP)
    loop = asyncio.get_event_loop()

    try:
        # 1) 무음 검출
        yield {"step": "silence", "status": "running"}
        t0 = loop.time()
        info = await asyncio.to_thread(probe_media, video_path)
        silences = await asyncio.to_thread(
            detect_silence, video_path, noise, min_silence
        )
        keeps = compute_keep_segments(info["duration"], silences, min_keep, KEEP_PAD)
        await _pad(t0)
        yield {"step": "silence", "status": "done",
               "stats": {"n_silence": len(silences), "n_keep": len(keeps)}}

        # 2) 음성 인식 (mlx-whisper, 세그먼트+단어)
        yield {"step": "asr", "status": "running"}
        t0 = loop.time()
        transcript = await transcribe(video_path)
        segments = transcript["segments"]
        await _pad(t0)
        yield {"step": "asr", "status": "done",
               "stats": {"n_segments": len(segments)}}

        # 3) 잔말 컷(자동) + NG 후보(표시만)
        yield {"step": "filler", "status": "running"}
        t0 = loop.time()
        filler_cuts = find_filler_cuts(segments)
        keeps = subtract_cuts(keeps, filler_cuts, min_keep)
        ng = find_ng_candidates(segments)
        await _pad(t0)
        yield {"step": "filler", "status": "done",
               "stats": {"n_filler": len(filler_cuts), "n_ng": len(ng)}}

        yield {"step": "ready", "data": {
            "info": info,
            "keeps": keeps,
            "segments": segments,
            "ng": ng,
            "transcript": transcript["text"],
            "n_filler": len(filler_cuts),
            "min_silence": min_silence,
        }}
    except Exception as e:
        yield {"step": "error", "status": "error", "message": str(e)}


def recompute_keeps(video_path, duration, min_silence, segments):
    """검토 화면 '쉼 감도' 슬라이더용: ASR 없이 무음 재검출 → 보존 구간 재계산.
    초기 분석과 동일하게 잔말 컷도 다시 빼준다(감도 조절해도 잔말은 계속 제거)."""
    silences = detect_silence(video_path, NOISE_DB, min_silence)
    keeps = compute_keep_segments(duration, silences, MIN_KEEP, KEEP_PAD)
    filler_cuts = find_filler_cuts(segments)
    return subtract_cuts(keeps, filler_cuts, MIN_KEEP)


def build_draft_from_keeps(video_path, draft_name, keeps, info, segments):
    """검토 화면에서 사용자가 확정한 keeps로 캡컷 드래프트 생성. 자막은 잔말 제거본 사용."""
    sub = strip_fillers(segments)
    return build_jumpcut_draft(
        video_path, draft_name, keeps, DRAFT_ROOT,
        info["width"], info["height"], info["fps"], sub,
    )
