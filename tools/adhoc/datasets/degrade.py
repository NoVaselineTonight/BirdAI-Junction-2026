"""Ad-hoc: worse-quality copies of training frames, with the same labels (the user's idea).

    python data/degrade.py <labels tag> [every]

Reads data/labels/<tag>.jsonl and data/review/corrections_<tag>.csv. For every `every`-th training
frame of the feeder camera and the forest-feeder videos (never the held-out day) writes a degraded
copy next to the original as <video>_<ms+1>.jpg, so it lands in the same train/val part as its
original, and writes data/labels/lowq_<tag>.jsonl with the final labels.
Degradations, mixed at random: shrink and enlarge, strong JPEG compression, blur, noise, dull contrast.
"""
import csv
import json
import random
import sys
from pathlib import Path

import cv2
import numpy as np

root = Path("data")
tag = sys.argv[1]
every = int(sys.argv[2]) if len(sys.argv) > 2 else 4
random.seed(3)
np.random.seed(3)
rows = [json.loads(line) for line in open(root / "labels" / f"{tag}.jsonl")]
corrections = {r["id"]: r["label"] for r in csv.DictReader(open(root / "review" / f"corrections_{tag}.csv"))}
by_frame = {}
for r in rows:
    if r["split"] != "train" or not (r["video"].startswith("talvilintulive-") or r["video"].startswith("catv-")):
        continue
    by_frame.setdefault(r["frame"], []).append(r)


def degrade(img):
    h, w = img.shape[:2]
    if random.random() < 0.7:
        f = random.uniform(0.3, 0.6)
        img = cv2.resize(cv2.resize(img, (int(w * f), int(h * f)), interpolation=cv2.INTER_AREA), (w, h),
                         interpolation=random.choice([cv2.INTER_LINEAR, cv2.INTER_CUBIC, cv2.INTER_NEAREST]))
    if random.random() < 0.4:
        k = random.choice([5, 7, 9])
        kernel = np.zeros((k, k), np.float32)
        if random.random() < 0.5:
            kernel[k // 2, :] = 1.0 / k
        else:
            kernel[:, k // 2] = 1.0 / k
        img = cv2.filter2D(img, -1, kernel)
    elif random.random() < 0.5:
        img = cv2.GaussianBlur(img, (0, 0), random.uniform(0.8, 1.8))
    if random.random() < 0.5:
        img = np.clip(img.astype(np.float32) * random.uniform(0.75, 1.0) + random.uniform(-10, 25), 0, 255).astype(np.uint8)
    if random.random() < 0.4:
        img = np.clip(img.astype(np.float32) + np.random.normal(0, random.uniform(3, 9), img.shape), 0, 255).astype(np.uint8)
    ok, buf = cv2.imencode(".jpg", img, [cv2.IMWRITE_JPEG_QUALITY, random.randint(18, 45)])
    return cv2.imdecode(buf, cv2.IMREAD_COLOR)


out_rows, n = [], 0
for i, frame in enumerate(sorted(by_frame)):
    if i % every:
        continue
    src = root / "frames" / frame
    img = cv2.imread(str(src))
    if img is None:
        continue
    stem = src.stem
    video, ms = stem.rsplit("_", 1)
    new_stem = f"{video}_{int(ms) + 1:0{len(ms)}d}"
    new_frame = str(Path(frame).with_name(new_stem + ".jpg"))
    cv2.imwrite(str(root / "frames" / new_frame), degrade(img), [cv2.IMWRITE_JPEG_QUALITY, 92])
    kept = 0
    for k, r in enumerate(by_frame[frame]):
        if r["box"] is None:
            continue
        label = corrections.get(r["id"], r["label"])
        if label == "drop":
            continue
        out_rows.append({"id": f"{new_stem}#q{k}", "split": "train", "video": r["video"], "frame": new_frame,
                         "box": r["box"], "label": label, "status": "auto"})
        kept += 1
    if not kept:
        out_rows.append({"id": f"{new_stem}#-", "split": "train", "video": by_frame[frame][0]["video"], "frame": new_frame,
                         "box": None, "label": None, "status": "empty"})
    n += 1
    if n % 2000 == 0:
        print(n, flush=True)
with open(root / "labels" / f"lowq_{tag}.jsonl", "w") as f:
    for r in out_rows:
        f.write(json.dumps(r) + "\n")
print("degraded frames", n, "rows", len(out_rows))
print("DONE")
