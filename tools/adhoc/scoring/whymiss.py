"""Ad-hoc: for the student's detections on the held-out day with no truth box, was there a teacher box at all, and what became of it?"""
import collections, csv, json, sys
from pathlib import Path
import cv2
sys.path.insert(0, "tools"); sys.path.insert(0, ".")
import evaluate as ev
dataset, models_dir, size, thr = Path("data/dataset_v2a"), Path("models_v2a"), "960", 0.5
classes = json.loads((dataset / "classes.json").read_text())
det = ev._build(f"student:{size}", models_dir, classes)
det = det[0] if isinstance(det, tuple) else det
rows = collections.defaultdict(list)
corr = {r["id"]: r["label"] for r in csv.DictReader(open("data/review/corrections_v2.csv"))}
for line in open("data/labels/v2.jsonl"):
    r = json.loads(line)
    if r["split"] == "demo" and r["box"] is not None:
        rows[Path(r["frame"]).stem].append(r)
out = collections.Counter()
confs = collections.defaultdict(list)
for path in sorted((dataset / "images" / "test").glob("*.jpg")):
    img = cv2.imread(str(path)); h, w = img.shape[:2]
    truth = ev.read_truth(dataset / "labels" / "test" / f"{path.stem}.txt", (w, h), classes)
    for p in det.detect(img):
        if p.confidence < thr or p.species == "unidentified" or any(ev.iou(p.box, t.box) >= 0.3 for t in truth):
            continue
        near = [r for r in rows[path.stem] if ev.iou(p.box, r["box"]) >= 0.3]
        if not near:
            out["teacher drew no box"] += 1
        else:
            r = max(near, key=lambda r: ev.iou(p.box, r["box"]))
            final = corr.get(r["id"], r["label"])
            out[f"teacher box, final label {final}"] += 1
            confs[final].append((round(r["box_conf"], 2), r["bioclip"]["species"][:6], round(r["bioclip"]["score"], 2)))
print(dict(out))
for k, v in confs.items():
    print(k, v[:25])
