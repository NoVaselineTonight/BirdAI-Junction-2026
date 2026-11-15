"""Ad-hoc: paste squirrel cut-outs into frames of the feeder camera, to teach the squirrel class.

    python data/squirrel_paste.py <labels tag> [count]

Reads data/labels/<tag>.jsonl and data/review/corrections_<tag>.csv (so the birds already in a frame
keep their final labels), data/squirrel_cut/*.png and, if present, data/squirrel_cut/exclude.txt
(cut-out names to skip, one per line). Uses training footage of the feeder only, never the held-out
day. Writes data/frames/train/synth-squirrel/synth-squirrel_<n>.jpg and
data/labels/squirrel_synth.jsonl, plus the sheet data/check/sq_synth.jpg.
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
count = int(sys.argv[2]) if len(sys.argv) > 2 else 1200
random.seed(7)
np.random.seed(7)

rows = [json.loads(line) for line in open(root / "labels" / f"{tag}.jsonl")]
corrections = {r["id"]: r["label"] for r in csv.DictReader(open(root / "review" / f"corrections_{tag}.csv"))}
by_frame = {}
for r in rows:
    if r["split"] != "train" or not r["video"].startswith("talvilintulive-"):
        continue
    birds = by_frame.setdefault(r["frame"], [])
    if r["box"] is None:
        continue
    label = corrections.get(r["id"], r["label"])
    if label != "drop":
        birds.append((r["box"], label))
empty = sorted(f for f, b in by_frame.items() if not b)
busy = sorted(f for f, b in by_frame.items() if b)

skip = set()
if (root / "squirrel_cut" / "exclude.txt").exists():
    skip = {s.strip() for s in (root / "squirrel_cut" / "exclude.txt").read_text().split()}
def solid(path):
    """A usable cut-out is one solid piece with a sensible fill and proportions (drops fragments and slivers)."""
    a = (cv2.imread(str(path), cv2.IMREAD_UNCHANGED)[:, :, 3] > 0).astype(np.uint8)
    n, _, stats, _ = cv2.connectedComponentsWithStats(a)
    if n < 2:
        return False
    biggest = stats[1:, cv2.CC_STAT_AREA].max()
    h, w = a.shape
    return biggest >= 0.93 * a.sum() and 0.3 <= a.mean() <= 0.85 and 0.4 <= w / h <= 2.5


all_cuts = sorted(p for p in (root / "squirrel_cut").glob("*.png") if p.stem not in skip)
cuts = [p for p in all_cuts if solid(p)]
print(f"cut-outs passing the shape filter: {len(cuts)} of {len(all_cuts)}")
random.shuffle(cuts)  # the tail of the list becomes validation, so it holds cut-outs the training part never used
print(f"backgrounds: {len(empty)} empty, {len(busy)} with birds; cut-outs {len(cuts)} (skipped {len(skip)})")

out_dir = root / "frames" / "train" / "synth-squirrel"
out_dir.mkdir(parents=True, exist_ok=True)
for old in out_dir.glob("*.jpg"):
    old.unlink()
out_rows, samples = [], []


def overlaps(a, b):
    return min(a[2], b[2]) > max(a[0], b[0]) and min(a[3], b[3]) > max(a[1], b[1])


for n in range(count):
    cut = cv2.imread(str(cuts[n * len(cuts) // count]), cv2.IMREAD_UNCHANGED)
    frame_name = random.choice(busy if (n % 2 and busy) else empty)
    frame = cv2.imread(str(root / "frames" / frame_name))
    H, W = frame.shape[:2]
    ch, cw = cut.shape[:2]
    target = min(random.uniform(0.12, 0.38) * H, 1.5 * ch)
    s = target / ch
    if cw * s > 0.6 * W:
        s = 0.6 * W / cw
    cut = cv2.resize(cut, (max(8, round(cw * s)), max(8, round(ch * s))), interpolation=cv2.INTER_AREA if s < 1 else cv2.INTER_LINEAR)
    if random.random() < 0.5:
        cut = cut[:, ::-1].copy()
    ch, cw = cut.shape[:2]
    birds = by_frame[frame_name]
    for attempt in range(40):
        x = random.randint(0, W - cw)
        y = random.randint(min(int(0.1 * H), H - ch), H - ch)
        box = [x, y, x + cw, y + ch]
        if not any(overlaps(box, b) for b, _ in birds):
            break
    kept_birds = [(b, lab) for b, lab in birds if not overlaps(box, b)]

    alpha = cut[:, :, 3]
    alpha = cv2.erode(alpha, np.ones((3, 3), np.uint8))
    alpha = cv2.GaussianBlur(alpha, (5, 5), 0).astype(np.float32)[:, :, None] / 255.0
    patch = frame[y:y + ch, x:x + cw].astype(np.float32)
    lab = cv2.cvtColor(cut[:, :, :3], cv2.COLOR_BGR2LAB).astype(np.float32)
    bg_l = cv2.cvtColor(frame[y:y + ch, x:x + cw], cv2.COLOR_BGR2LAB)[:, :, 0].mean()
    inside = cut[:, :, 3] > 0
    lab[:, :, 0] += 0.5 * (bg_l - lab[:, :, 0][inside].mean())  # move the animal's brightness half way to the scene's
    lab[:, :, 1:] = 128 + (lab[:, :, 1:] - 128) * random.uniform(0.7, 1.0)  # winter light is dull
    fg = cv2.cvtColor(np.clip(lab, 0, 255).astype(np.uint8), cv2.COLOR_LAB2BGR).astype(np.float32)
    frame[y:y + ch, x:x + cw] = (fg * alpha + patch * (1 - alpha)).astype(np.uint8)

    stem = f"synth-squirrel_{n:06d}"
    cv2.imwrite(str(out_dir / f"{stem}.jpg"), frame, [cv2.IMWRITE_JPEG_QUALITY, 90])
    base = {"split": "train", "video": "synth-squirrel", "frame": f"train/synth-squirrel/{stem}.jpg", "status": "auto"}
    out_rows.append({**base, "id": f"{stem}#sq", "box": [float(v) for v in box], "label": "red_squirrel"})
    for k, (b, label) in enumerate(kept_birds):
        out_rows.append({**base, "id": f"{stem}#b{k}", "box": b, "label": label})
    if n % (count // 12) == 0 and len(samples) < 12:
        shown = frame.copy()
        cv2.rectangle(shown, (box[0], box[1]), (box[2], box[3]), (0, 0, 255), 3)
        samples.append(cv2.resize(shown, (640, round(640 * H / W))))

with open(root / "labels" / "squirrel_synth.jsonl", "w") as f:
    for r in out_rows:
        f.write(json.dumps(r) + "\n")
h = min(t.shape[0] for t in samples)
samples = [t[:h] for t in samples]
cv2.imwrite(str(root / "check" / "sq_synth.jpg"), np.vstack([np.hstack(samples[i:i + 4]) for i in range(0, 12, 4)]),
            [cv2.IMWRITE_JPEG_QUALITY, 80])
print("frames", count, "rows", len(out_rows))
print("DONE")
