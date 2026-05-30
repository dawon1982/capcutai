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


def compute_keep_segments(
    duration: float, silences, min_keep: float = 0.2, pad: float = 0.2
):
    """무음을 제거한 보존(말소리) 구간 리스트 [(start, end)] 반환 (초 단위).

    pad: 각 컷 양옆에 남길 여유(초). 단어 끝소리(받침·잦아드는 모음)가 무음으로
    잡혀 말이 채 끝나기 전에 잘리는 걸 막고, 자연스러운 호흡 쉼을 남긴다.
    패딩을 빼고도 남는 무음만 실제로 컷하므로 짧은 쉼은 잘리지 않는다.
    """
    cuts = []
    for s, e in silences:
        if e is None:
            e = duration
        cs, ce = s + pad, e - pad
        if ce - cs > 0:
            cuts.append((cs, ce))

    segs = []
    cursor = 0.0
    for cs, ce in cuts:
        if cs - cursor >= min_keep:
            segs.append((cursor, cs))
        cursor = max(cursor, ce)
    if duration - cursor >= min_keep:
        segs.append((cursor, duration))
    return segs
