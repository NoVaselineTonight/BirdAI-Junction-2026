"""Ad-hoc: turn BioCLIP-only predictions into labels where the agreement rule gave up, and re-split.

Reads data/labels/auto.jsonl. Writes data/labels/v1.jsonl (12 Nov becomes the held-out `demo`
footage, 13 Nov becomes training footage) and data/review/corrections_v1.csv for build_dataset.py.

Rule for rows the teachers left as `unidentified` (status `review`):
  detector sure (box_conf >= 0.35) and BioCLIP sure (score >= 0.85, margin >= 0.6)  -> BioCLIP species
  detector unsure but BioCLIP near certain (score >= 0.95, margin >= 0.8)           -> BioCLIP species
  detector unsure and BioCLIP not certain                                           -> drop (mostly fat balls, snow)
  otherwise                                                                         -> stays unidentified
"""
import collections
import csv
import json
import sys
from pathlib import Path

root = Path("data")
src = sys.argv[1] if len(sys.argv) > 1 else "auto.jsonl"
tag = sys.argv[2] if len(sys.argv) > 2 else "v1"
held_out = "talvilintulive-20261112"
rows = [json.loads(line) for line in open(root / "labels" / src)]
for r in rows:
    r["split"] = "demo" if r["video"] == held_out else "train"
with open(root / "labels" / f"{tag}.jsonl", "w") as f:
    for r in rows:
        f.write(json.dumps(r) + "\n")

corrections = {}
for r in rows:
    if r.get("status") != "review":
        continue
    conf, score, margin = r["box_conf"], r["bioclip"]["score"], r["bioclip"]["margin"]
    if conf >= 0.35 and score >= 0.85 and margin >= 0.6:
        corrections[r["id"]] = r["bioclip"]["species"]
    elif conf < 0.35 and score >= 0.95 and margin >= 0.8:
        corrections[r["id"]] = r["bioclip"]["species"]
    elif conf < 0.35:
        corrections[r["id"]] = "drop"
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
