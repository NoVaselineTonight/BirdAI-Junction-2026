"""Ad-hoc: the in-domain teacher (a large detector trained on this camera) proposes birds the first teacher missed.

    python data/big_propose.py <weights.pt> <labels.jsonl> <frames dir> <out.jsonl>

Runs the detector on every TRAINING frame named in <labels.jsonl> (never the held-out day) and writes a
labels-format row for each detection that overlaps no existing teacher box (IoU < 0.4). The rows carry
`source: "big"`; relabel3.py then filters and names them like any unsure box. A detection the big teacher
is sure about (>= 0.9) and that names a bird species keeps that name as its "BioCLIP" guess.
"""
import json
import sys
from pathlib import Path

from ultralytics import YOLO

weights, labels_path, frames_dir, out_path = sys.argv[1], Path(sys.argv[2]), Path(sys.argv[3]), Path(sys.argv[4])
HELD_OUT = "talvilintulive-20261112"
SKIP_NAMES = {"unidentified", "red_squirrel"}


def iou(a, b):
    w = min(a[2], b[2]) - max(a[0], b[0])
    h = min(a[3], b[3]) - max(a[1], b[1])
    if w <= 0 or h <= 0:
        return 0.0
    return w * h / ((a[2] - a[0]) * (a[3] - a[1]) + (b[2] - b[0]) * (b[3] - b[1]) - w * h)


existing, video_of = {}, {}
for line in open(labels_path):
    r = json.loads(line)
    if r["video"] == HELD_OUT or not (r["video"].startswith("talvilintulive-") or r["video"].startswith("catv-")):
        continue
    existing.setdefault(r["frame"], [])
    video_of[r["frame"]] = r["video"]
    if r["box"] is not None:
        existing[r["frame"]].append(r["box"])
frames = sorted(existing)
model = YOLO(weights)
names = model.names
out, n_new = open(out_path, "w"), 0
for i in range(0, len(frames), 32):
    chunk = frames[i:i + 32]
    for frame, res in zip(chunk, model.predict([str(frames_dir / f) for f in chunk], imgsz=1280, conf=0.3, verbose=False)):
        stem = Path(frame).stem
        k = 0
        for b in res.boxes:
            box = [round(float(v), 1) for v in b.xyxy[0]]
            if any(iou(box, e) >= 0.4 for e in existing[frame]):
                continue
            name, conf = names[int(b.cls[0])], float(b.conf[0])
            sure = conf >= 0.9 and name not in SKIP_NAMES
            row = {"id": f"{stem}#big{k}", "split": "train", "video": video_of[frame], "frame": frame, "box": box,
                   "box_conf": round(conf, 3), "source": "big",
                   "bioclip": {"species": name if name not in SKIP_NAMES else "unidentified",
                               "score": round(conf, 3) if sure else 0.0, "margin": round(conf, 3) if sure else 0.0},
                   "inat": None, "label": "unidentified", "status": "review", "big_class": name}
            out.write(json.dumps(row) + "\n")
            existing[frame].append(box)
            k += 1
            n_new += 1
    if i % 3200 == 0:
        print(i, "/", len(frames), "new boxes", n_new, flush=True)
out.close()
print("frames", len(frames), "new boxes", n_new)
print("DONE")
