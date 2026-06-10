import json
import subprocess
from array import array


def compute_peaks(path: str, buckets: int = 1000):
    """검토 화면 파형 표시용 진폭 피크(0~1) 리스트. 오디오 없으면 []."""
    proc = subprocess.run(
        ["ffmpeg", "-v", "error", "-i", path, "-vn",
         "-ac", "1", "-ar", "8000", "-f", "s16le", "-"],
        capture_output=True,
    )
    raw = proc.stdout
    if len(raw) < 2:
        return []
    samples = array("h")
    samples.frombytes(raw[: len(raw) // 2 * 2])
    n = len(samples)
    step = max(1, n // buckets)
    peaks = []
    for i in range(0, n, step):
        chunk = samples[i:i + step]
        peaks.append(round(max(max(chunk), -min(chunk)) / 32768, 3))
    return peaks[:buckets]


def _rotation(stream) -> int:
    """회전 메타데이터(도) 추출. side_data(신형) 우선, 없으면 tags.rotate(구형)."""
    for sd in stream.get("side_data_list", []):
        if "rotation" in sd:
            try:
                return int(sd["rotation"])
            except (TypeError, ValueError):
                pass
    r = stream.get("tags", {}).get("rotate")
    if r is not None:
        try:
            return int(r)
        except (TypeError, ValueError):
            pass
    return 0


def probe_media(path: str) -> dict:
    out = subprocess.run(
        [
            "ffprobe", "-v", "error", "-print_format", "json",
            "-show_entries",
            "format=duration"
            ":stream=width,height,r_frame_rate,codec_type"
            ":stream_tags=rotate:stream_side_data=rotation",
            path,
        ],
        capture_output=True, text=True, check=True,
    ).stdout
    data = json.loads(out)
    duration = float(data["format"]["duration"])
    width = height = None
    fps = 30.0
    for s in data.get("streams", []):
        if s.get("codec_type") == "video":
            width = int(s["width"])
            height = int(s["height"])
            # 회전 ±90/270이면 실제 표시 방향이 가로/세로 바뀜 → W/H 교환
            if _rotation(s) % 180 != 0:
                width, height = height, width
            num, _, den = s["r_frame_rate"].partition("/")
            den = float(den) if den else 1.0
            fps = float(num) / den if den else 30.0
            break
    return {"duration": duration, "width": width, "height": height, "fps": fps}
