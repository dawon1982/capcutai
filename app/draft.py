import json
import os
import shutil

import pycapcut as c

SEC = 1_000_000  # pycapcut 시간 단위 = 마이크로초. float은 이미 µs로 해석되므로 직접 변환.


def _us(seconds: float) -> int:
    return int(round(seconds * SEC))


def _finalize_draft(draft_path: str) -> None:
    """pycapcut가 안 채우는 캡컷 8.x 필수 항목 보정.

    - draft_meta_info.json의 tm_duration=0 → 실제 길이로 (0이면 홈/에디터가 00:00, 재생 불가)
    - draft_content.json → draft_info.json 복사 (신버전 캡컷은 draft_info.json을 읽음)
    """
    content_path = os.path.join(draft_path, "draft_content.json")
    with open(content_path) as f:
        duration = json.load(f).get("duration", 0)

    meta_path = os.path.join(draft_path, "draft_meta_info.json")
    with open(meta_path) as f:
        meta = json.load(f)
    meta["tm_duration"] = duration
    with open(meta_path, "w") as f:
        json.dump(meta, f, ensure_ascii=False)

    shutil.copy(content_path, os.path.join(draft_path, "draft_info.json"))


def build_jumpcut_draft(
    video_path: str,
    draft_name: str,
    keep_segments,
    draft_root: str,
    width: int,
    height: int,
    fps: float = 30.0,
) -> str:
    video_path = os.path.abspath(video_path)
    folder = c.DraftFolder(draft_root)
    script = folder.create_draft(
        draft_name, width, height, fps=int(round(fps)), allow_replace=True
    )
    script.add_track(c.TrackType.video)

    material = c.VideoMaterial(video_path)
    timeline = 0.0
    for s, e in keep_segments:
        dur = e - s
        if dur <= 0:
            continue
        seg = c.VideoSegment(
            material,
            c.Timerange(_us(timeline), _us(dur)),
            source_timerange=c.Timerange(_us(s), _us(dur)),
        )
        script.add_segment(seg)
        timeline += dur

    script.save()

    draft_path = os.path.join(draft_root, draft_name)
    _finalize_draft(draft_path)
    return draft_path
