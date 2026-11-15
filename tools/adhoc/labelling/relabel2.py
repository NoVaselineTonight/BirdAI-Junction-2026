"""Ad-hoc: second labelling pass (ruling R31). Uses the bird-or-not score to remove non-birds.

    python data/relabel2.py <tag> <cut> <labels.jsonl> [<labels.jsonl> ...]

Each labels file must have a sibling <file>.birdness.json (from birdness.py). Writes
data/labels/<tag>.jsonl (all inputs joined, split set: 12 Nov = held-out `demo`, everything else
`train`) and data/review/corrections_<tag>.csv for build_dataset.py.

Rule per box:
  bird-or-not score < cut                                     -> drop (fat balls, snow, hooks)
  both teachers agreed (status auto)                          -> keep their species
  BioCLIP score >= 0.6 and margin >= 0.3                      -> BioCLIP species
  otherwise                                                   -> unidentified (a bird we cannot name)
Videos whose name starts with `catv-` are not from Finland: a willow tit there may be another
species of tit, so those become unidentified.
"""
import collections
import csv
import json
import sys
from pathlib import Path

root = Path("data")
tag, cut = sys.argv[1], float(sys.argv[2])
held_out = "talvilintulive-20261112"
rows, birdness = [], {}
for name in sys.argv[3:]:
    rows += [json.loads(line) for line in open(name)]
    birdness.update(json.loads(Path(name + ".birdness.json").read_text()))
seen = set()
for r in rows:
    assert r["id"] not in seen, f"duplicate id {r['id']}"
    seen.add(r["id"])
    r["split"] = "demo" if r["video"] == held_out else "train"
with open(root / "labels" / f"{tag}.jsonl", "w") as f:
    for r in rows:
        f.write(json.dumps(r) + "\n")

corrections = {}
for r in rows:
    if r.get("status") == "empty":
        continue
    label = r["label"]
    if birdness[r["id"]] < cut:
        new = "drop"
    elif r.get("status") == "auto":
        new = label
    elif r["bioclip"]["score"] >= 0.6 and r["bioclip"]["margin"] >= 0.3:
        new = r["bioclip"]["species"]
    else:
        new = "unidentified"
    if r["video"].startswith("catv-") and new == "willow_tit":
        new = "unidentified"
    if new != label:
        corrections[r["id"]] = new
with open(root / "review" / f"corrections_{tag}.csv", "w", newline="") as f:
    w = csv.writer(f)
    w.writerow(["id", "label"])
    w.writerows(sorted(corrections.items()))

final = collections.defaultdict(collections.Counter)
for r in rows:
    if r.get("status") == "empty":
        final[r["split"]]["(empty frame)"] += 1
        continue
    final[r["split"]][corrections.get(r["id"], r["label"])] += 1
for split in ("train", "demo"):
    print(split, sum(final[split].values()), sorted(final[split].items(), key=lambda kv: -kv[1]))
print("corrections:", len(corrections), "of which drop:", sum(1 for v in corrections.values() if v == "drop"))
