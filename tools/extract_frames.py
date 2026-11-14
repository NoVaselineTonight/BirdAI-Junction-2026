"""Cuts feeder videos into still frames, keeping the train/demo split.

    python tools/extract_frames.py --videos data/videos --out data/frames [--every 1.0] [--max-per-video 1500]

`<videos>/<train|demo>/**/<stem>.<ext>` becomes
`<out>/<split>/<stem>/<stem>_<milliseconds:08d>.jpg`.
"""

import argparse
import sys
from collections import defaultdict
from pathlib import Path

import cv2

SPLITS = ("train", "demo")
VIDEO_SUFFIXES = {".mp4", ".mov", ".avi", ".mkv", ".m4v"}


def extract_video(video: Path, out_dir: Path, every: float, max_frames: int) -> int:
    """Writes one frame per `every` seconds; returns how many were written."""
    cap = cv2.VideoCapture(str(video))
    if not cap.isOpened():
        print(f"warning: cannot open {video}", file=sys.stderr)
        return 0
    fps = cap.get(cv2.CAP_PROP_FPS) or 25.0
    total = cap.get(cv2.CAP_PROP_FRAME_COUNT)
    if total > 0:  # a long video is thinned out evenly instead of cut off after its first minutes
        every = max(every, total / fps / max_frames)
    out_dir.mkdir(parents=True, exist_ok=True)
    written, index = 0, 0
    while written < max_frames:
        ok, frame = cap.read()
        if not ok:
            break
        t = index / fps
        if t + 1e-6 >= written * every:
            cv2.imwrite(str(out_dir / f"{video.stem}_{round(t * 1000):08d}.jpg"), frame)
            written += 1
        index += 1
    cap.release()
    return written


def check_unique_stems(found: dict[str, list[Path]], root: Path) -> None:
    """Exits with code 2 if two videos share a stem: frame names and folders carry only the stem."""
    by_stem: dict[str, list[Path]] = defaultdict(list)
    for files in found.values():
        for video in files:
            by_stem[video.stem].append(video)
    clashes = {stem: files for stem, files in by_stem.items() if len(files) > 1}
    if clashes:
        lines = [f"  {stem}: " + ", ".join(v.relative_to(root).as_posix() for v in files)
                 for stem, files in sorted(clashes.items())]
        print("error: videos share a file name stem, so their frames would overwrite each other. "
              "Rename them so every stem is unique (train and demo included):\n" + "\n".join(lines),
              file=sys.stderr)
        raise SystemExit(2)


def main(argv: list[str] | None = None) -> None:
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--videos", type=Path, required=True)
    ap.add_argument("--out", type=Path, required=True)
    ap.add_argument("--every", type=float, default=1.0, help="seconds between frames")
    ap.add_argument("--max-per-video", type=int, default=1500)
    args = ap.parse_args(argv)

    found = {split: sorted(p for p in (args.videos / split).rglob("*") if p.suffix.lower() in VIDEO_SUFFIXES)
             for split in SPLITS}
    check_unique_stems(found, args.videos)

    total = 0
    for split, files in found.items():
        for video in files:
            n = extract_video(video, args.out / split / video.stem, args.every, args.max_per_video)
            print(f"{split}/{video.name}: {n} frames")
            total += n
    print(f"{total} frames in {args.out}")


if __name__ == "__main__":
    main()
