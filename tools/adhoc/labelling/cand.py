"""Ad-hoc: candidate birds for the machine check.

    python data/cand.py <dataset> <split> <out dir> [--shard i/n]

For every image of the split, pools boxes from: the dataset's label (minus boxes too big to be one small bird on
feeder-camera frames), three students (v4 640, v4 960, v5 960) and the camera-tuned teacher (big2.pt), all at
low confidence. Boxes of one bird are merged (IoU >= 0.5, or one box covering >= 70 % of the other). Writes
cands.jsonl (one candidate per bird with every source's vote) and one crop per candidate for the judge.
"""
import json, sys
from pathlib import Path

import cv2
import numpy as np
from ultralytics import YOLO

dataset, split, out = Path(sys.argv[1]), sys.argv[2], Path(sys.argv[3])
shard = (0, 1)
if "--shard" in sys.argv:
    a, b = sys.argv[sys.argv.index("--shard") + 1].split("/")
    shard = (int(a), int(b))
tag = f"{shard[0]}of{shard[1]}"
(out / "crops").mkdir(parents=True, exist_ok=True)
classes = json.loads((dataset / "classes.json").read_text())
K = "keep_from_fast/models"
SOURCES = [
    ("s4_640", f"{K}/student_v4_640/runs/640/weights/best.pt", 640),
    ("s4_960", f"{K}/student_v4_960/runs/960/weights/best.pt", 960),
    ("s5_960", f"{K}/student_v5_960/runs/960/weights/best.pt", 960),
    ("teacher", "data/big2.pt", 1280),
]
MIN_CONF = 0.2
paths = sorted((dataset / "images" / split).glob("*.jpg"))
paths = [p for i, p in enumerate(paths) if i % shard[1] == shard[0]]
print("images", len(paths), flush=True)

pooled = {p.stem: [] for p in paths}  # stem -> [(src, species, conf, box)]
sizes = {}
for name, weights, imgsz in SOURCES:
    model = YOLO(weights)
    B = 64 if imgsz <= 960 else 24
    for i in range(0, len(paths), B):
        chunk = paths[i:i + B]
        for p, r in zip(chunk, model.predict([str(c) for c in chunk], imgsz=imgsz, conf=MIN_CONF, verbose=False, device=0, half=True)):
            sizes[p.stem] = (r.orig_shape[1], r.orig_shape[0])
            for box, conf, cls in zip(r.boxes.xyxy.tolist(), r.boxes.conf.tolist(), r.boxes.cls.tolist()):
                pooled[p.stem].append((name, model.names[int(cls)], float(conf), [float(v) for v in box]))
    print("source done", name, flush=True)
    del model

for p in paths:
    W, H = sizes.get(p.stem, (1920, 1080))
    lf = dataset / "labels" / split / f"{p.stem}.txt"
    feeder = p.stem.startswith("talvilintulive-")
    for line in (lf.read_text().splitlines() if lf.exists() else []):
        q = line.split()
        if len(q) < 5:
            continue
        c, cx, cy, w, h = int(q[0]), *[float(v) for v in q[1:5]]
        if feeder and classes[c] != "red_squirrel" and (h >= 330 / 1080 or w >= 500 / 1920):
            continue
        pooled[p.stem].append(("label", classes[c], 1.0, [(cx - w / 2) * W, (cy - h / 2) * H, (cx + w / 2) * W, (cy + h / 2) * H]))


def rel(a, b):
    w = min(a[2], b[2]) - max(a[0], b[0]); h = min(a[3], b[3]) - max(a[1], b[1])
    inter = max(w, 0) * max(h, 0)
    aa, bb = (a[2] - a[0]) * (a[3] - a[1]), (b[2] - b[0]) * (b[3] - b[1])
    return inter / max(aa + bb - inter, 1e-9), inter / max(min(aa, bb), 1e-9)


PRIORITY = {"s4_960": 0, "s5_960": 1, "s4_640": 2, "teacher": 3, "label": 4}
n_c = 0
with open(out / f"cands-{tag}.jsonl", "w") as fh:
    for p in paths:
        items = pooled[p.stem]
        if not items:
            continue
        parent = list(range(len(items)))

        def find(i):
            while parent[i] != i:
                parent[i] = parent[parent[i]]
                i = parent[i]
            return i

        for i in range(len(items)):
            for j in range(i + 1, len(items)):
                iou, cov = rel(items[i][3], items[j][3])
                if iou >= 0.5 or cov >= 0.7:
                    parent[find(i)] = find(j)
        groups = {}
        for i, it in enumerate(items):
            groups.setdefault(find(i), []).append(it)
        img = None
        for k, g in enumerate(groups.values()):
            best = min(g, key=lambda it: (PRIORITY[it[0]], -it[2]))
            same = [it[3] for it in g if it[0] == best[0]]
            box = [float(np.median([b[d] for b in same])) for d in range(4)] if len(same) > 1 else best[3]
            if img is None:
                img = cv2.imread(str(p))
            H, W = img.shape[:2]
            bw, bh = box[2] - box[0], box[3] - box[1]
            if bw < 6 or bh < 6:
                continue
            side = max(1.6 * max(bw, bh), 128)
            cx, cy = (box[0] + box[2]) / 2, (box[1] + box[3]) / 2
            x0, y0 = int(max(cx - side / 2, 0)), int(max(cy - side / 2, 0))
            x1, y1 = int(min(cx + side / 2, W)), int(min(cy + side / 2, H))
            crop = img[y0:y1, x0:x1]
            s = 448 / max(crop.shape[:2])
            crop = cv2.resize(crop, (max(int(crop.shape[1] * s), 8), max(int(crop.shape[0] * s), 8)), interpolation=cv2.INTER_CUBIC if s > 1 else cv2.INTER_AREA)
            cid = f"{p.stem}__{k}"
            cv2.imwrite(str(out / "crops" / f"{cid}.jpg"), crop, [cv2.IMWRITE_JPEG_QUALITY, 92])
            fh.write(json.dumps(dict(id=cid, frame=p.stem, W=W, H=H, box=[round(v, 1) for v in box],
                                     votes=[dict(src=it[0], species=it[1], conf=round(it[2], 3)) for it in g])) + "\n")
            n_c += 1
print("candidates", n_c, "done", flush=True)
