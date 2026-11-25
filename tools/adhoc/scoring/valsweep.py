import json, sys
from pathlib import Path
sys.path.insert(0, "tools"); sys.path.insert(0, ".")
import evaluate as ev
from feeder_census.detectors import build_detector
from feeder_census.species import load_species
ds = Path("data/dataset_v8"); classes = json.loads((ds / "classes.json").read_text()); species = [c for c in classes if c != "unidentified"]
det = build_detector("student", Path("models"), load_species(), student_dir=Path(sys.argv[1]))
for split in ("val", "test"):
    frames, _ = ev.run_split(det, ds, split, classes)
    for thr in (0.25, 0.30, 0.35, 0.40, 0.45, 0.50, 0.60):
        tall = ev._tally_frames(frames, thr, species)
        tp = sum(t.tp for t in tall.values()); fp = sum(t.fp for t in tall.values()); fn = sum(t.fn for t in tall.values())
        exact = sum(ev.frame_is_exact(p, t, thr, species) for p, t in frames) / len(frames)
        sq = tall.get("red_squirrel")
        print(f"{split} thr {thr:.2f} P {tp/max(tp+fp,1):.3f} R {tp/max(tp+fn,1):.3f} exact {exact:.3f} squirrel tp/fp/fn {sq.tp if sq else 0}/{sq.fp if sq else 0}/{sq.fn if sq else 0}")
