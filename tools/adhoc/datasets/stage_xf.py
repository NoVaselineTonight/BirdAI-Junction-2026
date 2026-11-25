"""Ad-hoc: stage teacher-labelled frames of other feeders as a one-split dataset for the machine check.

    python data/stage_xf.py data/dataset_xf data/labels/auto_xf1.jsonl:data/frames_xf1 [more jsonl:framesdir ...]

Frames are hard-linked to <out>/images/train/<stem>.jpg, labels written in YOLO text format with the class list of
data/dataset_v8. A teacher label that is not one of those classes becomes `unidentified` (the check decides later).
"""
import json, os, shutil, sys
from collections import Counter, defaultdict
from pathlib import Path
from PIL import Image

out = Path(sys.argv[1])
classes = json.loads(Path("data/dataset_v8/classes.json").read_text()); UN = classes.index("unidentified")
(out / "images/train").mkdir(parents=True, exist_ok=True); (out / "labels/train").mkdir(parents=True, exist_ok=True)
shutil.copy("data/dataset_v8/classes.json", out / "classes.json")
(out / "data.yaml").write_text(Path("data/dataset_v8/data.yaml").read_text().replace(str(Path("data/dataset_v8").resolve()), str(out.resolve())))
st = Counter()
for spec in sys.argv[2:]:
    jl, frames = spec.split(":"); frames = Path(frames)
    by = defaultdict(list)
    for line in open(jl):
        r = json.loads(line); by[r["frame"]].append(r)
    for frame, rows in by.items():
        src = frames / frame; stem = Path(frame).stem
        if not src.exists():
            st["frame missing"] += 1; continue
        W, H = Image.open(src).size
        dst = out / "images/train" / f"{stem}.jpg"
        if not dst.exists():
            os.link(src, dst)
        lines = []
        for r in rows:
            if not r.get("box"):
                continue
            x1, y1, x2, y2 = r["box"]; x1, y1, x2, y2 = max(x1, 0), max(y1, 0), min(x2, W), min(y2, H)
            if x2 <= x1 or y2 <= y1:
                continue
            c = classes.index(r["label"]) if r.get("label") in classes else UN
            st["box " + (classes[c] if c != UN else "unidentified")] += 1
            lines.append(f"{c} {(x1 + x2) / 2 / W:.6f} {(y1 + y2) / 2 / H:.6f} {(x2 - x1) / W:.6f} {(y2 - y1) / H:.6f}")
        (out / "labels/train" / f"{stem}.txt").write_text("\n".join(lines) + ("\n" if lines else ""))
        st["frames"] += 1; st["frames with a box" if lines else "empty frames"] += 1
print(json.dumps(dict(st.most_common()), indent=1))
