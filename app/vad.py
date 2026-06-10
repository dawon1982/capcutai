import subprocess
from array import array

_model = None


def speech_regions(path: str):
    """Silero VAD로 실제 사람 음성 구간 [(s, e)] 검출. 실패하면 [] (보정 생략).

    whisper 단어 타임스탬프는 끝이 실제보다 약간 이른 편향이 있어, 컷 경계를
    '실제로 소리가 끝난 곳'에 맞추는 보정 재료로 쓴다. 오디오는 silero의
    read_audio(torchcodec 필요) 대신 ffmpeg로 직접 PCM 디코드.
    """
    global _model
    try:
        import torch
        from silero_vad import get_speech_timestamps, load_silero_vad

        if _model is None:
            _model = load_silero_vad()
        proc = subprocess.run(
            ["ffmpeg", "-v", "error", "-i", path, "-vn",
             "-ac", "1", "-ar", "16000", "-f", "s16le", "-"],
            capture_output=True,
        )
        raw = proc.stdout
        if len(raw) < 2:
            return []
        samples = array("h")
        samples.frombytes(raw[: len(raw) // 2 * 2])
        audio = torch.tensor(samples, dtype=torch.float32) / 32768.0
        ts = get_speech_timestamps(
            audio, _model, sampling_rate=16000, return_seconds=True
        )
        return [(float(t["start"]), float(t["end"])) for t in ts]
    except Exception:
        return []
