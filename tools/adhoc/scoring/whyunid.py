"""Ad-hoc: why does the page show 'unidentified'? Split the student's detections on the held-out day by cause."""
import collections, json, sys
from pathlib import Path
import cv2
sys.path.insert(0, "tools"); sys.path.insert(0, ".")
import evaluate as ev
dataset, models_dir, size = Path(sys.argv[1]), Path(sys.argv[2]), sys.argv[3]
classes = json.loads((dataset / "classes.json").read_text())
det = ev._build(f"student:{size}", models_dir, classes)
det = det[0] if isinstance(det, tuple) else det
c = collections.Counter(); truth_of_unid = collections.Counter(); truth_of_low = collections.Counter(); n_frames = 0
for path in sorted((dataset / "images" / "test").glob("*.jpg")):
    img = cv2.imread(str(path)); h, w = img.shape[:2]; n_frames += 1
    truth = ev.read_truth(dataset / "labels" / "test" / f"{path.stem}.txt", (w, h), classes)
    for p in det.detect(img):
        near = [t for t in truth if ev.iou(p.box, t.box) >= 0.5]
        t = near[0].species if near else "(no teacher box)"
        if p.species == "unidentified":
            c["model itself says unidentified"] += 1; truth_of_unid[t] += 1
        elif p.confidence < 0.4:
            c["named, confidence under 0.4"] += 1; truth_of_low[t] += 1
        elif p.confidence < 0.6:
            c["named, confidence 0.4-0.6"] += 1; truth_of_low[t] += 1
        else:
            c["named, confidence 0.6 or more"] += 1
print("frames", n_frames, dict(c))
print("teacher's label where the model says unidentified:", truth_of_unid.most_common(6))
print("teacher's label where the model names but under 0.6:", truth_of_low.most_common(6))
