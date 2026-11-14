"""Re-encode a video smaller and slower (OpenCV, mp4v), so the board spends no CPU decoding 1080p30.

python tools/prepare_video.py IN OUT [--height 720] [--fps 15]
"""
import argparse
import sys
from pathlib import Path

import cv2


def prepare(src: Path, dst: Path, height: int, fps: float) -> int:
    """Writes the copy and returns the number of frames written."""
    cap = cv2.VideoCapture(str(src))
    src_fps = cap.get(cv2.CAP_PROP_FPS)
    ok, frame = cap.read()
    if not ok or src_fps <= 0:
        raise ValueError(f"cannot read {src} as a video")
    src_h, src_w = frame.shape[:2]
    out_h = min(height, src_h) // 2 * 2  # never enlarge; mp4v wants even sizes
    out_w = round(src_w * out_h / src_h / 2) * 2
    dst.parent.mkdir(parents=True, exist_ok=True)
    writer = cv2.VideoWriter(str(dst), cv2.VideoWriter_fourcc(*"mp4v"), fps, (out_w, out_h))
    written, index = 0, 0
    while ok:
        # write this source frame as many times as output ticks fall before the next one
        while written / fps < (index + 1) / src_fps:
            writer.write(cv2.resize(frame, (out_w, out_h), interpolation=cv2.INTER_AREA))
            written += 1
        ok, frame = cap.read()
        index += 1
    writer.release()
    cap.release()
    return written


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(prog="prepare_video.py", description=__doc__)
    parser.add_argument("src", type=Path)
    parser.add_argument("dst", type=Path)
    parser.add_argument("--height", type=int, default=720)
    parser.add_argument("--fps", type=float, default=15)
    args = parser.parse_args(argv)
    try:
        frames = prepare(args.src, args.dst, args.height, args.fps)
    except ValueError as exc:
        print(f"error: {exc}", file=sys.stderr)
        return 1
    print(f"{args.dst}: {frames} frames, {frames / args.fps:.1f} s")
    return 0


if __name__ == "__main__":
    sys.exit(main())
