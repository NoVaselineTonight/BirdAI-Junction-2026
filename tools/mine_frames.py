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

Decoding is the bottleneck: with ffmpeg on PATH it does the sampling (and reads the kept frames by
timestamp in pass 2), otherwise OpenCV is used for both passes (by frame index). ffmpeg is never
silently replaced by OpenCV: a failing ffmpeg stops the run (exit 2 for a failed self-test on the
first video) or fails that video (exit 1 at the end). Pass 2 is checked: up to five kept samples per
video are compared with their saved frame (`check_diff` in mining.csv); a frame that cannot be
written is recorded as `write-failed`, an unreadable scan image as `unreadable`.
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
from concurrent.futures import Future, ProcessPoolExecutor
from concurrent.futures.process import BrokenProcessPool
from fractions import Fraction
from functools import partial
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
MAX_POOL_REBUILDS = 3  # dead worker pools replaced per run before the run gives up
CHECK_SAMPLES = 5  # kept samples per video compared with their saved frame
CHECK_THRESHOLD = 12.0  # mean absolute pixel difference (0 to 255) above which a saved frame is not the scanned one
CSV_COLUMNS = ["split", "video", "ms", "n_boxes", "max_conf", "kept", "reason", "check_diff"]

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
    short = target - len(near_kept) - len(plain_kept)  # not enough plain empties: more near-misses make up for it
    near_kept += near[len(near_kept):len(near_kept) + short]
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


# Frame index and millisecond: the one place the two conventions meet -------------------------------

def frame_to_ms(index: int, fps: float) -> int:
    """Time of a frame, as the millisecond used in sample and file names (OpenCV mode)."""
    return round(index / fps * 1000)


def ms_to_frame(ms: int, fps: float) -> int:
    """The frame a sample named `ms` stands for. Exact inverse of `frame_to_ms` below ~1000 fps."""
    return round(ms * fps / 1000)


def check_times(kept_ms: list[int], n: int = CHECK_SAMPLES) -> list[int]:
    """Up to `n` of the kept times: the first, the last and the rest spread between them."""
    if len(kept_ms) <= n:
        return list(kept_ms)
    return [kept_ms[i * (len(kept_ms) - 1) // (n - 1)] for i in range(n)]


def frames_match(saved, scanned) -> float:
    """Mean absolute pixel difference (0 to 255) after shrinking `saved` to the size of `scanned`."""
    small = cv2.resize(saved, (scanned.shape[1], scanned.shape[0]), interpolation=cv2.INTER_AREA)
    return float(cv2.absdiff(small, scanned).mean())


def frame_path(out_dir: Path, stem: str, ms: int) -> Path:
    return out_dir / f"{stem}_{ms:08d}.jpg"


# Pass 1: decode and scan -----------------------------------------------------------------------

def have_ffmpeg() -> bool:
    return shutil.which("ffmpeg") is not None


def _tail(text: str) -> str:
    return " | ".join(text.strip().splitlines()[-4:])[-400:]


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
        if index / fps + 1e-6 >= len(times) * every:
            ok, frame = cap.read()
            if not ok:
                break
            cv2.imwrite(str(dest / f"{len(times):08d}.jpg"), _downscale(frame, imgsz), [cv2.IMWRITE_JPEG_QUALITY, 90])
            times.append(frame_to_ms(index, fps))
        elif not cap.grab():  # skipped frames are decoded but never converted
            break
        index += 1
    cap.release()
    return times


def ffmpeg_command(video: Path, every: float, imgsz: int, dest: Path, limit_s: float | None = None) -> list[str]:
    """One sample every `every` seconds, long side at most `imgsz` (the other side -2: even, same aspect)."""
    rate = Fraction(1) / Fraction(every).limit_denominator(1000)
    scale = f"scale=w='if(gt(iw,ih),min(iw,{imgsz}),-2)':h='if(gt(iw,ih),-2,min(ih,{imgsz}))'"
    cmd = ["ffmpeg", "-v", "error", "-nostdin", "-threads", "2", "-i", str(video), "-an", "-sn"]
    if limit_s:
        cmd += ["-t", str(limit_s)]
    return cmd + ["-vf", f"fps={rate.numerator}/{rate.denominator},{scale}", "-q:v", "3", "-start_number", "0",
                  str(dest / "%08d.jpg")]


def ffmpeg_selftest(video: Path, every: float, imgsz: int) -> str | None:
    """Runs the exact filter chain on the first two seconds of `video`; returns ffmpeg's complaint or None."""
    with tempfile.TemporaryDirectory() as tmp:
        try:
            done = subprocess.run(ffmpeg_command(video, every, imgsz, Path(tmp), limit_s=2), capture_output=True,
                                  text=True, timeout=120)
        except (OSError, subprocess.TimeoutExpired) as err:
            return str(err)
        if done.returncode != 0 or not list(Path(tmp).glob("*.jpg")):
            return _tail(done.stderr) or f"exit {done.returncode}, no sample written"
    return None


def decode_ffmpeg(video: Path, every: float, imgsz: int, dest: Path) -> list[int]:
    """Same result as decode_opencv with ffmpeg sampling by timestamp (much faster). Raises when it fails."""
    timeout = max(600.0, 10 * video_length_s(video, [], 0.0))
    try:
        done = subprocess.run(ffmpeg_command(video, every, imgsz, dest), capture_output=True, text=True,
                              timeout=timeout)
    except subprocess.TimeoutExpired:
        raise RuntimeError(f"ffmpeg did not finish within {timeout:.0f} s") from None
    count = len(list(dest.glob("*.jpg")))
    if done.returncode != 0 or count == 0:
        raise RuntimeError(f"ffmpeg failed (exit {done.returncode}, {count} samples): {_tail(done.stderr)}")
    return [round(i * every * 1000) for i in range(count)]


def decode_samples(video: Path, every: float, imgsz: int, dest: Path, use_ffmpeg: bool) -> list[int]:
    """Runs in a worker process. ffmpeg failures are errors; OpenCV is used only when ffmpeg is absent."""
    return decode_ffmpeg(video, every, imgsz, dest) if use_ffmpeg else decode_opencv(video, every, imgsz, dest)


class Runner:
    """Runs functions in a process pool, or inline for one worker. Always hands back a Future.

    A worker that dies (an OOM kill) breaks the whole pool: the futures of that pool fail with
    BrokenProcessPool, and the next `submit` replaces the dead pool with a fresh one. After
    `max_rebuilds` replacements it stops submitting and every new task fails with "worker pool kept dying".
    """

    def __init__(self, workers: int, max_rebuilds: int = MAX_POOL_REBUILDS):
        self.workers, self.max_rebuilds, self.rebuilds = workers, max_rebuilds, 0
        self.pool = ProcessPoolExecutor(workers) if workers > 1 else None
        self.broken = False
        self.gave_up = False

    def submit(self, fn, *args) -> Future:
        future: Future = Future()
        if self.pool is None:
            try:
                future.set_result(fn(*args))
            except Exception as err:
                future.set_exception(err)
            return future
        while True:
            if self.broken and not self._rebuild():
                future.set_exception(RuntimeError("worker pool kept dying"))
                return future
            try:
                future = self.pool.submit(fn, *args)
            except BrokenProcessPool:
                self.broken = True
                continue
            future.add_done_callback(partial(self._watch, self.pool))
            return future

    def _watch(self, pool, future: Future) -> None:
        if not future.cancelled() and isinstance(future.exception(), BrokenProcessPool) and pool is self.pool:
            self.broken = True

    def _rebuild(self) -> bool:
        if self.gave_up or self.rebuilds >= self.max_rebuilds:
            self.gave_up = True
            return False
        self.rebuilds += 1
        print(f"warning: a worker process died; starting a new pool ({self.rebuilds}/{self.max_rebuilds})",
              file=sys.stderr)
        self.pool.shutdown(wait=True, cancel_futures=True)
        self.pool = ProcessPoolExecutor(self.workers)
        self.broken = False
        return True

    def close(self) -> None:
        if self.pool:
            self.pool.shutdown(wait=True, cancel_futures=True)


def decode_all(videos: list[tuple[str, Path]], runner: Runner, workers: int, every: float, imgsz: int,
               scratch: Path, use_ffmpeg: bool) -> Iterator[tuple[str, Path, Path, Future]]:
    """Yields (split, video, temp dir, future of the sample ms) in order; the caller removes each temp dir.

    Up to `workers` videos are decoded ahead of the one being scanned, so that many temp dirs exist at once.
    """
    made: list[Path] = []
    queue: deque = deque()
    todo = iter(videos)
    try:
        while True:
            while len(queue) < workers and (item := next(todo, None)):
                tmp = Path(tempfile.mkdtemp(prefix=".scan_", dir=scratch))
                made.append(tmp)
                queue.append((*item, tmp, runner.submit(decode_samples, item[1], every, imgsz, tmp, use_ffmpeg)))
            if not queue:
                return
            yield queue.popleft()
    finally:
        for tmp in made:
            shutil.rmtree(tmp, ignore_errors=True)


def scan_samples(times: list[int], tmp: Path, scan_fn: Callable[[list], list[tuple[int, float]]]
                 ) -> tuple[list[Sample], list[int]]:
    """Scans the sample images; returns the samples and the ms of images that could not be read."""
    samples: list[Sample] = []
    unreadable: list[int] = []
    for lo in range(0, len(times), BATCH):
        chunk = [(ms, cv2.imread(str(tmp / f"{lo + i:08d}.jpg"))) for i, ms in enumerate(times[lo:lo + BATCH])]
        unreadable += [ms for ms, img in chunk if img is None]
        good = [(ms, img) for ms, img in chunk if img is not None]
        if good:
            samples += [(ms, int(n), float(conf)) for (ms, _), (n, conf) in zip(good, scan_fn([img for _, img in good]))]
    return samples, unreadable


def scan_images(tmp: Path, times: list[int], decisions: list[Decision]) -> dict[int, object]:
    """The scan-size images of the kept samples that pass 2 will be checked against."""
    index = {ms: i for i, ms in enumerate(times)}
    images = {ms: cv2.imread(str(tmp / f"{index[ms]:08d}.jpg")) for ms in check_times([d.ms for d in decisions if d.kept])}
    return {ms: img for ms, img in images.items() if img is not None}


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

def _frames_opencv(video: Path, out_dir: Path, times_ms: list[int]) -> list[int]:
    cap = cv2.VideoCapture(str(video))
    if not cap.isOpened():
        print(f"warning: cannot open {video}", file=sys.stderr)
        return []
    fps = cap.get(cv2.CAP_PROP_FPS) or 25.0
    written = []
    for ms in sorted(times_ms):
        cap.set(cv2.CAP_PROP_POS_FRAMES, ms_to_frame(ms, fps))  # pass 1 chose these by frame index
        ok, frame = cap.read()
        if ok and cv2.imwrite(str(frame_path(out_dir, video.stem, ms)), frame, [cv2.IMWRITE_JPEG_QUALITY, JPEG_QUALITY]):
            written.append(ms)
        else:
            print(f"warning: no frame at {ms} ms in {video.name}", file=sys.stderr)
    cap.release()
    return written


def _frames_ffmpeg(video: Path, out_dir: Path, times_ms: list[int]) -> list[int]:
    written = []
    for ms in sorted(times_ms):  # pass 1 chose these by timestamp, so ffmpeg seeks by timestamp too
        target = frame_path(out_dir, video.stem, ms)
        cmd = ["ffmpeg", "-v", "error", "-nostdin", "-y", "-threads", "2", "-ss", f"{ms / 1000:.3f}", "-i", str(video),
               "-frames:v", "1", "-q:v", "2", str(target)]
        try:
            done = subprocess.run(cmd, capture_output=True, text=True, timeout=300)
        except subprocess.TimeoutExpired:
            print(f"warning: ffmpeg timed out at {ms} ms in {video.name}", file=sys.stderr)
            continue
        if done.returncode == 0 and target.exists():
            written.append(ms)
        else:
            print(f"warning: no frame at {ms} ms in {video.name}: {_tail(done.stderr)}", file=sys.stderr)
    return written


def write_frames(video: Path, out_dir: Path, times_ms: list[int], use_ffmpeg: bool = False) -> list[int]:
    """Saves the frame at each time at full resolution with the decoder pass 1 used; returns the ms written."""
    out_dir.mkdir(parents=True, exist_ok=True)
    return (_frames_ffmpeg if use_ffmpeg else _frames_opencv)(video, out_dir, times_ms)


def video_length_s(video: Path, samples: list[Sample], every: float) -> float:
    cap = cv2.VideoCapture(str(video))
    frames, fps = cap.get(cv2.CAP_PROP_FRAME_COUNT), cap.get(cv2.CAP_PROP_FPS)
    cap.release()
    if frames > 0 and fps > 0:
        return frames / fps
    return max((ms for ms, *_ in samples), default=0) / 1000 + every if samples else 0.0


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


def _summary(label: str, counts: list[int]) -> str:
    scanned, with_birds, kept_birds, kept_empty, write_failed, unreadable = counts
    share = with_birds / scanned if scanned else 0.0
    text = (f"{label}: {scanned} scanned, {with_birds} with birds ({share:.0%}), "
            f"kept {kept_birds} with birds + {kept_empty} empty")
    if write_failed or unreadable:
        text += f", {write_failed} write-failed, {unreadable} unreadable"
    return text


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


def _validate(args: argparse.Namespace, videos: list[tuple[str, Path]]) -> None:
    if not videos:
        _fail(f"no videos found under {args.videos}/train or {args.videos}/demo")
    if bool(args.highlights) != bool(args.highlights_from):
        _fail("--highlights and --highlights-from go together")
    if args.highlights_from and args.highlights_from not in {v.stem for _, v in videos}:
        _fail(f"--highlights-from {args.highlights_from!r} is not the stem of any video under {args.videos}")
    if not 0 <= args.empty_share < 1:
        _fail("--empty-share must be at least 0 and below 1")
    for flag, value in (("--every", args.every), ("--scan-imgsz", args.scan_imgsz),
                        ("--max-per-video", args.max_per_video)):
        if value <= 0:
            _fail(f"{flag} must be positive, got {value}")


class Pending(NamedTuple):
    """A video whose frames are being written (pass 2) and whose rows are not yet in mining.csv."""
    split: str
    video: Path
    samples: list[Sample]
    unreadable: list[int]
    decisions: list[Decision]
    writes: list[Future]
    checks: dict[int, object]


def finish_video(p: Pending, out: Path, table, failures: list[tuple[str, str]]) -> list[int]:
    """Waits for the pass-2 writes, verifies them, writes the CSV rows; returns the summary counts."""
    label = f"{p.split}/{p.video.name}"

    def fail(message: str) -> None:
        failures.append((label, message))
        print(f"error: {label}: {message}", file=sys.stderr)

    written: set[int] = set()
    for future in p.writes:
        try:
            written.update(future.result())
        except Exception as err:
            fail(f"writing frames failed: {err}")
    diffs: dict[int, float] = {}
    for ms, scanned in p.checks.items():
        saved = cv2.imread(str(frame_path(out / p.split / p.video.stem, p.video.stem, ms))) if ms in written else None
        if saved is None:
            written.discard(ms)
        else:
            diffs[ms] = frames_match(saved, scanned)
    decisions = [d if not d.kept or d.ms in written else Decision(d.ms, False, "write-failed") for d in p.decisions]
    bad = sorted(ms for ms, diff in diffs.items() if diff > CHECK_THRESHOLD)
    if len(bad) > 1:
        fail(f"the saved frames do not match the scanned samples (mean difference above {CHECK_THRESHOLD} at "
             f"{', '.join(map(str, bad))} ms): pass 2 is not reading the frames that were scanned")
    lost = [d.ms for d in decisions if d.reason == "write-failed"]
    if lost:
        fail(f"{len(lost)} frames could not be written (see the write-failed rows in mining.csv)")

    rows = [(s[0], [p.split, p.video.stem, s[0], s[1], f"{s[2]:.4f}", d.kept, d.reason,
                    f"{diffs[s[0]]:.2f}" if s[0] in diffs else ""]) for s, d in zip(sorted(p.samples), decisions)]
    rows += [(ms, [p.split, p.video.stem, ms, 0, "0.0000", False, "unreadable", ""]) for ms in p.unreadable]
    table.writerows(row for _, row in sorted(rows, key=lambda r: r[0]))
    counts = [len(p.samples), sum(s[1] >= 1 for s in p.samples),
              sum(d.kept and d.reason.startswith("bird") for d in decisions),
              sum(d.kept and d.reason in ("empty", "near-miss") for d in decisions), len(lost), len(p.unreadable)]
    print(_summary(label, counts))
    return counts


def main(argv: list[str] | None = None, scan_fn: Callable[[list], list[tuple[int, float]]] | None = None) -> None:
    args = _parse(argv)
    found = {split: sorted(p for p in (args.videos / split).rglob("*") if p.suffix.lower() in VIDEO_SUFFIXES)
             for split in SPLITS}
    check_unique_stems(found, args.videos)
    videos = [(split, video) for split, files in found.items() for video in files]
    _validate(args, videos)

    use_ffmpeg = have_ffmpeg()
    if use_ffmpeg:
        problem = ffmpeg_selftest(videos[0][1], args.every, args.scan_imgsz)
        if problem:
            _fail(f"ffmpeg cannot sample {videos[0][1]}: {problem}\n(is this ffmpeg too old or broken? the sampling "
                  "filter chain is fps + scale with if/min expressions; try a current ffmpeg)")
    if scan_fn is None:
        scan_fn = load_scan_fn(args.scan_model, args.scan_imgsz, args.scan_conf)
    print(f"decoding with {'ffmpeg' if use_ffmpeg else 'OpenCV (no ffmpeg on PATH, this is slow)'}")
    args.out.mkdir(parents=True, exist_ok=True)

    workers = max(1, args.workers)
    totals = [0] * 6
    failures: list[tuple[str, str]] = []
    highlight_source: tuple[Path, list[Sample]] | None = None
    pending: deque[Pending] = deque()
    runner = Runner(workers)
    decoded = decode_all(videos, runner, workers, args.every, args.scan_imgsz, args.out, use_ffmpeg)
    with (args.out / "mining.csv").open("w", newline="") as f:
        table = csv.writer(f)
        table.writerow(CSV_COLUMNS)

        def finish(p: Pending) -> None:
            nonlocal totals, highlight_source
            try:
                counts = finish_video(p, args.out, table, failures)
            except Exception as err:
                failures.append((f"{p.split}/{p.video.name}", f"finishing the video failed: {err}"))
                print(f"error: {p.split}/{p.video.name}: finishing the video failed: {err}", file=sys.stderr)
                return
            totals = [a + b for a, b in zip(totals, counts)]
            f.flush()
            if p.video.stem == args.highlights_from:
                highlight_source = (p.video, p.samples)

        try:
            for split, video, tmp, future in decoded:
                try:
                    times = future.result()
                    samples, unreadable = scan_samples(times, tmp, scan_fn)
                    if not samples:
                        raise RuntimeError("no sample could be decoded and read")
                    decisions = select_frames(samples, args.min_gap_s, args.empty_share, args.max_per_video)
                    checks = scan_images(tmp, times, decisions)
                except Exception as err:
                    failures.append((f"{split}/{video.name}", str(err)))
                    print(f"error: {split}/{video.name}: {err}", file=sys.stderr)
                    continue
                finally:
                    shutil.rmtree(tmp, ignore_errors=True)
                kept = [d.ms for d in decisions if d.kept]
                size = 50 if use_ffmpeg else max(1, len(kept))  # one ffmpeg process per frame, chunks fill the pool
                writes = [runner.submit(write_frames, video, args.out / split / video.stem, kept[i:i + size], use_ffmpeg)
                          for i in range(0, len(kept), size)]
                pending.append(Pending(split, video, samples, unreadable, decisions, writes, checks))
                while len(pending) > workers:
                    finish(pending.popleft())
            while pending:
                finish(pending.popleft())
        finally:
            runner.close()
            decoded.close()
    print(_summary("total", totals))
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
    if args.highlights and not highlight_source:
        print(f"warning: no highlights clip, {args.highlights_from} was not mined successfully", file=sys.stderr)
    if failures:
        print(f"{len(failures)} problem(s), exit 1:", file=sys.stderr)
        for label, message in failures:
            print(f"  {label}: {message}", file=sys.stderr)
        raise SystemExit(1)


if __name__ == "__main__":
    main()
