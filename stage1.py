import argparse
import os

from app.draft import build_jumpcut_draft
from app.probe import probe_media
from app.silence import compute_keep_segments, detect_silence

DRAFT_ROOT = os.path.expanduser(
    "~/Movies/CapCut/User Data/Projects/com.lveditor.draft"
)


def main():
    ap = argparse.ArgumentParser(description="1단: 무음 제거 점프컷 캡컷 드래프트 생성")
    ap.add_argument("video")
    ap.add_argument("--name", default="capcut_agent_test")
    ap.add_argument("--noise", type=float, default=-30.0)
    ap.add_argument("--min-silence", type=float, default=0.3)
    ap.add_argument("--min-keep", type=float, default=0.2)
    ap.add_argument("--draft-root", default=DRAFT_ROOT)
    args = ap.parse_args()

    info = probe_media(args.video)
    silences = detect_silence(args.video, args.noise, args.min_silence)
    keeps = compute_keep_segments(info["duration"], silences, args.min_keep)

    kept = sum(e - s for s, e in keeps)
    print(f"video      : {args.video}")
    print(f"resolution : {info['width']}x{info['height']} @ {info['fps']:.3f}fps")
    print(f"duration   : {info['duration']:.3f}s")
    print(f"silences   : {[(round(s,3), round(e,3) if e else None) for s,e in silences]}")
    print(f"keep segs  : {[(round(s,3), round(e,3)) for s,e in keeps]}")
    print(f"kept total : {kept:.3f}s  (cut {info['duration']-kept:.3f}s)")

    path = build_jumpcut_draft(
        args.video, args.name, keeps, args.draft_root,
        info["width"], info["height"], info["fps"],
    )
    print(f"draft      : {path}")


if __name__ == "__main__":
    main()
