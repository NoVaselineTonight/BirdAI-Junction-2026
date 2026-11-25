"""Ad-hoc: how often does a student name a squirrel on the held-out day (which has none)?

    python data/falsesq.py <dataset> <student dir>
"""
import sys
from pathlib import Path

import cv2

from feeder_census.detectors import build_detector
from feeder_census.species import load_species

dataset, student = Path(sys.argv[1]), Path(sys.argv[2])
det = build_detector("student", Path("models"), load_species(), student_dir=student)
frames = sorted((dataset / "images" / "test").glob("*.jpg"))
hits = []
for f in frames:
    for d in det.detect(cv2.imread(str(f))):
        if d.species == "red_squirrel":
            hits.append((round(d.confidence, 2), f.name))
print("frames", len(frames), "squirrel detections", len(hits))
for t in (0.25, 0.4, 0.5, 0.6, 0.8):
    fr = {n for c, n in hits if c >= t}
    print(f"conf >= {t}: {sum(c >= t for c, _ in hits)} boxes in {len(fr)} frames")
print(sorted(hits, reverse=True)[:12])
