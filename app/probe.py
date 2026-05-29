import json
import subprocess


def probe_media(path: str) -> dict:
    out = subprocess.run(
        [
            "ffprobe", "-v", "error", "-print_format", "json",
            "-show_entries", "format=duration:stream=width,height,r_frame_rate,codec_type",
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
            num, _, den = s["r_frame_rate"].partition("/")
            den = float(den) if den else 1.0
            fps = float(num) / den if den else 30.0
            break
    return {"duration": duration, "width": width, "height": height, "fps": fps}
