"""Picks the frames worth labelling out of long, mostly empty feeder streams.

    python tools/mine_frames.py --videos data/videos --out data/frames [--every 1.0] \
        [--scan-model yolo26s.pt] [--scan-imgsz 960] [--scan-conf 0.15] [--min-gap-s 4.0] \
        [--empty-share 0.15] [--max-per-video 3000] [--workers N] \
        [--highlights OUT.mp4 --highlights-from STEM [--pad-s 2.0] [--max-highlights-s 900]]

Replaces extract_frames.py for footage where birds are rare. Pass 1 scans one downscaled sample
every `--every` seconds with a small YOLO and records how many birds each shows. The selection keeps
bird frames without piling up near-identical ones, plus a controlled share of empty frames. Pass 2
writes the kept frames at full resolution in the extract_frames layout,
`<out>/<split>/<stem>/<stem>_<milliseconds:08d>.jpg`, and `<out>/mining.csv` says what happened to
every sample. `--highlights` additionally cuts the busy parts of one video into a clip.

Decoding is the bottleneck: with ffmpeg on PATH it does the sampling, otherwise OpenCV is used.
Runs on the GPU machine under `uv run --group train`.
"""

import argparse
import csv
import math
import os
import shutil
import subprocess
import sys
import tempfile
from collections import deque
from collections.abc import Callable, Iterator
from concurrent.futures import ProcessPoolExecutor
from fractions import Fraction
from pathlib import Path
from typing import NamedTuple, NoReturn

import cv2

from extract_frames import SPLITS, VIDEO_SUFFIXES, check_unique_stems

COCO_BIRD = 14
FALLBACK_SCAN_MODEL = "yolo11s.pt"
SCAN_FLOOR = 0.05  # detections below this are not even reported; at or above it a miss is a "near-miss"
MIN_EMPTY = 20
BATCH = 32
JPEG_QUALITY = 92
CSV_COLUMNS = ["split", "video", "ms", "n_boxes", "max_conf", "kept", "reason"]

Sample = tuple[int, int, float]  # (ms, n_boxes, max_conf)


class Decision(NamedTuple):
    ms: int
    kept: bool
    reason: str


# Selection (pure) ------------------------------------------------------------------------------

def thin_evenly(items: list, k: int) -> list:
    """`k` items spread evenly over `items`, in order."""
    n = len(items)
    if k >= n:
        return list(items)
    return [items[(2 * i + 1) * n // (2 * k)] for i in range(k)]


def _walk_birds(birds: list[Sample], min_gap_ms: float) -> dict[int, str]:
    """ms -> reason for every bird sample (`bird`, `bird-count-changed` or `skipped-duplicate`)."""
    reasons: dict[int, str] = {}
    last_ms, last_n = None, None
    for ms, n, _ in birds:
        if last_ms is None or ms - last_ms >= min_gap_ms - 1e-6:
            reasons[ms] = "bird"
        elif n != last_n:
            reasons[ms] = "bird-count-changed"
        else:
            reasons[ms] = "skipped-duplicate"
            continue
        last_ms, last_n = ms, n
    return reasons


def _within_budget(kept: list[Sample], budget: int) -> list[Sample]:
    """Multi-bird samples first (thinned if they alone are too many), then single birds, evenly thinned."""
    if len(kept) <= budget:
        return kept
    multi = [s for s in kept if s[1] >= 2]
    if len(multi) >= budget:
        return thin_evenly(multi, budget)
    return multi + thin_evenly([s for s in kept if s[1] < 2], budget - len(multi))


def select_frames(samples: list[Sample], min_gap_s: float, empty_share: float, max_frames: int) -> list[Decision]:
    """Decides, for one video, which samples to keep; returns one Decision per sample in time order."""
    if not 0 <= empty_share < 1:
        raise ValueError(f"empty_share must be in [0, 1), got {empty_share}")
    samples = sorted(samples)
    birds = [s for s in samples if s[1] >= 1]
    walked = _walk_birds(birds, min_gap_s * 1000)
    kept_birds = _within_budget([s for s in birds if walked[s[0]] != "skipped-duplicate"],
                                math.floor(max_frames * (1 - empty_share) + 1e-9))
    reason = {ms: "skipped-duplicate" if walked[ms] == "skipped-duplicate" else "skipped-budget" for ms, *_ in birds}
    reason.update({ms: walked[ms] for ms, *_ in kept_birds})

    empties = [s for s in samples if s[1] == 0]
    target = max(round(len(kept_birds) * empty_share / (1 - empty_share)), min(MIN_EMPTY, len(empties)))
    near = sorted((s for s in empties if s[2] >= SCAN_FLOOR), key=lambda s: (-s[2], s[0]))
    plain = [s for s in empties if s[2] < SCAN_FLOOR]
    near_kept = near[:min(target // 2, len(near))]
    plain_kept = thin_evenly(plain, min(target - len(near_kept), len(plain)))
    reason.update({ms: "skipped-empty" for ms, *_ in empties})
    reason.update({ms: "near-miss" for ms, *_ in near_kept})
    reason.update({ms: "empty" for ms, *_ in plain_kept})

    return [Decision(s[0], not reason[s[0]].startswith("skipped"), reason[s[0]]) for s in samples]


def peak_boxes(samples: list[Sample], start_s: float, end_s: float) -> int:
    """The most birds any sample shows between `start_s` and `end_s`."""
    return max((n for ms, n, _ in samples if start_s <= ms / 1000 <= end_s), default=0)


def highlight_segments(samples: list[Sample], every_s: float, pad_s: float, max_total_s: float,
                       video_len_s: float) -> list[tuple[float, float]]:
    """Time segments around the bird samples, in time order, at most `max_total_s` long in all.

    Samples closer than 2 * pad + every are merged, each segment is padded by `pad_s` and clamped to
    the video. When the total would exceed the cap, segments with the highest peak bird count are
    taken first; a segment that does not fit is skipped (or trimmed if it is the first one taken).
    """
    times = sorted((ms, n) for ms, n, _ in samples if n >= 1)
    join_ms = round((2 * pad_s + every_s) * 1000)
    groups: list[list[tuple[int, int]]] = []
    for ms, n in times:
        if groups and ms - groups[-1][-1][0] < join_ms:
            groups[-1].append((ms, n))
        else:
            groups.append([(ms, n)])
    segments = [(max(0.0, g[0][0] / 1000 - pad_s), min(video_len_s, g[-1][0] / 1000 + pad_s), max(n for _, n in g))
                for g in groups]

    chosen: list[tuple[float, float]] = []
    remaining = max_total_s
    for start, end, _ in sorted(segments, key=lambda s: (-s[2], s[0])):
        length = end - start
        if length <= remaining + 1e-9:
            chosen.append((start, end))
            remaining -= length
        elif not chosen:
            chosen.append((start, start + remaining))
            remaining = 0.0
    return sorted(chosen)


# Pass 1: decode and scan -----------------------------------------------------------------------

def have_ffmpeg() -> bool:
    return shutil.which("ffmpeg") is not None


def _downscale(frame, long_side: int):
    h, w = frame.shape[:2]
    scale = long_side / max(h, w)
    if scale >= 1:
        return frame
    return cv2.resize(frame, (max(1, round(w * scale)), max(1, round(h * scale))), interpolation=cv2.INTER_AREA)


def decode_opencv(video: Path, every: float, imgsz: int, dest: Path) -> list[int]:
    """Writes one downscaled JPEG per `every` seconds as `dest/<n:08d>.jpg`; returns each one's ms."""
    cap = cv2.VideoCapture(str(video))
    if not cap.isOpened():
        return []
    fps = cap.get(cv2.CAP_PROP_FPS) or 25.0
    times: list[int] = []
    index = 0
    while True:
        t = index / fps
        if t + 1e-6 >= len(times) * every:
            ok, frame = cap.read()
            if not ok:
                break
            cv2.imwrite(str(dest / f"{len(times):08d}.jpg"), _downscale(frame, imgsz),
                        [cv2.IMWRITE_JPEG_QUALITY, 90])
            times.append(round(t * 1000))
        elif not cap.grab():  # skipped frames are decoded but never converted
            break
        index += 1
    cap.release()
    return times


def decode_ffmpeg(video: Path, every: float, imgsz: int, dest: Path) -> list[int]:
    """Same result as decode_opencv, with ffmpeg doing the sampling and scaling (much faster)."""
    rate = Fraction(1) / Fraction(every).limit_denominator(1000)
    scale = f"scale=w='min(iw,{imgsz})':h='min(ih,{imgsz})':force_original_aspect_ratio=decrease:force_divisible_by=2"
    cmd = ["ffmpeg", "-v", "error", "-nostdin", "-i", str(video), "-an", "-sn",
           "-vf", f"fps={rate.numerator}/{rate.denominator},{scale}",
           "-q:v", "3", "-start_number", "0", str(dest / "%08d.jpg")]
    done = subprocess.run(cmd, capture_output=True, text=True)
    count = len(list(dest.glob("*.jpg")))
    if done.returncode != 0:  # a live recording often has a damaged tail: keep what was decoded
        print(f"warning: ffmpeg reported errors on {video.name} after {count} samples: "
              f"{done.stderr.strip()[-300:]}", file=sys.stderr)
    return [round(i * every * 1000) for i in range(count)]


def decode_samples(video: Path, every: float, imgsz: int, dest: Path) -> list[int]:
    """Runs in a worker process. Falls back to OpenCV when ffmpeg is missing or produced nothing."""
    if have_ffmpeg():
        times = decode_ffmpeg(video, every, imgsz, dest)
        if times:
            return times
        for stale in dest.glob("*.jpg"):
            stale.unlink()
    return decode_opencv(video, every, imgsz, dest)


def decode_all(videos: list[tuple[str, Path]], workers: int, every: float, imgsz: int,
               scratch: Path) -> Iterator[tuple[str, Path, Path, list[int]]]:
    """Yields (split, video, temp dir, sample ms) in order; the caller removes each temp dir after use.

    Up to `workers` videos are decoded ahead of the one being scanned, so that many temp dirs exist at once.
    """
    made: list[Path] = []
    pool = ProcessPoolExecutor(workers) if workers > 1 else None
    queue: deque = deque()
    todo = iter(videos)
    try:
        while True:
            while len(queue) < workers and (item := next(todo, None)):
                tmp = Path(tempfile.mkdtemp(prefix=".scan_", dir=scratch))
                made.append(tmp)
                future = pool.submit(decode_samples, item[1], every, imgsz, tmp) if pool else None
                queue.append((*item, tmp, future))
            if not queue:
                return
            split, video, tmp, future = queue.popleft()
            times = future.result() if future else decode_samples(video, every, imgsz, tmp)
            yield split, video, tmp, times
    finally:
        if pool:
            pool.shutdown(wait=True, cancel_futures=True)
        for tmp in made:
            shutil.rmtree(tmp, ignore_errors=True)


def scan_samples(times: list[int], tmp: Path, scan_fn: Callable[[list], list[tuple[int, float]]]) -> list[Sample]:
    samples: list[Sample] = []
    for lo in range(0, len(times), BATCH):
        chunk = times[lo:lo + BATCH]
        frames = [cv2.imread(str(tmp / f"{lo + i:08d}.jpg")) for i in range(len(chunk))]
        samples += [(ms, int(n), float(conf)) for ms, (n, conf) in zip(chunk, scan_fn(frames))]
    return samples


def load_scan_fn(model_name: str, imgsz: int, conf: float) -> Callable[[list], list[tuple[int, float]]]:
    """The only place that imports ultralytics and torch. `scan_fn(frames) -> [(n_boxes, max_conf)]`."""
    import torch
    from ultralytics import YOLO

    try:
        model = YOLO(model_name)
    except Exception as err:
        print(f"cannot load {model_name} ({err}); using {FALLBACK_SCAN_MODEL}", file=sys.stderr)
        model = YOLO(FALLBACK_SCAN_MODEL)
    cuda = torch.cuda.is_available()
    if not cuda:
        print("warning: no CUDA GPU found, the scan runs on the CPU and will be slow", file=sys.stderr)

    def scan_fn(frames):
        results = model.predict(frames, classes=[COCO_BIRD], imgsz=imgsz, conf=SCAN_FLOOR,
                                device=0 if cuda else "cpu", half=cuda, verbose=False)
        out = []
        for result in results:
            confs = result.boxes.conf.cpu().numpy()
            out.append((int((confs >= conf).sum()), float(confs.max()) if len(confs) else 0.0))
        return out

    return scan_fn


# Pass 2 and the clip ---------------------------------------------------------------------------

def write_frames(video: Path, out_dir: Path, times_ms: list[int]) -> int:
    """Saves the frame at each millisecond, full resolution, one capture for the whole video."""
    cap = cv2.VideoCapture(str(video))
    if not cap.isOpened():
        print(f"warning: cannot open {video}", file=sys.stderr)
        return 0
    out_dir.mkdir(parents=True, exist_ok=True)
    written = 0
    for ms in sorted(times_ms):
        cap.set(cv2.CAP_PROP_POS_MSEC, ms)
        ok, frame = cap.read()
        if not ok:
            print(f"warning: no frame at {ms} ms in {video.name}", file=sys.stderr)
            continue
        cv2.imwrite(str(out_dir / f"{video.stem}_{ms:08d}.jpg"), frame, [cv2.IMWRITE_JPEG_QUALITY, JPEG_QUALITY])
        written += 1
    cap.release()
    return written


def video_length_s(video: Path, samples: list[Sample], every: float) -> float:
    cap = cv2.VideoCapture(str(video))
    frames, fps = cap.get(cv2.CAP_PROP_FRAME_COUNT), cap.get(cv2.CAP_PROP_FPS)
    cap.release()
    if frames > 0 and fps > 0:
        return frames / fps
    return max((ms for ms, *_ in samples), default=0) / 1000 + every


def write_highlights(video: Path, segments: list[tuple[float, float]], dest: Path) -> None:
    cap = cv2.VideoCapture(str(video))
    fps = cap.get(cv2.CAP_PROP_FPS) or 25.0
    size = (int(cap.get(cv2.CAP_PROP_FRAME_WIDTH)), int(cap.get(cv2.CAP_PROP_FRAME_HEIGHT)))
    writer = cv2.VideoWriter(str(dest), cv2.VideoWriter_fourcc(*"mp4v"), fps, size)
    for start, end in segments:
        cap.set(cv2.CAP_PROP_POS_MSEC, start * 1000)
        for _ in range(round((end - start) * fps)):
            ok, frame = cap.read()
            if not ok:
                break
            writer.write(frame)
    writer.release()
    cap.release()


# Command line ----------------------------------------------------------------------------------

def _fail(message: str) -> NoReturn:
    print(f"error: {message}", file=sys.stderr)
    raise SystemExit(2)


def _summary(label: str, scanned: int, with_birds: int, kept_birds: int, kept_empty: int) -> str:
    share = with_birds / scanned if scanned else 0.0
    return (f"{label}: {scanned} scanned, {with_birds} with birds ({share:.0%}), "
            f"kept {kept_birds} with birds + {kept_empty} empty")


def _parse(argv: list[str] | None) -> argparse.Namespace:
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--videos", type=Path, required=True)
    ap.add_argument("--out", type=Path, required=True)
    ap.add_argument("--every", type=float, default=1.0, help="seconds between scanned samples")
    ap.add_argument("--scan-model", default="yolo26s.pt")
    ap.add_argument("--scan-imgsz", type=int, default=960, help="long side of the scan samples")
    ap.add_argument("--scan-conf", type=float, default=0.15, help="confidence that counts a box as a bird")
    ap.add_argument("--min-gap-s", type=float, default=4.0)
    ap.add_argument("--empty-share", type=float, default=0.15)
    ap.add_argument("--max-per-video", type=int, default=3000)
    ap.add_argument("--workers", type=int, default=max(1, (os.cpu_count() or 2) // 2), help="decoding processes")
    ap.add_argument("--highlights", type=Path, help="write a clip of the busy parts to this .mp4")
    ap.add_argument("--highlights-from", metavar="STEM", help="the video the clip is cut from")
    ap.add_argument("--pad-s", type=float, default=2.0)
    ap.add_argument("--max-highlights-s", type=float, default=900.0)
    return ap.parse_args(argv)


def main(argv: list[str] | None = None, scan_fn: Callable[[list], list[tuple[int, float]]] | None = None) -> None:
    args = _parse(argv)
    found = {split: sorted(p for p in (args.videos / split).rglob("*") if p.suffix.lower() in VIDEO_SUFFIXES)
             for split in SPLITS}
    check_unique_stems(found, args.videos)
    videos = [(split, video) for split, files in found.items() for video in files]
    if not videos:
        _fail(f"no videos found under {args.videos}/train or {args.videos}/demo")
    if bool(args.highlights) != bool(args.highlights_from):
        _fail("--highlights and --highlights-from go together")
    if args.highlights_from and args.highlights_from not in {v.stem for _, v in videos}:
        _fail(f"--highlights-from {args.highlights_from!r} is not the stem of any video under {args.videos}")
    if not 0 <= args.empty_share < 1:
        _fail("--empty-share must be at least 0 and below 1")

    if scan_fn is None:
        scan_fn = load_scan_fn(args.scan_model, args.scan_imgsz, args.scan_conf)
    print(f"decoding with {'ffmpeg' if have_ffmpeg() else 'OpenCV (no ffmpeg on PATH, this is slow)'}")
    args.out.mkdir(parents=True, exist_ok=True)

    totals = [0, 0, 0, 0]
    highlight_source: tuple[Path, list[Sample]] | None = None
    with (args.out / "mining.csv").open("w", newline="") as f:
        table = csv.writer(f)
        table.writerow(CSV_COLUMNS)
        for split, video, tmp, times in decode_all(videos, max(1, args.workers), args.every, args.scan_imgsz, args.out):
            try:
                samples = scan_samples(times, tmp, scan_fn)
            finally:
                shutil.rmtree(tmp, ignore_errors=True)
            if not samples:
                print(f"warning: no samples from {video}", file=sys.stderr)
                continue
            decisions = select_frames(samples, args.min_gap_s, args.empty_share, args.max_per_video)
            write_frames(video, args.out / split / video.stem, [d.ms for d in decisions if d.kept])
            table.writerows([split, video.stem, s[0], s[1], f"{s[2]:.4f}", d.kept, d.reason]
                            for s, d in zip(sorted(samples), decisions))
            f.flush()
            counts = [len(samples), sum(s[1] >= 1 for s in samples),
                      sum(d.kept and d.reason.startswith("bird") for d in decisions),
                      sum(d.kept and d.reason in ("empty", "near-miss") for d in decisions)]
            print(_summary(f"{split}/{video.name}", *counts))
            totals = [a + b for a, b in zip(totals, counts)]
            if video.stem == args.highlights_from:
                highlight_source = (video, samples)
    print(_summary("total", *totals))
    print(f"{totals[2] + totals[3]} frames in {args.out}")

    if args.highlights and highlight_source:
        video, samples = highlight_source
        segments = highlight_segments(samples, args.every, args.pad_s, args.max_highlights_s,
                                      video_length_s(video, samples, args.every))
        write_highlights(video, segments, args.highlights)
        with Path(f"{args.highlights}.segments.csv").open("w", newline="") as f:
            table = csv.writer(f)
            table.writerow(["start_s", "end_s", "peak_boxes"])
            for start, end in segments:
                peak = peak_boxes(samples, start, end)
                table.writerow([start, end, peak])
                print(f"highlight {start:.1f}-{end:.1f} s (peak {peak} birds)")
        print(f"highlights: {len(segments)} segments, {sum(e - s for s, e in segments):.1f} s in {args.highlights}")


if __name__ == "__main__":
    main()
