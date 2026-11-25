"""Ad-hoc: contact sheets of the student's false alarms and misses on the held-out day at one threshold.
python data/errsheet.py <dataset> <models_dir> <size> <threshold>"""
import json, random, sys
from pathlib import Path
import cv2, numpy as np
sys.path.insert(0, "tools"); sys.path.insert(0, ".")
import evaluate as ev
dataset, models_dir, size, thr = Path(sys.argv[1]), Path(sys.argv[2]), sys.argv[3], float(sys.argv[4])
classes = json.loads((dataset / "classes.json").read_text())
det = ev._build(f"student:{size}", models_dir, classes)
det = det[0] if isinstance(det, tuple) else det
fps, fns = [], []
for path in sorted((dataset / "images" / "test").glob("*.jpg")):
    img = cv2.imread(str(path))
    h, w = img.shape[:2]
    truth = ev.read_truth(dataset / "labels" / "test" / f"{path.stem}.txt", (w, h), classes)
    pred = [d for d in det.detect(img) if d.confidence >= thr and d.species != "unidentified"]
    unknown = [t.box for t in truth if t.species == "unidentified"]
    pred = [p for p in pred if not any(ev.iou(p.box, b) >= 0.5 for b in unknown)]
    free = [t for t in truth if t.species != "unidentified"]
    for p in sorted(pred, key=lambda d: -d.confidence):
        cand = [t for t in free if t.species == p.species and ev.iou(p.box, t.box) >= 0.5]
        if cand:
            free.remove(max(cand, key=lambda t: ev.iou(p.box, t.box)))
        else:
            near = [t for t in truth if ev.iou(p.box, t.box) >= 0.3]
            why = ("truth:" + near[0].species[:6]) if near else "no truth box"
            fps.append((path, p.box, f"{p.species[:6]} {p.confidence:.2f} {why}"))
    for t in free:
        fns.append((path, t.box, f"missed {t.species[:8]}"))
print("false alarms", len(fps), "misses", len(fns))
import collections
print("false alarm kinds:", collections.Counter(s.split(" ", 2)[2] for _, _, s in fps).most_common(8))


def sheet(name, items, n=64, cols=8, size=170):
    random.seed(4)
    items = random.sample(items, min(n, len(items)))
    tiles = []
    for path, box, text in items:
        img = cv2.imread(str(path))
        x1, y1, x2, y2 = [int(v) for v in box]
        pad = int(0.35 * max(x2 - x1, y2 - y1))
        c = img[max(0, y1 - pad):y2 + pad, max(0, x1 - pad):x2 + pad].copy()
        cv2.rectangle(c, (min(pad, x1), min(pad, y1)), (min(pad, x1) + x2 - x1, min(pad, y1) + y2 - y1), (0, 255, 0), 1)
        hh, ww = c.shape[:2]
        s = size / max(hh, ww)
        c = cv2.resize(c, (max(1, int(ww * s)), max(1, int(hh * s))))
        t = np.full((size, size, 3), 40, np.uint8)
        t[:c.shape[0], :c.shape[1]] = c
        cv2.putText(t, text, (3, size - 5), cv2.FONT_HERSHEY_SIMPLEX, 0.36, (0, 255, 255), 1)
        tiles.append(t)
    while len(tiles) % cols:
        tiles.append(np.full((size, size, 3), 40, np.uint8))
    cv2.imwrite(f"data/check/{name}.jpg", np.vstack([np.hstack(tiles[i:i + cols]) for i in range(0, len(tiles), cols)]),
                [cv2.IMWRITE_JPEG_QUALITY, 82])


sheet("err_false_alarms", fps)
sheet("err_misses", fns)
print("DONE")
