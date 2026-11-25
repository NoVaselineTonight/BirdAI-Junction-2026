"""Ad-hoc: one model on the held-out frames of a dataset, whatever class order the model was trained with.

    python data/curve2.py <dataset> <student dir> <name>

Like curve.py but test split only, and the detector is built straight from its own card: predictions carry
species names, so a model from an earlier round (other class order, or no squirrel class) can be scored against
the newest labels. Prints one line per cut-off: name, cut-off, pooled precision, recall, exact-count share.
"""
import json, sys
from pathlib import Path
sys.path.insert(0, "tools"); sys.path.insert(0, ".")
import evaluate as ev
from feeder_census.detectors import build_detector
from feeder_census.species import load_species
dataset, student_dir, name = Path(sys.argv[1]), Path(sys.argv[2]), sys.argv[3]
classes = json.loads((dataset / "classes.json").read_text())
species = [c for c in classes if c != "unidentified"]
det = build_detector("student", Path("models"), load_species(), student_dir=student_dir)
frames, _ = ev.run_split(det, dataset, "test", classes)
for thr in (0.25, 0.4, 0.5, 0.6):
    tall = ev._tally_frames(frames, thr, species)
    exact = sum(ev.frame_is_exact(p, t, thr, species) for p, t in frames) / len(frames)
    tp = sum(t.tp for t in tall.values()); fp = sum(t.fp for t in tall.values()); fn = sum(t.fn for t in tall.values())
    gt, bt = ev._known_rates(tall["great_tit"]), ev._known_rates(tall["blue_tit"])
    print(f"ROW {name} thr {thr:.2f} P {tp/max(tp+fp,1):.3f} R {tp/max(tp+fn,1):.3f} exact {exact:.3f} great_tit {gt[0]}/{gt[1]} blue_tit {bt[0]}/{bt[1]}")
