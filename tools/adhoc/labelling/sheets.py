"""Ad-hoc check: per-day counts of BioCLIP-only labels and sample contact sheets per BioCLIP species."""
import collections
import json
import random
from pathlib import Path

import cv2
import numpy as np

root = Path("data")
out = root / "check"
out.mkdir(exist_ok=True)
random.seed(7)
rows = [json.loads(line) for line in open(root / "labels/auto.jsonl")]
boxes = [r for r in rows if r.get("status") != "empty"]


def strict(r):
    return r["bioclip"]["score"] >= 0.85 and r["bioclip"]["margin"] >= 0.6 and r["box_conf"] >= 0.35


per = collections.defaultdict(collections.Counter)
for r in boxes:
    per[r["video"][-8:]][r["bioclip"]["species"] if strict(r) else "~unsure"] += 1
species = sorted({k for c in per.values() for k in c})
lines = ["day      " + " ".join(f"{s[:9]:>9}" for s in species)]
for day in sorted(per):
    frames = len({r["frame"] for r in boxes if r["video"][-8:] == day and strict(r)})
    lines.append(f"{day} " + " ".join(f"{per[day][s]:>9}" for s in species) + f"  frames with sure boxes: {frames}")


def sheet(name, items, n=48, cols=8, size=150):
    items = random.sample(items, min(n, len(items)))
    tiles = []
    for r in items:
        frame = cv2.imread(str(root / "frames" / r["frame"]))
        x1, y1, x2, y2 = [int(v) for v in r["box"]]
        pad = int(0.15 * max(x2 - x1, y2 - y1))
        crop = frame[max(0, y1 - pad):y2 + pad, max(0, x1 - pad):x2 + pad]
        h, w = crop.shape[:2]
        scale = size / max(h, w)
        crop = cv2.resize(crop, (max(1, int(w * scale)), max(1, int(h * scale))))
        tile = np.full((size, size, 3), 40, np.uint8)
        tile[:crop.shape[0], :crop.shape[1]] = crop
        text = f"{r['bioclip']['species'][:6]} {r['bioclip']['score']:.2f}"
        cv2.putText(tile, text, (3, size - 5), cv2.FONT_HERSHEY_SIMPLEX, 0.4, (0, 255, 255), 1)
        tiles.append(tile)
    while len(tiles) % cols:
        tiles.append(np.full((size, size, 3), 40, np.uint8))
    grid = np.vstack([np.hstack(tiles[i:i + cols]) for i in range(0, len(tiles), cols)])
    cv2.imwrite(str(out / f"{name}.jpg"), grid, [cv2.IMWRITE_JPEG_QUALITY, 82])
    lines.append(f"sheet {name}: {len(items)} crops")


for s in ("great_tit", "blue_tit", "magpie", "bullfinch", "tree_sparrow", "jay", "great_spotted_woodpecker",
          "house_sparrow", "nuthatch", "crested_tit", "willow_tit"):
    sheet(s, [r for r in boxes if strict(r) and r["bioclip"]["species"] == s])
sheet("lowbox", [r for r in boxes if r["box_conf"] < 0.35])
sheet("unsure", [r for r in boxes if r["box_conf"] >= 0.35 and not strict(r)])
sheet("demo_sure", [r for r in boxes if strict(r) and r["split"] == "demo"])
(out / "summary.txt").write_text("\n".join(lines) + "\nDONE\n")
