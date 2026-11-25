import json, sys
from pathlib import Path
sys.path.insert(0, "tools"); sys.path.insert(0, ".")
import evaluate as ev
from feeder_census.detectors import build_detector
from feeder_census.species import load_species
ds = Path("data/dataset_v8"); classes = json.loads((ds / "classes.json").read_text())
for name, d in (("new 640", "models_v8/student"), ("old 640", "models_v4/student")):
    det = build_detector("student", Path("models"), load_species(), student_dir=Path(d))
    frames, _ = ev.run_split(det, ds, "test", classes)
    n = sum(1 for p, _ in frames for x in p if x.species == "unidentified"); a = sum(len(p) for p, _ in frames)
    print(name, "predictions", a, "of them unidentified", n)
