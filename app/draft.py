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
        content = json.load(f)
    duration = content.get("duration", 0)

    # 회전 영상 보정: pycapcut은 영상 소재 크기를 회전 무시한 저장 크기로 쓴다.
    # 캔버스(회전 반영)와 W/H가 뒤바뀐 경우 소재 크기를 캔버스에 맞춰 일관성 확보
    # (안 맞추면 캡컷이 영상을 레터박스 → 검은 여백).
    canvas = content.get("canvas_config", {})
    cw, ch = canvas.get("width"), canvas.get("height")
    patched = False
    if cw and ch:
        for v in content.get("materials", {}).get("videos", []):
            if v.get("width") == ch and v.get("height") == cw:
                v["width"], v["height"] = cw, ch
                patched = True
    if patched:
        with open(content_path, "w") as f:
            json.dump(content, f, ensure_ascii=False)

    meta_path = os.path.join(draft_path, "draft_meta_info.json")
    with open(meta_path) as f:
        meta = json.load(f)
    meta["tm_duration"] = duration
    with open(meta_path, "w") as f:
        json.dump(meta, f, ensure_ascii=False)

    shutil.copy(content_path, os.path.join(draft_path, "draft_info.json"))


MAX_SUB_CHARS = 16  # 캡션 1줄 목표 글자 수(이보다 길면 짧게 끊음)


def _split_caption(text: str, max_chars: int = MAX_SUB_CHARS):
    """긴 자막을 단어 경계에서 max_chars 이하 줄들로 분할(캡션 1줄 유지용)."""
    lines, cur = [], ""
    for w in text.split():
        if cur and len(cur) + 1 + len(w) > max_chars:
            lines.append(cur)
            cur = w
        else:
            cur = f"{cur} {w}" if cur else w
    if cur:
        lines.append(cur)
    return lines or [text]


SUB_HOLD = 0.7  # 캡션을 다음 캡션 시작까지(최대 HOLD초) 유지해 깜빡임 방지
MIN_RAW_SUB = 0.1  # 매핑 후 실 발화 구간이 이보다 짧으면(=대부분 컷됨) 캡션 생략


def _group_words(words, max_chars=MAX_SUB_CHARS):
    """단어들을 캡션 1줄(≤max_chars) 단위로 묶되, 어미·조사·문장부호 등
    자연스러운 끊김 지점에서 우선 분할(글자수 위치에서 기계적으로 끊지 않게)."""
    groups, cur, cur_len, brk = [], [], 0, -1
    for w in words:
        tok = w["word"].strip()
        add = len(tok) + (1 if cur else 0)
        if cur and cur_len + add > max_chars:
            if 0 <= brk < len(cur) - 1:  # 자연 분할점이 있으면 거기서 끊기
                groups.append(cur[:brk + 1])
                cur = cur[brk + 1:]
            else:
                groups.append(cur)
                cur = []
            cur_len = sum(len(x["word"].strip()) for x in cur) + max(0, len(cur) - 1)
            brk = -1
            add = len(tok) + (1 if cur else 0)
            if cur and cur_len + add > max_chars:  # 남은 조각도 넘치면 통째로 확정
                groups.append(cur)
                cur, cur_len = [], 0
                add = len(tok)
        cur.append(w)
        cur_len += add
        core = tok.rstrip(".,?!…\"'")
        if cur_len >= 6 and (tok[-1:] in ".,?!…" or (core and core[-1] in "요다죠까데고서며면")):
            brk = len(cur) - 1
    if cur:
        groups.append(cur)
    return groups


def compute_captions(segments, keep_segments):
    """단어 타임스탬프 기반 캡션 목록 [[text, tl_start, tl_end], ...] 생성.

    글자수 비례 추정이 아니라 각 캡션에 속한 단어의 실제 발화 시각을 점프컷
    타임라인에 매핑해 배치한다(자막 싱크 정확도). 단어 정보가 없는 세그먼트만
    글자수 비례 폴백.
    """
    caps = []
    for seg in segments:
        text = seg["text"].strip()
        if not text:
            continue
        words = [w for w in seg.get("words", []) if w["word"].strip()]
        if words:
            for g in _group_words(words):
                gtext = "".join(x["word"] for x in g).strip().rstrip(".").rstrip()
                if not gtext:
                    continue
                ts = _map_to_timeline(g[0]["start"], keep_segments)
                te = _map_to_timeline(g[-1]["end"], keep_segments)
                if te - ts < MIN_RAW_SUB:  # 단어들이 컷 안에 들어가 사라진 캡션
                    continue
                caps.append([gtext, ts, te])
        else:
            tl_start = _map_to_timeline(seg["start"], keep_segments)
            tl_end = _map_to_timeline(seg["end"], keep_segments)
            dur = tl_end - tl_start
            if dur < MIN_SUB_SEC:
                continue
            chunks = [ch.rstrip().rstrip(".").rstrip() for ch in _split_caption(text)]
            chunks = [ch for ch in chunks if ch]
            total = sum(len(ch) for ch in chunks) or 1
            t = tl_start
            for ch in chunks:
                e = t + dur * (len(ch) / total)
                caps.append([ch, t, e])
                t = e
    caps.sort(key=lambda x: x[1])
    # 캡션 사이 짧은 틈은 다음 캡션 시작까지 끌어서 메움(깜빡임 방지)
    for i, cap in enumerate(caps):
        if i + 1 < len(caps):
            cap[2] = max(cap[2], min(caps[i + 1][1], cap[2] + SUB_HOLD))
        else:
            cap[2] += 0.3
    return caps


def captions_to_srt(caps) -> str:
    """캡션 목록 → SRT 문자열 (유튜브 등 자막 파일로 활용)."""
    def ts(sec):
        ms = int(round(sec * 1000))
        h, rem = divmod(ms, 3600000)
        m, rem = divmod(rem, 60000)
        s, ms = divmod(rem, 1000)
        return f"{h:02d}:{m:02d}:{s:02d},{ms:03d}"

    lines = []
    for i, (text, a, b) in enumerate(caps, 1):
        lines.append(f"{i}\n{ts(a)} --> {ts(b)}\n{text}\n")
    return "\n".join(lines)


def _add_subtitles(script, segments, keep_segments) -> int:
    """캡션 목록을 자막 트랙으로 추가. 추가한 자막 수 반환."""
    # auto_wrapping=True → 캡컷에서 '자막(캡션)' 타입. 짧게 끊으므로 실제로는 1줄.
    style = c.TextStyle(size=8.0, color=(1.0, 1.0, 1.0), align=1,
                        auto_wrapping=True, max_line_width=1.0)
    border = c.TextBorder(color=(0.0, 0.0, 0.0), width=40.0)
    clip = c.ClipSettings(transform_y=-0.82)  # 화면 하단

    script.add_track(c.TrackType.text, "자막")
    n = 0
    cursor_us = 0  # 정수 µs로 항상 이전 캡션 끝 이후에 배치(겹침·반올림 1µs 겹침 방지)
    for text, ts_sec, te_sec in compute_captions(segments, keep_segments):
        start_us = max(_us(ts_sec), cursor_us)
        end_us = _us(te_sec)
        if end_us - start_us < _us(MIN_SUB_SEC):
            continue
        ts = c.TextSegment(
            text, c.Timerange(start_us, end_us - start_us),
            style=style, border=border, clip_settings=clip,
        )
        script.add_segment(ts, "자막")
        n += 1
        cursor_us = end_us
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
    # ffprobe 컨테이너 길이가 실제 소재 길이보다 길 수 있어(오디오/비디오 트랙 길이 차) 보존
    # 구간이 소재 끝을 넘으면 pycapcut이 크래시한다. 소재 실제 길이로 클램프.
    mat_dur = material.duration / SEC
    keep_segments = [
        (s, min(e, mat_dur)) for s, e in keep_segments if min(e, mat_dur) - s > 0
    ]

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
