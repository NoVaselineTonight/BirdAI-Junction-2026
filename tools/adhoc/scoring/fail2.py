"""Ad-hoc: redraw failure tiles with every label box and every model box, and count double labels.

    python data/fail2.py <dataset> <fail dir>
"""
import json, random, sys
from collections import Counter, defaultdict
from pathlib import Path

import cv2
import numpy as np

dataset, out = Path(sys.argv[1]), Path(sys.argv[2])
rows = [json.loads(l) for l in (out / "records.jsonl").read_text().splitlines()]
labels = [r for r in rows if r["group"] != "false_alarm"]
alarms = [r for r in rows if r["group"] == "false_alarm"]
by_frame = defaultdict(list)
for r in labels:
    by_frame[r["frame"]].append(r)
al_frame = defaultdict(list)
for a in alarms:
    al_frame[a["frame"]].append(a)
random.seed(1)


def inter(a, b):
    w = min(a[2], b[2]) - max(a[0], b[0]); h = min(a[3], b[3]) - max(a[1], b[1])
    return max(w, 0) * max(h, 0)


def area(b):
    return (b[2] - b[0]) * (b[3] - b[1])


def kind(r):
    """Why a label was not matched, judged from the boxes alone."""
    b = r["box"]
    if r["h"] >= 330 or r["w"] >= 500:
        return "huge box (not one small bird)"
    best = None
    for o in by_frame[r["frame"]]:
        if o is r:
            continue
        cover = inter(b, o["box"]) / min(area(b), area(o["box"]))
        if cover >= 0.6 and (best is None or cover > best[0]):
            best = (cover, o)
    if best is not None:
        o = best[1]
        return "nested in another label, that one " + ("found" if o["group"] in ("hit", "unsure_right", "wrong_sure", "wrong_unsure") else "also missed")
    for a in al_frame[r["frame"]]:
        if inter(b, a["box"]) / min(area(b), area(a["box"])) >= 0.6:
            return "model box there but shaped differently"
    if r["overlap"] >= 0.1:
        return "touches another labelled bird"
    return "alone, no model box"


for g in ("not_seen", "poor_box"):
    c = Counter(kind(r) for r in labels if r["group"] == g)
    print(f"== {g}: {sum(c.values())} ==")
    for k, v in c.most_common():
        print(f"   {v:4d}  {k}")
    for r in labels:
        if r["group"] == g:
            r["kind"] = kind(r)
(out / "records2.jsonl").write_text("\n".join(json.dumps(r) for r in rows))

# labels per frame vs model boxes per frame for crowded spots: how many labels are nested pairs overall
pairs = 0
for f, rs in by_frame.items():
    for i, a in enumerate(rs):
        for b in rs[i + 1:]:
            if inter(a["box"], b["box"]) / min(area(a["box"]), area(b["box"])) >= 0.6:
                pairs += 1
print("nested label pairs on the whole day:", pairs, "of", len(labels), "labels")

T = 256
cache = {}


def img_of(stem):
    if stem not in cache:
        if len(cache) > 40:
            cache.clear()
        cache[stem] = cv2.imread(str(dataset / "images" / "test" / f"{stem}.jpg"))
    return cache[stem]


def tile(r):
    img = img_of(r["frame"])
    H, W = img.shape[:2]
    x0, y0, x1, y1 = r["box"]
    side = int(min(max(3.2 * max(x1 - x0, y1 - y0), 200), 900))
    cx, cy = (x0 + x1) / 2, (y0 + y1) / 2
    ax = int(min(max(cx - side / 2, 0), max(W - side, 0))); ay = int(min(max(cy - side / 2, 0), max(H - side, 0)))
    crop = img[ay:ay + side, ax:ax + side]
    s = T / max(crop.shape[0], crop.shape[1])
    crop = cv2.resize(crop, (int(crop.shape[1] * s), int(crop.shape[0] * s)), interpolation=cv2.INTER_AREA if s < 1 else cv2.INTER_CUBIC)
    canvas = np.zeros((T + 34, T, 3), np.uint8)
    canvas[:crop.shape[0], :crop.shape[1]] = crop

    def rect(b, colour, thick=1):
        cv2.rectangle(canvas[:T], (int((b[0] - ax) * s), int((b[1] - ay) * s)), (int((b[2] - ax) * s), int((b[3] - ay) * s)), colour, thick)

    for o in by_frame[r["frame"]]:  # other labels: thin white; their model boxes: yellow
        if o is not r:
            rect(o["box"], (255, 255, 255), 1)
        if o.get("pbox") and o["group"] != "poor_box":
            rect(o["pbox"], (0, 220, 255), 1)
    for a in al_frame[r["frame"]]:
        if a is not r:
            rect(a["box"], (0, 140, 255), 1)
    rect(r["box"], (255, 0, 255), 2)  # the one this tile is about: magenta
    if r["group"] == "poor_box" and r.get("pbox"):
        rect(r["pbox"], (0, 140, 255), 2)
    if r["group"] == "false_alarm":
        l1, l2 = f"M {r['species'][:14]} {r['conf']:.2f}", f"{int(r['w'])}x{int(r['h'])}"
    else:
        l1, l2 = f"L {r['species'][:12]} {int(r['w'])}x{int(r['h'])}", r.get("kind", "")[:36]
    cv2.putText(canvas, l1, (2, T + 13), cv2.FONT_HERSHEY_SIMPLEX, 0.4, (255, 255, 255), 1, cv2.LINE_AA)
    cv2.putText(canvas, l2, (2, T + 28), cv2.FONT_HERSHEY_SIMPLEX, 0.36, (0, 220, 255), 1, cv2.LINE_AA)
    return canvas


def sheets(name, items, per_sheet=35, cols=7, max_sheets=2):
    items = list(items)
    random.shuffle(items)
    for k in range(min(max_sheets, (len(items) + per_sheet - 1) // per_sheet)):
        part = items[k * per_sheet:(k + 1) * per_sheet]
        n_rows = (len(part) + cols - 1) // cols
        sheet = np.zeros((n_rows * (T + 38), cols * (T + 4), 3), np.uint8)
        for j, r in enumerate(part):
            t = tile(r)
            yy, xx = (j // cols) * (T + 38), (j % cols) * (T + 4)
            sheet[yy:yy + t.shape[0], xx:xx + T] = t
        cv2.imwrite(str(out / f"{name}-{k + 1}.jpg"), sheet, [cv2.IMWRITE_JPEG_QUALITY, 88])
    print("sheets", name, len(items))


for old in out.glob("*.jpg"):
    if old.name.startswith(("not_seen", "poor_box", "false_alarm")):
        old.unlink()
ns = [r for r in labels if r["group"] == "not_seen"]
for k in sorted({r["kind"] for r in ns}):
    sheets("notseen-" + k.split(",")[0].split("(")[0].strip().replace(" ", "_"), [r for r in ns if r["kind"] == k], max_sheets=1)
sheets("poor_box", [r for r in labels if r["group"] == "poor_box"], max_sheets=1)
sheets("false_alarm", alarms, max_sheets=4)
print("done")
