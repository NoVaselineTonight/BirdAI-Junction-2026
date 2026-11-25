"""Ad-hoc: copy a YOLO dataset with two mechanical label defects removed from train and val (test untouched).

    python data/clean_labels.py <dataset in> <dataset out>

1. Feeder-camera frames only (stem starts with talvilintulive-): a box taller than 330/1080 of the frame or wider
   than 500/1920 is not one small bird (it is a feeder column or a bird plus its surroundings): dropped.
   Squirrel boxes are exempt.
2. Everywhere: two boxes of the same class where one covers >= 60 % of the other are one bird labelled twice.
   If the larger is at most 4x the smaller's area the smaller (a body box inside the whole-bird box) is dropped,
   otherwise the larger (a sloppy box around a small bird) is dropped.
Images are hard-linked, not copied.
"""
import json, shutil, subprocess, sys
from collections import Counter
from pathlib import Path

src, dst = Path(sys.argv[1]), Path(sys.argv[2])
classes = json.loads((src / "classes.json").read_text())
SQ = classes.index("red_squirrel")
MAX_H, MAX_W = 330 / 1080, 500 / 1920
dst.mkdir(parents=True, exist_ok=True)
subprocess.run(["cp", "-al", str(src / "images"), str(dst / "images")], check=True)
for f in ("classes.json", "split.json"):
    if (src / f).exists():
        shutil.copy(src / f, dst / f)
(dst / "data.yaml").write_text((src / "data.yaml").read_text().replace(str(src.resolve()), str(dst.resolve())))
stats = Counter()


def cover(a, b):
    ax0, ay0, ax1, ay1 = a[1] - a[3] / 2, a[2] - a[4] / 2, a[1] + a[3] / 2, a[2] + a[4] / 2
    bx0, by0, bx1, by1 = b[1] - b[3] / 2, b[2] - b[4] / 2, b[1] + b[3] / 2, b[2] + b[4] / 2
    w = min(ax1, bx1) - max(ax0, bx0); h = min(ay1, by1) - max(ay0, by0)
    small = min(a[3] * a[4], b[3] * b[4])
    return max(w, 0) * max(h, 0) / small if small > 0 else 0.0


for split in ("train", "val", "test"):
    (dst / "labels" / split).mkdir(parents=True, exist_ok=True)
    for path in (src / "labels" / split).glob("*.txt"):
        text = path.read_text()
        if split == "test":
            (dst / "labels" / split / path.name).write_text(text)
            continue
        rows = [[int(p[0])] + [float(v) for v in p[1:5]] for p in (l.split() for l in text.splitlines()) if len(p) >= 5]
        stats[f"{split} boxes in"] += len(rows)
        if path.name.startswith("talvilintulive-"):
            kept = [r for r in rows if r[0] == SQ or (r[4] < MAX_H and r[3] < MAX_W)]
            stats[f"{split} huge dropped"] += len(rows) - len(kept)
            rows = kept
        drop = set()
        for i in range(len(rows)):
            for j in range(i + 1, len(rows)):
                a, b = rows[i], rows[j]
                if a[0] != b[0] or cover(a, b) < 0.6:
                    continue
                big, small = (i, j) if a[3] * a[4] >= b[3] * b[4] else (j, i)
                ratio = (rows[big][3] * rows[big][4]) / max(rows[small][3] * rows[small][4], 1e-9)
                drop.add(small if ratio <= 4 else big)
        stats[f"{split} doubles dropped"] += len(drop)
        rows = [r for k, r in enumerate(rows) if k not in drop]
        stats[f"{split} boxes out"] += len(rows)
        (dst / "labels" / split / path.name).write_text("".join(f"{r[0]} {r[1]:.6f} {r[2]:.6f} {r[3]:.6f} {r[4]:.6f}\n" for r in rows))
for k in sorted(stats):
    print(k, stats[k])
