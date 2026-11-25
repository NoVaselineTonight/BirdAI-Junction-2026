"""Ad-hoc: draw the weak-detection crops whose BioCLIP guess was jay/squirrel-like, at full size."""
import json
from pathlib import Path
import cv2
root = Path("data"); out = root / "check"
rows = [json.loads(l) for l in open(root / "labels/auto.jsonl")]
cand = [r for r in rows if r.get("status") != "empty" and r["box_conf"] < 0.35 and r["bioclip"]["species"] == "jay" and 0.30 <= r["bioclip"]["score"] <= 0.42]
print(len(cand), [(r["id"], round(r["bioclip"]["score"], 3), round(r["box_conf"], 2)) for r in cand[:20]])
for i, r in enumerate(cand[:6]):
    f = cv2.imread(str(root / "frames" / r["frame"]))
    x1, y1, x2, y2 = [int(v) for v in r["box"]]
    cx, cy = (x1 + x2) // 2, (y1 + y2) // 2
    c = f[max(0, cy - 300):cy + 300, max(0, cx - 400):cx + 400].copy()
    cv2.imwrite(str(out / f"sq{i}.jpg"), c, [cv2.IMWRITE_JPEG_QUALITY, 85])
