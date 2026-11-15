"""Ad-hoc: score a student on the held-out frames twice: against the labels as they are, and against the same
labels with two mechanical defects removed (rules use label boxes only, never the model's output):

  - two labels of the same species where one covers >= 60 % of the other count as ONE bird
    (a prediction may match either box);
  - a label taller than 330 px or wider than 500 px (in the 1920x1080 frame) is not one small bird:
    it is ignored, and a prediction on it is neither a hit nor an error.

    PYTHONPATH=. python data/rescore.py <dataset> <student dir> <name>
"""
import json, sys
from collections import Counter
from pathlib import Path

import cv2

sys.path.insert(0, "tools"); sys.path.insert(0, ".")
import evaluate as ev
from feeder_census.detectors import build_detector
from feeder_census.species import load_species

dataset, student_dir, name = Path(sys.argv[1]), Path(sys.argv[2]), sys.argv[3]
classes = json.loads((dataset / "classes.json").read_text())
species = [c for c in classes if c != "unidentified"]
det = build_detector("student", Path("models"), load_species(), student_dir=student_dir)

import os, dataclasses
if os.environ.get("TILES"):  # ad-hoc: run the detector on two overlapping halves of the photo and merge
    OVER = int(os.environ["TILES"])
    _plain = det.detect

    def _cover(a, b):
        w = min(a[2], b[2]) - max(a[0], b[0]); h = min(a[3], b[3]) - max(a[1], b[1])
        return max(w, 0) * max(h, 0) / max(min((a[2]-a[0])*(a[3]-a[1]), (b[2]-b[0])*(b[3]-b[1])), 1e-9)

    def _tiled(img):
        H, W = img.shape[:2]
        tw = (W + OVER) // 2
        out = []
        for x0 in (0, W - tw):
            for p in _plain(img[:, x0:x0 + tw]):
                b = p.box
                if (x0 == 0 and b[2] >= tw - 3) or (x0 > 0 and b[0] <= 3):
                    continue  # cut by the inner tile edge: the other half sees it whole
                out.append(dataclasses.replace(p, box=(b[0] + x0, b[1], b[2] + x0, b[3])))
        keep = []
        for p in sorted(out, key=lambda d: -d.confidence):
            if not any(_cover(p.box, k.box) >= 0.6 for k in keep):
                keep.append(p)
        return keep

    det.detect = _tiled


def cover(a, b):
    w = min(a[2], b[2]) - max(a[0], b[0]); h = min(a[3], b[3]) - max(a[1], b[1])
    inter = max(w, 0) * max(h, 0)
    return inter / min((a[2] - a[0]) * (a[3] - a[1]), (b[2] - b[0]) * (b[3] - b[1]))


frames = []
for path in sorted((dataset / "images" / "test").glob("*.jpg")):
    img = cv2.imread(str(path))
    H, W = img.shape[:2]
    truth = ev.read_truth(dataset / "labels" / "test" / f"{path.stem}.txt", (W, H), classes)
    frames.append((det.detect(img), truth, W / 1920.0))

for thr in (0.4, 0.5, 0.6):
    # as the labels are
    tall = ev._tally_frames([(p, t) for p, t, _ in frames], thr, species)
    tp = sum(t.tp for t in tall.values()); fp = sum(t.fp for t in tall.values()); fn = sum(t.fn for t in tall.values())
    exact = sum(ev.frame_is_exact(p, t, thr, species) for p, t, _ in frames) / len(frames)
    print(f"ROW {name} thr {thr:.2f} labels-as-is  P {tp/max(tp+fp,1):.3f} R {tp/max(tp+fn,1):.3f} exact {exact:.3f} tp {tp} fp {fp} fn {fn}")
    # with the two defects removed
    TP = FP = FN = EX = merged = dropped = 0
    per = {s: [0, 0, 0] for s in species}
    for pred, truth, k in frames:
        huge = [t for t in truth if t.species != "unidentified" and ((t.box[3] - t.box[1]) >= 330 * k or (t.box[2] - t.box[0]) >= 500 * k)]
        ignore = [t.box for t in truth if t.species == "unidentified"] + [t.box for t in huge]
        keep = [t for t in truth if t.species != "unidentified" and t not in huge]
        dropped += len(huge)
        parent = list(range(len(keep)))

        def find(i):
            while parent[i] != i:
                parent[i] = parent[parent[i]]
                i = parent[i]
            return i

        for i in range(len(keep)):
            for j in range(i + 1, len(keep)):
                if keep[i].species == keep[j].species and cover(keep[i].box, keep[j].box) >= 0.6:
                    parent[find(i)] = find(j)
        clusters = {}
        for i, t in enumerate(keep):
            clusters.setdefault(find(i), []).append(t)
        merged += len(keep) - len(clusters)
        free = list(clusters.values())
        counted = Counter()
        for p in sorted(pred, key=lambda d: -d.confidence):
            if p.species == "unidentified" or p.confidence < thr:
                continue
            if any(ev.iou(p.box, b) >= 0.5 for b in ignore):
                continue
            counted[p.species] += 1
            cands = [(max(ev.box_iou(p, t) for t in c), n) for n, c in enumerate(free) if c[0].species == p.species]
            cands = [c for c in cands if c[0] >= 0.5]
            if cands:
                free.pop(max(cands)[1])
                TP += 1; per[p.species][0] += 1
            else:
                FP += 1; per[p.species][1] += 1
        for c in free:
            FN += 1; per[c[0].species][2] += 1
        wanted = Counter(c[0].species for c in clusters.values())
        EX += all(counted.get(s, 0) == wanted.get(s, 0) for s in species)
    print(f"ROW {name} thr {thr:.2f} defects-removed P {TP/max(TP+FP,1):.3f} R {TP/max(TP+FN,1):.3f} exact {EX/len(frames):.3f} tp {TP} fp {FP} fn {FN} merged {merged} ignored {dropped}")
    if thr == 0.5:
        for s in species:
            a, b, c = per[s]
            if a + c:
                print(f"   {name} {s:26s} P {a/max(a+b,1):.2f} R {a/max(a+c,1):.2f} birds {a+c}")
