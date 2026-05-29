import json
import os
import uuid

from fastapi import FastAPI, File, HTTPException, UploadFile
from fastapi.responses import FileResponse, StreamingResponse

from app.pipeline import run_pipeline, safe_draft_name

BASE = os.path.dirname(__file__)
UPLOADS = os.path.join(BASE, "..", "uploads")
STATIC = os.path.join(BASE, "static")
os.makedirs(UPLOADS, exist_ok=True)

ALLOWED_EXT = {".mp4", ".mov", ".m4v"}

app = FastAPI(title="캡컷 에이전트")
_jobs: dict[str, dict] = {}


@app.post("/api/upload")
async def upload(file: UploadFile = File(...)):
    ext = os.path.splitext(file.filename or "")[1].lower()
    if ext not in ALLOWED_EXT:
        raise HTTPException(400, f"지원 형식: mp4, mov, m4v (받은 형식: {ext or '없음'})")
    job_id = uuid.uuid4().hex
    dest = os.path.join(UPLOADS, job_id + ext)
    with open(dest, "wb") as f:
        while chunk := await file.read(1 << 20):
            f.write(chunk)
    _jobs[job_id] = {"path": dest, "name": file.filename}
    return {"job_id": job_id, "filename": file.filename}


@app.get("/api/stream/{job_id}")
async def stream(job_id: str):
    job = _jobs.get(job_id)
    if not job:
        raise HTTPException(404, "job not found")
    draft_name = safe_draft_name(job["name"])

    async def gen():
        async for ev in run_pipeline(job["path"], draft_name):
            yield f"data: {json.dumps(ev, ensure_ascii=False)}\n\n"

    return StreamingResponse(gen(), media_type="text/event-stream")


@app.get("/")
async def index():
    return FileResponse(os.path.join(STATIC, "index.html"))
