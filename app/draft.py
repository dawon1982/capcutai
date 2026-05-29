import json
import os
import shutil

import pycapcut as c

SEC = 1_000_000  # pycapcut 시간 단위 = 마이크로초. float은 이미 µs로 해석되므로 직접 변환.


MIN_SUB_SEC = 0.3  # 너무 짧은 자막(컷에 잘려 거의 0초)은 버림


def _us(seconds: float) -> int:
    return int(round(seconds * SEC))


def _map_to_timeline(t: float, keep_segments) -> float:
    """원본 시간 t → 점프컷 타임라인 시간. 컷(무음) 구간이면 가장 가까운 보존 경계로 스냅."""
    cum = 0.0
    for s, e in keep_segments:
        if t < s:
            return cum
        if t <= e:
            return cum + (t - s)
        cum += e - s
    return cum


def _stage_media(video_path: str, draft_path: str) -> str:
    """캡컷(맥)은 샌드박스라 컨테이너 밖 경로(~/projects 등)의 원본을 못 읽음
    ('파일에 액세스할 수 없음'). 드래프트 폴더(=캡컷이 직접 쓰는 접근 가능 영역) 안으로
    미디어를 반입해 그 경로를 참조한다. 같은 볼륨이면 하드링크(복사 비용 0), 아니면 복사.
    """
    dest = os.path.join(draft_path, os.path.basename(video_path))
    if os.path.abspath(dest) == os.path.abspath(video_path):
        return dest
    if os.path.exists(dest):
        os.remove(dest)
    try:
        os.link(video_path, dest)
    except OSError:
        shutil.copy(video_path, dest)
    return dest


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


def _add_subtitles(script, segments, keep_segments) -> int:
    """ASR 세그먼트를 점프컷 타임라인에 매핑해 자막 트랙으로 추가. 추가한 자막 수 반환."""
    style = c.TextStyle(size=8.0, color=(1.0, 1.0, 1.0), align=1, auto_wrapping=True)
    border = c.TextBorder(color=(0.0, 0.0, 0.0), width=40.0)
    clip = c.ClipSettings(transform_y=-0.82)  # 화면 하단

    script.add_track(c.TrackType.text, "자막")
    n = 0
    for seg in segments:
        text = seg["text"].strip()
        if not text:
            continue
        tl_start = _map_to_timeline(seg["start"], keep_segments)
        tl_end = _map_to_timeline(seg["end"], keep_segments)
        dur = tl_end - tl_start
        if dur < MIN_SUB_SEC:
            continue
        ts = c.TextSegment(
            text,
            c.Timerange(_us(tl_start), _us(dur)),
            style=style,
            border=border,
            clip_settings=clip,
        )
        script.add_segment(ts, "자막")
        n += 1
    return n


def build_jumpcut_draft(
    video_path: str,
    draft_name: str,
    keep_segments,
    draft_root: str,
    width: int,
    height: int,
    fps: float = 30.0,
    segments=None,
) -> str:
    video_path = os.path.abspath(video_path)
    folder = c.DraftFolder(draft_root)
    script = folder.create_draft(
        draft_name, width, height, fps=int(round(fps)), allow_replace=True
    )
    draft_path = os.path.join(draft_root, draft_name)
    staged = _stage_media(video_path, draft_path)
    script.add_track(c.TrackType.video)

    material = c.VideoMaterial(staged)
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

    if segments:
        _add_subtitles(script, segments, keep_segments)

    script.save()

    _finalize_draft(draft_path)
    return draft_path
