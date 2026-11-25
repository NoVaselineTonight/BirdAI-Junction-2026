import sys, json, importlib.util, collections
from pathlib import Path
sys.argv = ["x", "data/dataset_v5", "data/check_train", "/tmp/unused"]
spec = importlib.util.spec_from_file_location("truth", "data/truth.py"); T = importlib.util.module_from_spec(spec); spec.loader.exec_module(T)
kept = collections.Counter(); days = collections.Counter()
for stem, cs in T.by_frame.items():
    for c in cs:
        kind, sp = T.decide(c)
        if kind == "keep":
            kept[sp] += 1
            if sp == "red_squirrel": days[stem.split("_")[0]] += 1
print("kept by species (feeder-camera train frames):", dict(kept.most_common()))
print("real squirrel boxes by day:", dict(sorted(days.items())))
