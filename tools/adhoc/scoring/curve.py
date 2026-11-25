"""Ad-hoc: precision/recall of a student at several confidence levels, on test and val. python data/curve.py <dataset> <models_dir> <size>"""
import json, sys
from pathlib import Path
sys.path.insert(0, "tools"); sys.path.insert(0, ".")
import evaluate as ev
dataset, models_dir, size = Path(sys.argv[1]), Path(sys.argv[2]), sys.argv[3]
classes = json.loads((dataset / "classes.json").read_text())
species = [c for c in classes if c != "unidentified"]
det = ev._build(f"student:{size}", models_dir, classes)
if isinstance(det, tuple):
    det = det[0]
for split in ("test", "val"):
    frames, _ = ev.run_split(det, dataset, split, classes)
    boxes = ev.count_boxes(frames, species)
    print(f"== {split}: {len(frames)} frames; boxes {boxes}")
    for thr in (0.25, 0.4, 0.5, 0.6, 0.7, 0.8, 0.9):
        tall = ev._tally_frames(frames, thr, species)
        cells = []
        for s in species:
            if boxes[s] < 10: continue
            p, r = ev._known_rates(tall[s])
            cells.append(f"{s[:9]} {('%.2f' % p) if p is not None else '  - '}/{('%.2f' % r) if r is not None else '  - '}")
        exact = sum(ev.frame_is_exact(p, t, thr, species) for p, t in frames) / len(frames)
        tp = sum(t.tp for t in tall.values()); fp = sum(t.fp for t in tall.values()); fn = sum(t.fn for t in tall.values())
        print(f"thr {thr:.2f} all P {tp/max(tp+fp,1):.2f} R {tp/max(tp+fn,1):.2f} exact {exact:.2f} | " + " | ".join(cells))
