"""Time a detector on frames spread evenly through a video.

python -m feeder_census.bench --detector two_stage --video clip.mp4 [--frames 30]
"""
import argparse
import sys
import time
from pathlib import Path

import cv2
import numpy as np

from feeder_census.detectors import KINDS, build_detector
from feeder_census.species import load_species


def read_frames(video: Path, count: int) -> list[np.ndarray]:
    cap = cv2.VideoCapture(str(video))
    total = int(cap.get(cv2.CAP_PROP_FRAME_COUNT))
    frames = []
    for index in np.linspace(0, max(total - 1, 0), count).astype(int):
        cap.set(cv2.CAP_PROP_POS_FRAMES, int(index))
        ok, frame = cap.read()
        if ok:
            frames.append(frame)
    cap.release()
    return frames


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(prog="python -m feeder_census.bench")
    parser.add_argument("--detector", required=True, choices=KINDS)
    parser.add_argument("--video", required=True, type=Path)
    parser.add_argument("--frames", type=int, default=30)
    parser.add_argument("--models-dir", type=Path, default=Path("models"))
    parser.add_argument("--student-dir", type=Path, default=None)
    args = parser.parse_args(argv)

    frames = read_frames(args.video, args.frames)
    if not frames:
        print(f"no frames could be read from {args.video}", file=sys.stderr)
        return 1
    detector = build_detector(
        args.detector, args.models_dir, load_species(), student_dir=args.student_dir
    )
    detector.detect(frames[0])  # warm-up, not timed
    times_ms, birds = [], []
    for frame in frames:
        start = time.perf_counter()
        found = detector.detect(frame)
        times_ms.append((time.perf_counter() - start) * 1000)
        birds.append(len(found))
    print(f"median_ms: {np.median(times_ms):.1f}")
    print(f"p90_ms: {np.percentile(times_ms, 90):.1f}")
    print(f"birds_per_frame: {np.mean(birds):.1f}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
