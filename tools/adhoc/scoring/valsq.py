import json, sys
from pathlib import Path
sys.path.insert(0, "tools"); sys.path.insert(0, ".")
import evaluate as ev
from feeder_census.detectors import build_detector
from feeder_census.species import load_species
dataset = Path("data/dataset_v8"); classes = json.loads((dataset / "classes.json").read_text()); species = [c for c in classes if c != "unidentified"]
det = build_detector("student", Path("models"), load_species(), student_dir=Path("models_v8/student"))
frames, _ = ev.run_split(det, dataset, "val", classes)
tall = ev._tally_frames(frames, 0.5, species)
for s in ("red_squirrel", "great_tit", "blue_tit", "jay", "nuthatch", "tree_sparrow"):
    t = tall.get(s); 
    if t: print(s, "tp", t.tp, "fp", t.fp, "fn", t.fn, "P", round(t.tp / max(t.tp + t.fp, 1), 3), "R", round(t.tp / max(t.tp + t.fn, 1), 3))
tp = sum(t.tp for t in tall.values()); fp = sum(t.fp for t in tall.values()); fn = sum(t.fn for t in tall.values())
print("val pooled P", round(tp / (tp + fp), 3), "R", round(tp / (tp + fn), 3), "frames", len(frames))
