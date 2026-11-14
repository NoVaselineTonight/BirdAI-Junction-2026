"""Turn corrected teacher labels into a YOLO dataset for the student detector.

    python tools/build_dataset.py --labels data/labels/auto.jsonl --corrections data/review/corrections.csv \
        --frames data/frames --out data/dataset [--min-boxes 60]

Writes <out>/images/{train,val}/<frame stem>.jpg, <out>/labels/{train,val}/<frame stem>.txt (YOLO text
format), <out>/data.yaml and <out>/classes.json. `val` is exactly the `demo` footage, so a frame is never
split between the two. A species with fewer than --min-boxes training boxes becomes `unidentified`;
boxes labelled `drop` are removed (a frame left with no rows at all is left out of the dataset).
"""

import argparse
import csv
import json
import shutil
import sys
from collections import Counter
from collections.abc import Mapping
from typing import NoReturn
from pathlib import Path

import cv2

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))  # `python tools/build_dataset.py` has no repo root on the path

from feeder_census.species import load_species  # noqa: E402
from feeder_census.types import UNIDENTIFIED  # noqa: E402

DROP = "drop"
SPLIT_DIR = {"train": "train", "demo": "val"}


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
    args = ap.parse_args(argv)

    rows = [json.loads(line) for line in args.labels.read_text().splitlines() if line.strip()]
    corrections = _read_corrections(args.corrections)
    valid = {s.key for s in load_species()} | {UNIDENTIFIED, DROP}
    bad = sorted({label for label in corrections.values() if label not in valid})
    if bad:
        _fail(f"corrections.csv has labels that are not a species key, unidentified or drop: {', '.join(bad)}")
    rows = apply_corrections(rows, corrections)

    for r in rows:
        if r["split"] not in SPLIT_DIR:
            _fail(f"row {r['id']} has split {r['split']!r}; expected train or demo")
    if not any(r["split"] == "demo" for r in rows):
        _fail("no held-out footage: put the demo video in data/videos/demo")

    boxes = [r for r in rows if r["box"] is not None]
    train_counts = Counter(r["label"] for r in boxes if r["split"] == "train" and r["label"] != UNIDENTIFIED)
    classes = choose_classes(train_counts, args.min_boxes)
    if len(classes) < 3:
        listing = "\n".join(f"  {key}: {n}" for key, n in train_counts.most_common()) or "  (no species boxes)"
        _fail(f"fewer than two species have {args.min_boxes} training boxes; boxes per species in train:\n{listing}")
    index = {key: i for i, key in enumerate(classes)}

    by_frame: dict[str, list[dict]] = {}
    for r in rows:
        by_frame.setdefault(r["frame"], []).append(r)

    for sub in ("images", "labels"):
        shutil.rmtree(args.out / sub, ignore_errors=True)
    table: Counter = Counter()
    for frame, frame_rows in sorted(by_frame.items()):
        split = SPLIT_DIR[frame_rows[0]["split"]]
        stem = Path(frame).stem
        src = args.frames / frame
        image = cv2.imread(str(src))
        if image is None:
            _fail(f"cannot read frame {src}")
        height, width = image.shape[:2]
        lines = []
        for r in frame_rows:
            if r["box"] is None:
                continue
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
    names = "".join(f"  {i}: {key}\n" for i, key in enumerate(classes))
    (args.out / "data.yaml").write_text(
        f"path: {args.out.resolve()}\ntrain: images/train\nval: images/val\nnames:\n{names}")

    print(f"{'class':<28}{'train':>8}{'val':>8}")
    for key in classes:
        print(f"{key:<28}{table[key, 'train']:>8}{table[key, 'val']:>8}")


if __name__ == "__main__":
    main()
