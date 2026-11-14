"""Turn corrected teacher labels into a YOLO dataset for the student detector.

    python tools/build_dataset.py --labels data/labels/auto.jsonl --corrections data/review/corrections.csv \
        --frames data/frames --out data/dataset [--min-boxes 60] [--val-fraction 0.15]

Writes <out>/images/{train,val,test}/<frame stem>.jpg, <out>/labels/{train,val,test}/<frame stem>.txt (YOLO
text format), <out>/data.yaml, <out>/classes.json and <out>/split.json. `test` is exactly the `demo`
footage: nothing about training or model selection may read it. `val` is the last --val-fraction of each
training video (a contiguous tail, since neighbouring frames are near-duplicates; videos under 10 frames
stay whole in `train`), used for early stopping and picking the checkpoint. `train` is the rest, so a
frame is never split between sets. A species with fewer than --min-boxes boxes in the training footage
becomes `unidentified`; boxes labelled `drop` are removed, and a frame left with no boxes stays as an
empty-label negative.
"""

import argparse
import csv
import json
import math
import shutil
import sys
from collections import Counter
from collections.abc import Mapping
from pathlib import Path
from typing import NoReturn

import cv2

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))  # `python tools/build_dataset.py` has no repo root on the path

from feeder_census.species import load_species  # noqa: E402
from feeder_census.types import UNIDENTIFIED  # noqa: E402

DROP = "drop"
MIN_FRAMES_FOR_VAL = 10


def choose_classes(train_counts: Mapping[str, int], min_boxes: int = 60) -> list[str]:
    """Species with at least `min_boxes` training boxes, most frequent first, then `unidentified`."""
    species = [(key, n) for key, n in train_counts.items() if key != UNIDENTIFIED and n >= min_boxes]
    species.sort(key=lambda item: (-item[1], item[0]))
    return [key for key, _ in species] + [UNIDENTIFIED]


def apply_corrections(rows: list[dict], corrections: Mapping[str, str]) -> list[dict]:
    """Relabel rows by id; `drop` removes a row. Corrected rows get status `corrected`."""
    known = {r["id"] for r in rows}
    for row_id in corrections:
        if row_id not in known:
            print(f"warning: correction for {row_id!r} matches no label row", file=sys.stderr)
    out = []
    for r in rows:
        label = corrections.get(r["id"])
        if label == DROP:
            continue
        out.append({**r, "label": label, "status": "corrected"} if label is not None else dict(r))
    return out


def carve_validation(frames: Mapping[str, str], fraction: float) -> dict[str, str]:
    """Maps each frame (path relative to the frames dir) to `train`, `val` or `test`.

    `frames` maps a frame to its footage split, `train` or `demo`. The last `ceil(fraction * n)` frames
    of every training video with at least MIN_FRAMES_FOR_VAL frames, in the order of the millisecond in
    the frame stem, go to `val`; demo frames go to `test`.
    """
    where = {frame: "test" for frame, split in frames.items() if split == "demo"}
    by_video: dict[str, list[str]] = {}
    for frame, split in frames.items():
        if split == "train":
            by_video.setdefault(Path(frame).parent.name, []).append(frame)
    for video_frames in by_video.values():
        video_frames.sort(key=lambda f: int(Path(f).stem.rsplit("_", 1)[1]))
        n_val = math.ceil(round(len(video_frames) * fraction, 9)) if len(video_frames) >= MIN_FRAMES_FOR_VAL else 0
        for i, frame in enumerate(video_frames):
            where[frame] = "val" if i >= len(video_frames) - n_val else "train"
    return where


def _fail(message: str) -> NoReturn:
    print(f"error: {message}", file=sys.stderr)
    raise SystemExit(2)


def _read_corrections(path: Path) -> dict[str, str]:
    with open(path, newline="") as f:
        return {r["id"]: r["label"].strip() for r in csv.DictReader(f) if r["label"].strip()}


def _yolo_line(class_id: int, box: list[float], width: int, height: int) -> str | None:
    x1, y1 = max(box[0], 0.0), max(box[1], 0.0)
    x2, y2 = min(box[2], float(width)), min(box[3], float(height))
    if x2 <= x1 or y2 <= y1:
        return None
    return (f"{class_id} {(x1 + x2) / 2 / width:.6f} {(y1 + y2) / 2 / height:.6f} "
            f"{(x2 - x1) / width:.6f} {(y2 - y1) / height:.6f}")


def main(argv: list[str] | None = None) -> None:
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--labels", type=Path, required=True)
    ap.add_argument("--corrections", type=Path, required=True)
    ap.add_argument("--frames", type=Path, required=True)
    ap.add_argument("--out", type=Path, required=True)
    ap.add_argument("--min-boxes", type=int, default=60)
    ap.add_argument("--val-fraction", type=float, default=0.15)
    args = ap.parse_args(argv)
    if not 0 < args.val_fraction < 1:
        ap.error("--val-fraction must be between 0 and 1")

    all_rows = [json.loads(line) for line in args.labels.read_text().splitlines() if line.strip()]
    corrections = _read_corrections(args.corrections)
    valid = {s.key for s in load_species()} | {UNIDENTIFIED, DROP}
    bad = sorted({label for label in corrections.values() if label not in valid})
    if bad:
        _fail(f"corrections.csv has labels that are not a species key, unidentified or drop: {', '.join(bad)}")

    frame_split: dict[str, str] = {}  # every frame that has any row, before `drop` removes boxes
    for r in all_rows:
        if r["split"] not in ("train", "demo"):
            _fail(f"row {r['id']} has split {r['split']!r}; expected train or demo")
        frame_split[r["frame"]] = r["split"]
    rows = apply_corrections(all_rows, corrections)

    if "demo" not in frame_split.values():
        _fail("no held-out footage: put the demo video in data/videos/demo")

    # Classes come from all training footage, before `val` is carved out of it.
    boxes = [r for r in rows if r["box"] is not None]
    train_counts = Counter(r["label"] for r in boxes if r["split"] == "train" and r["label"] != UNIDENTIFIED)
    classes = choose_classes(train_counts, args.min_boxes)
    if len(classes) < 3:
        listing = "\n".join(f"  {key}: {n}" for key, n in train_counts.most_common()) or "  (no species boxes)"
        _fail(f"fewer than two species have {args.min_boxes} training boxes; boxes per species in train:\n{listing}")
    index = {key: i for i, key in enumerate(classes)}

    where = carve_validation(frame_split, args.val_fraction)
    if "val" not in where.values():
        _fail("no validation frames: training videos are too short to hold some back")

    by_frame: dict[str, list[dict]] = {}
    for r in boxes:
        by_frame.setdefault(r["frame"], []).append(r)

    for sub in ("images", "labels"):
        shutil.rmtree(args.out / sub, ignore_errors=True)
    table: Counter = Counter()
    for frame, split in sorted(where.items()):
        stem = Path(frame).stem
        src = args.frames / frame
        image = cv2.imread(str(src))
        if image is None:
            _fail(f"cannot read frame {src}")
        height, width = image.shape[:2]
        lines = []
        for r in by_frame.get(frame, []):
            key = r["label"] if r["label"] in index else UNIDENTIFIED
            line = _yolo_line(index[key], r["box"], width, height)
            if line is not None:
                lines.append(line)
                table[key, split] += 1
        (args.out / "images" / split).mkdir(parents=True, exist_ok=True)
        (args.out / "labels" / split).mkdir(parents=True, exist_ok=True)
        shutil.copyfile(src, args.out / "images" / split / f"{stem}.jpg")
        (args.out / "labels" / split / f"{stem}.txt").write_text("".join(line + "\n" for line in lines))

    (args.out / "classes.json").write_text(json.dumps(classes))
    (args.out / "split.json").write_text(
        json.dumps({"val_fraction": args.val_fraction, "min_frames": MIN_FRAMES_FOR_VAL}))
    names = "".join(f"  {i}: {key}\n" for i, key in enumerate(classes))
    (args.out / "data.yaml").write_text(
        f"path: {args.out.resolve()}\ntrain: images/train\nval: images/val\ntest: images/test\nnames:\n{names}")

    print(f"{'class':<28}{'train':>8}{'val':>8}{'test':>8}")
    for key in classes:
        print(f"{key:<28}{table[key, 'train']:>8}{table[key, 'val']:>8}{table[key, 'test']:>8}")


if __name__ == "__main__":
    main()
