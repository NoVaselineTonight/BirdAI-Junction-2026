import sys, collections
from pathlib import Path
import cv2
from ultralytics import YOLOWorld, YOLO
photos = sorted(Path("data/squirrel_src/images").glob("*.jpg"))[:60]
for names in (["squirrel"], ["squirrel", "bird", "cat", "dog", "person", "marten", "rabbit"], ["a red squirrel", "bird"]):
    m = YOLOWorld("yolov8l-worldv2.pt"); m.set_classes(names)
    hit = collections.Counter(); confs = []
    for p in photos:
        im = cv2.imread(str(p))
        r = m.predict(im, conf=0.05, imgsz=960, verbose=False)[0]
        best = {}
        for b in r.boxes:
            c = names[int(b.cls[0])]; best[c] = max(best.get(c, 0), float(b.conf[0]))
        if best:
            top = max(best, key=best.get); hit[top] += 1
            confs.append(round(best.get(names[0], 0), 2))
        else:
            hit["(nothing)"] += 1; confs.append(0)
    print(names, dict(hit)); print(" squirrel conf sorted:", sorted(confs))
m = YOLO("yolo26x.pt")
hit = collections.Counter()
for p in photos:
    r = m.predict(cv2.imread(str(p)), conf=0.15, imgsz=960, verbose=False)[0]
    if len(r.boxes):
        i = int(r.boxes.conf.argmax()); hit[r.names[int(r.boxes.cls[i])]] += 1
    else: hit["(nothing)"] += 1
print("yolo26x top class:", dict(hit))
