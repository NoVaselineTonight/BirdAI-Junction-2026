"""Ad-hoc: draw the final training labels on a spread of frames, for a person to look at.

    python data/samples.py <labels tag> [count]

Reads data/labels/<tag>.jsonl and data/review/corrections_<tag>.csv; writes data/samples/<n>_<label>.jpg
(1280 px wide, boxes drawn, dropped boxes not drawn) and data/samples/index.csv. Training split only.
"""
import csv
import json
import random
import shutil
import sys
from pathlib import Path

import cv2

root = Path("data")
tag = sys.argv[1]
count = int(sys.argv[2]) if len(sys.argv) > 2 else 100
random.seed(11)
rows = [json.loads(line) for line in open(root / "labels" / f"{tag}.jsonl")]
corr = {r["id"]: r["label"] for r in csv.DictReader(open(root / "review" / f"corrections_{tag}.csv"))}
frames = {}
for r in rows:
    if r["split"] != "train":
        continue
    boxes = frames.setdefault(r["frame"], [])
    if r.get("box") is None:
        continue
    label = corr.get(r["id"], r["label"])
    if label != "drop":
        boxes.append((r["box"], label))
by_label = {}
for f, boxes in frames.items():
    for lab in {b[1] for b in boxes}:
        by_label.setdefault(lab, []).append(f)
empty = [f for f, b in frames.items() if not b]
print({k: len(v) for k, v in by_label.items()}, "empty", len(empty))
# a spread: common species get more, every label at least a few, a few empty frames
want = {"great_tit": 18, "blue_tit": 14, "unidentified": 10, "red_squirrel": 10, "magpie": 7, "jay": 6, "bullfinch": 6,
        "nuthatch": 5, "tree_sparrow": 5, "great_spotted_woodpecker": 4, "crested_tit": 3, "house_sparrow": 3,
        "willow_tit": 2, "coal_tit": 2}
picked, why = [], {}
for lab, n in want.items():
    pool = [f for f in sorted(by_label.get(lab, [])) if f not in why]
    random.shuffle(pool)
    for f in pool[:n]:
        picked.append(f)
        why[f] = lab
rest = sorted(set(frames) - set(why))
random.shuffle(rest)
for f in [f for f in empty if f not in why][:5] + rest:
    if len(picked) >= count:
        break
    if f not in why:
        picked.append(f)
        why[f] = "empty" if not frames[f] else "mixed"
COLORS = {"great_tit": (0, 220, 255), "blue_tit": (255, 160, 0), "red_squirrel": (0, 0, 255), "unidentified": (170, 170, 170),
          "magpie": (255, 255, 255), "jay": (200, 120, 255), "bullfinch": (80, 80, 255), "nuthatch": (0, 200, 120)}
out = root / "samples"
shutil.rmtree(out, ignore_errors=True)
out.mkdir()
with open(out / "index.csv", "w", newline="") as fh:
    w = csv.writer(fh)
    w.writerow(["file", "picked_for", "source_video", "frame", "labels"])
    for n, f in enumerate(picked[:count]):
        img = cv2.imread(str(root / "frames" / f))
        if img is None:
            continue
        s = 1280 / img.shape[1]
        img = cv2.resize(img, (1280, round(img.shape[0] * s)), interpolation=cv2.INTER_AREA if s < 1 else cv2.INTER_LINEAR)
        for box, lab in frames[f]:
            x1, y1, x2, y2 = [int(v * s) for v in box]
            c = COLORS.get(lab, (0, 255, 0))
            cv2.rectangle(img, (x1, y1), (x2, y2), c, 2)
            text = lab.replace("_", " ")
            (tw, th), _ = cv2.getTextSize(text, cv2.FONT_HERSHEY_SIMPLEX, 0.6, 2)
            ty = y1 - 6 if y1 > th + 10 else y2 + th + 6
            cv2.rectangle(img, (x1, ty - th - 4), (x1 + tw + 6, ty + 4), (0, 0, 0), -1)
            cv2.putText(img, text, (x1 + 3, ty), cv2.FONT_HERSHEY_SIMPLEX, 0.6, c, 2)
        name = f"{n:03d}_{why[f]}.jpg"
        cv2.imwrite(str(out / name), img, [cv2.IMWRITE_JPEG_QUALITY, 85])
        w.writerow([name, why[f], f.split("/")[1], Path(f).name, " ".join(sorted(b[1] for b in frames[f]))])
print("wrote", len(list(out.glob("*.jpg"))))
print("DONE")
