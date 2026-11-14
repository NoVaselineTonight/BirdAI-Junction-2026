"""Contact sheets for checking the teacher labels by eye.

    python tools/review_sheets.py --labels data/labels/auto.jsonl --frames data/frames --out data/review

Writes `<out>/<label>/<label>_<NN>.jpg` (48 crops each, 8 x 6, every crop 160 px with its row
number printed on it), `<out>/index.csv` (n,id,label,status,bioclip,inat; n counts per label and
matches the number on the crop) and, if missing, `<out>/corrections.csv` with the header `id,label`.
"""

import argparse
import csv
import json
from collections import defaultdict
from pathlib import Path

import cv2
import numpy as np

CELL, COLS, ROWS = 160, 8, 6
PER_SHEET = COLS * ROWS


def _crop_cell(frame: np.ndarray, box: list[float]) -> np.ndarray:
    """The box cut out and fitted into a CELL x CELL square, aspect ratio kept."""
    x1, y1 = max(int(box[0]), 0), max(int(box[1]), 0)
    crop = frame[y1:max(int(box[3]), y1 + 1), x1:max(int(box[2]), x1 + 1)]
    if crop.size == 0:
        return np.zeros((CELL, CELL, 3), np.uint8)
    scale = CELL / max(crop.shape[:2])
    size = (max(1, round(crop.shape[1] * scale)), max(1, round(crop.shape[0] * scale)))
    crop = cv2.resize(crop, size, interpolation=cv2.INTER_AREA)
    cell = np.zeros((CELL, CELL, 3), np.uint8)
    top, left = (CELL - crop.shape[0]) // 2, (CELL - crop.shape[1]) // 2
    cell[top:top + crop.shape[0], left:left + crop.shape[1]] = crop
    return cell


def _number(cell: np.ndarray, n: int) -> None:
    text = str(n)
    (tw, th), base = cv2.getTextSize(text, cv2.FONT_HERSHEY_SIMPLEX, 0.6, 2)
    cv2.rectangle(cell, (0, 0), (tw + 8, th + base + 6), (0, 0, 0), -1)
    cv2.putText(cell, text, (4, th + 3), cv2.FONT_HERSHEY_SIMPLEX, 0.6, (255, 255, 255), 2, cv2.LINE_AA)


def main(argv: list[str] | None = None) -> None:
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--labels", type=Path, required=True)
    ap.add_argument("--frames", type=Path, required=True)
    ap.add_argument("--out", type=Path, required=True)
    args = ap.parse_args(argv)

    by_label: dict[str, list[dict]] = defaultdict(list)
    for line in args.labels.read_text().splitlines():
        if not line.strip():
            continue
        row = json.loads(line)
        if row["box"] is not None:
            by_label[row["label"]].append(row)

    args.out.mkdir(parents=True, exist_ok=True)
    for old in args.out.glob("*/*.jpg"):  # sheets of an earlier run would be out of step with the new index
        old.unlink()
    index = []
    cache: tuple[str, np.ndarray] | None = None
    for label, rows in sorted(by_label.items()):
        (args.out / label).mkdir(exist_ok=True)
        for start in range(0, len(rows), PER_SHEET):
            sheet = np.zeros((ROWS * CELL, COLS * CELL, 3), np.uint8)
            for slot, row in enumerate(rows[start:start + PER_SHEET]):
                if cache is None or cache[0] != row["frame"]:
                    image = cv2.imread(str(args.frames / row["frame"]))
                    if image is None:
                        raise FileNotFoundError(args.frames / row["frame"])
                    cache = (row["frame"], image)
                n = start + slot + 1
                cell = _crop_cell(cache[1], row["box"])
                _number(cell, n)
                y, x = divmod(slot, COLS)
                sheet[y * CELL:(y + 1) * CELL, x * CELL:(x + 1) * CELL] = cell
                index.append([n, row["id"], label, row["status"], row["bioclip"]["species"], row["inat"]["species"] or ""])
            cv2.imwrite(str(args.out / label / f"{label}_{start // PER_SHEET + 1:02d}.jpg"), sheet)

    with open(args.out / "index.csv", "w", newline="") as f:
        writer = csv.writer(f, lineterminator="\n")
        writer.writerow(["n", "id", "label", "status", "bioclip", "inat"])
        writer.writerows(index)
    corrections = args.out / "corrections.csv"
    if not corrections.exists():
        corrections.write_text("id,label\n")
    print(f"{len(index)} crops on {sum(-(-len(r) // PER_SHEET) for r in by_label.values())} sheets in {args.out}")


if __name__ == "__main__":
    main()
