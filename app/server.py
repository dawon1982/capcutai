import asyncio
import json
import os
import time
import uuid

from fastapi import Body, FastAPI, File, HTTPException, UploadFile
from fastapi.responses import FileResponse, StreamingResponse

from app.pipeline import (
    build_draft_from_keeps,
    recompute_keeps,
    run_pipeline,
    safe_draft_name,
)

BASE = os.path.dirname(__file__)
UPLOADS = os.path.join(BASE, "..", "uploads")
STATIC = os.path.join(BASE, "static")
os.makedirs(UPLOADS, exist_ok=True)

ALLOWED_EXT = {".mp4", ".mov", ".m4v"}
MAX_UPLOAD_BYTES = 8 * 1024 ** 3  # 폭주 방지 상한(일반 토킹영상엔 충분)
JOB_TTL_SEC = 48 * 3600  # 이보다 오래된 미완료 잡은 새 업로드 때 정리
JOBS_FILE = os.path.join(UPLOADS, "jobs.json")


def _save_jobs():
    """잡·분석 결과를 디스크에 영속화 — 서버 재시작 후에도 검토 이어가기."""
    try:
        with open(JOBS_FILE, "w") as f:
            json.dump(_jobs, f, ensure_ascii=False)
    except OSError:
        pass


def _load_jobs() -> dict:
    try:
        with open(JOBS_FILE) as f:
            data = json.load(f)
    except (OSError, json.JSONDecodeError):
        return {}
    return {jid: j for jid, j in data.items() if os.path.isfile(j.get("path", ""))}


def _clear_uploads(keep_paths):
    """살아있는 잡이 참조하지 않는 업로드 잔여물만 정리. 빌드된 드래프트는
    미디어를 드래프트 폴더로 따로 반입(하드링크/복사)하므로 원본을 지워도 안전."""
    keep = {os.path.abspath(p) for p in keep_paths} | {os.path.abspath(JOBS_FILE)}
    try:
        for f in os.listdir(UPLOADS):
            p = os.path.abspath(os.path.join(UPLOADS, f))
            if os.path.isfile(p) and p not in keep:
                os.remove(p)
    except OSError:
        pass


_jobs: dict[str, dict] = _load_jobs()
_clear_uploads(j["path"] for j in _jobs.values())

app = FastAPI(title="캡컷 에이전트")


def _sanitize_keeps(raw, duration: float):
    """외부 입력 경계 검증: [[s,e],...] → 0<=s<e<=duration로 클램프·정렬, 무효 폐기."""
    out = []
    for item in raw or []:
        try:
            s, e = float(item[0]), float(item[1])
        except (TypeError, ValueError, IndexError):
            continue
        s = max(0.0, min(s, duration))
        e = max(0.0, min(e, duration))
        if e - s > 0.01:
            out.append((s, e))
    out.sort()
    return out


def _prune_old_jobs():
    now = time.time()
    for jid in [j for j, v in _jobs.items() if now - v.get("ts", now) > JOB_TTL_SEC]:
        try:
            os.remove(_jobs[jid]["path"])
        except OSError:
            pass
        _jobs.pop(jid, None)


@app.post("/api/upload")
async def upload(file: UploadFile = File(...)):
    ext = os.path.splitext(file.filename or "")[1].lower()
    if ext not in ALLOWED_EXT:
        raise HTTPException(400, f"지원 형식: mp4, mov, m4v (받은 형식: {ext or '없음'})")
    _prune_old_jobs()
    job_id = uuid.uuid4().hex
    dest = os.path.join(UPLOADS, job_id + ext)
    total = 0
    with open(dest, "wb") as f:
        while chunk := await file.read(1 << 20):
            total += len(chunk)
            if total > MAX_UPLOAD_BYTES:
                f.close()
                os.remove(dest)
                raise HTTPException(413, "파일이 너무 큽니다 (8GB 제한)")
            f.write(chunk)
    _jobs[job_id] = {"path": dest, "name": file.filename, "ts": time.time()}
    _save_jobs()
    return {"job_id": job_id, "filename": file.filename}


@app.get("/api/stream/{job_id}")
async def stream(job_id: str):
    job = _jobs.get(job_id)
    if not job:
        raise HTTPException(404, "job not found")

    async def gen():
        async for ev in run_pipeline(job["path"]):
            if ev.get("step") == "ready":
                data = ev["data"]
                job["analysis"] = data  # segments(words 포함)·info는 서버 보관
                _save_jobs()
                client = {"step": "ready", "video": {
                    "duration": round(data["info"]["duration"], 3),
                    "fps": data["info"]["fps"],
                    "keeps": [[round(s, 3), round(e, 3)] for s, e in data["keeps"]],
                    "ng": data["ng"],
                    "transcript": data["transcript"],
                    "n_segments": len(data["segments"]),
                    "n_filler": data["n_filler"],
                    "min_silence": data["min_silence"],
                    "pad": data["pad"],
                    "peaks": data["peaks"],
                }}
                yield f"data: {json.dumps(client, ensure_ascii=False)}\n\n"
            else:
                yield f"data: {json.dumps(ev, ensure_ascii=False)}\n\n"

    return StreamingResponse(gen(), media_type="text/event-stream")


@app.get("/api/video/{job_id}")
async def video(job_id: str):
    job = _jobs.get(job_id)
    if not job:
        raise HTTPException(404, "job not found")
    return FileResponse(job["path"])  # starlette FileResponse가 Range 처리 → seek 가능


@app.post("/api/reanalyze/{job_id}")
async def reanalyze(job_id: str, payload: dict = Body(...)):
    job = _jobs.get(job_id)
    if not job or "analysis" not in job:
        raise HTTPException(404, "job not found or not analyzed")
    try:
        min_silence = float(payload.get("min_silence"))
        pad = float(payload.get("pad"))
    except (TypeError, ValueError):
        raise HTTPException(400, "min_silence/pad 값이 올바르지 않습니다")
    min_silence = max(0.1, min(min_silence, 2.0))  # 외부 입력 클램프
    pad = max(0.0, min(pad, 0.5))
    info = job["analysis"]["info"]
    keeps = await asyncio.to_thread(
        recompute_keeps, job["path"], info["duration"], min_silence,
        job["analysis"]["segments"], pad,
    )
    return {"keeps": [[round(s, 3), round(e, 3)] for s, e in keeps]}


@app.post("/api/build/{job_id}")
async def build(job_id: str, payload: dict = Body(...)):
    job = _jobs.get(job_id)
    if not job or "analysis" not in job:
        raise HTTPException(404, "job not found or not analyzed")
    info = job["analysis"]["info"]
    keeps = _sanitize_keeps(payload.get("keeps"), info["duration"])
    if not keeps:
        raise HTTPException(400, "보존 구간이 비어 있습니다")

    draft_name = safe_draft_name(job["name"])
    draft_path, transcript, srt = await asyncio.to_thread(
        build_draft_from_keeps, job["path"], draft_name, keeps,
        info, job["analysis"]["segments"],
    )
    output_sec = sum(e - s for s, e in keeps)
    resp = {
        "input_sec": round(info["duration"], 2),
        "output_sec": round(output_sec, 2),
        "cut_sec": round(info["duration"] - output_sec, 2),
        "n_cuts": len(keeps),
        "n_segments": len(job["analysis"]["segments"]),
        "n_filler": job["analysis"]["n_filler"],
        "transcript": transcript,  # 자막과 동일하게 정리된 대본
        "srt": srt,
        "ng": job["analysis"]["ng"],
        "draft_name": draft_name,
        "draft_path": draft_path,
    }
    # 빌드 완료 → 업로드 원본 정리(미디어는 드래프트 폴더로 반입됨). 잡도 소비됨.
    try:
        os.remove(job["path"])
    except OSError:
        pass
    _jobs.pop(job_id, None)
    _save_jobs()
    return resp


@app.get("/")
async def index():
    return FileResponse(os.path.join(STATIC, "index.html"))
