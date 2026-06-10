import asyncio
import hashlib
import json
import os

CACHE_DIR = os.path.join(os.path.dirname(__file__), "..", ".asr_cache")

# 한국어 토킹영상용 기본 모델. 정확도/속도 균형(Apple Silicon).
# 다른 모델을 쓰려면 CAPCUT_ASR_MODEL 환경변수로 교체.
MODEL = os.environ.get("CAPCUT_ASR_MODEL", "mlx-community/whisper-large-v3-turbo")

# numba(mlx-whisper 내부 JIT)가 thread-safe하지 않아 동시 호출 시 segfault.
# 여러 잡이 겹쳐도 ASR은 한 번에 하나만 돌도록 직렬화.
_asr_lock = asyncio.Lock()


def _content_hash(path: str) -> str:
    h = hashlib.sha256()
    with open(path, "rb") as f:
        while chunk := f.read(1 << 20):
            h.update(chunk)
    return h.hexdigest()[:16]


ASR_OPTS_VERSION = "v2"  # transcribe 옵션이 바뀌면 올려서 옛 캐시 무효화


def _cache_file(path: str) -> str:
    model_tag = MODEL.rsplit("/", 1)[-1]
    key = f"{_content_hash(path)}_{model_tag}_{ASR_OPTS_VERSION}"
    return os.path.join(CACHE_DIR, key + ".json")


def _transcribe_sync(path: str) -> dict:
    import mlx_whisper  # lazy: 서버 기동 시 mlx/numba 로딩 지연 회피

    result = mlx_whisper.transcribe(
        path,
        path_or_hf_repo=MODEL,
        language="ko",
        word_timestamps=True,
        # 직전 문장에 조건화하면 한 번 빠진 패턴(목록 번호, 같은 문구)을 계속 따라 하는
        # 환각이 생긴다('5. 5. 6. 7…', '20 20 20…'의 주범). 문장마다 독립 인식.
        condition_on_previous_text=False,
    )

    segments = []
    for s in result.get("segments", []):
        words = [
            {"word": w["word"], "start": w["start"], "end": w["end"]}
            for w in s.get("words", [])
        ]
        segments.append({
            "start": s["start"],
            "end": s["end"],
            "text": s["text"].strip(),
            "words": words,
        })
    return {"text": result.get("text", "").strip(), "segments": segments}


async def transcribe(path: str) -> dict:
    """영상/오디오 → {text, segments:[{start,end,text,words:[...]}]}.

    내용 해시 캐시(파일 mtime 아님 — 같은 내용은 재전사 안 함). ASR은 _asr_lock으로 직렬화.
    """
    cache_file = await asyncio.to_thread(_cache_file, path)
    if os.path.exists(cache_file):
        with open(cache_file, encoding="utf-8") as f:
            return json.load(f)

    async with _asr_lock:
        if os.path.exists(cache_file):  # 락 대기 중 다른 잡이 채웠을 수 있음
            with open(cache_file, encoding="utf-8") as f:
                return json.load(f)
        result = await asyncio.to_thread(_transcribe_sync, path)

    os.makedirs(CACHE_DIR, exist_ok=True)
    with open(cache_file, "w", encoding="utf-8") as f:
        json.dump(result, f, ensure_ascii=False)
    return result
