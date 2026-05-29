import re
import subprocess

_START = re.compile(r"silence_start:\s*(-?[0-9.]+)")
_END = re.compile(r"silence_end:\s*(-?[0-9.]+)")


def detect_silence(path: str, noise_db: float = -30.0, min_silence: float = 0.3):
    """무음 구간 리스트 [(start, end)] 반환 (초 단위)."""
    proc = subprocess.run(
        [
            "ffmpeg", "-hide_banner", "-nostats", "-i", path,
            "-af", f"silencedetect=noise={noise_db}dB:d={min_silence}",
            "-f", "null", "-",
        ],
        capture_output=True, text=True,
    )
    log = proc.stderr
    starts = [float(m) for m in _START.findall(log)]
    ends = [float(m) for m in _END.findall(log)]
    intervals = []
    for i, s in enumerate(starts):
        e = ends[i] if i < len(ends) else None
        intervals.append((max(0.0, s), e))
    return intervals


def compute_keep_segments(duration: float, silences, min_keep: float = 0.2):
    """무음을 제거한 보존(말소리) 구간 리스트 [(start, end)] 반환 (초 단위)."""
    segs = []
    cursor = 0.0
    for s, e in silences:
        if e is None:
            e = duration
        if s - cursor >= min_keep:
            segs.append((cursor, s))
        cursor = max(cursor, e)
    if duration - cursor >= min_keep:
        segs.append((cursor, duration))
    return segs
