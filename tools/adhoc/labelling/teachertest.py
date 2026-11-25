"""Ad-hoc: how many birds the student found (and the teacher did not box) does the teacher detector find with other settings?"""
import collections, json, sys
from pathlib import Path
import cv2
from ultralytics import YOLO
sys.path.insert(0, "tools"); sys.path.insert(0, ".")
import evaluate as ev
dataset = Path("data/dataset_v2a")
classes = json.loads((dataset / "classes.json").read_text())
det = ev._build("student:960", Path("models_v2a"), classes)
det = det[0] if isinstance(det, tuple) else det
targets = []  # (path, box) the student found at >=0.5 with no truth box
truth_boxes = {}
paths = sorted((dataset / "images" / "test").glob("*.jpg"))
for path in paths:
    img = cv2.imread(str(path)); h, w = img.shape[:2]
    truth = ev.read_truth(dataset / "labels" / "test" / f"{path.stem}.txt", (w, h), classes)
    truth_boxes[path] = [t.box for t in truth]
    for p in det.detect(img):
        if p.confidence >= 0.5 and p.species != "unidentified" and not any(ev.iou(p.box, t.box) >= 0.3 for t in truth):
            targets.append((path, p.box))
print("frame size", img.shape, "targets", len(targets), "truth boxes", sum(len(v) for v in truth_boxes.values()))
big = YOLO("yolo26x.pt")
for imgsz, conf in ((1280, 0.20), (1280, 0.05), (1920, 0.20), (1920, 0.05)):
    found = collections.defaultdict(list)
    for i in range(0, len(paths), 16):
        for path, res in zip(paths[i:i + 16], big.predict([str(p) for p in paths[i:i + 16]], imgsz=imgsz, conf=conf, classes=[14], verbose=False)):
            found[path] = [[float(v) for v in b] for b in res.boxes.xyxy]
    hit = sum(any(ev.iou(box, f) >= 0.3 for f in found[path]) for path, box in targets)
    kept = sum(any(ev.iou(t, f) >= 0.5 for f in found[path]) for path in paths for t in truth_boxes[path])
    print(f"imgsz {imgsz} conf {conf}: boxes {sum(len(v) for v in found.values())}, covers {hit}/{len(targets)} of the student-only birds, "
          f"and {kept} of the existing truth boxes")
