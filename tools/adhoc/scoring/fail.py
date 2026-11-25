"""Ad-hoc: where does a student still fail on the held-out frames?

    PYTHONPATH=. python data/fail.py <dataset> <student dir> <out dir> [cut-off]

Every labelled bird of the test split lands in one group: hit, unsure_right, wrong_sure, wrong_unsure, poor_box,
not_seen. Every sure prediction that matches no label is a false alarm. Prints breakdowns, writes records.jsonl,
contact sheets of crops per group and full frames with both sets of boxes.
"""
import json, random, sys
from collections import Counter, defaultdict
from pathlib import Path

import cv2
import numpy as np

sys.path.insert(0, "tools"); sys.path.insert(0, ".")
import evaluate as ev
from feeder_census.detectors import build_detector
from feeder_census.species import load_species

dataset, student_dir, out = Path(sys.argv[1]), Path(sys.argv[2]), Path(sys.argv[3])
CUT = float(sys.argv[4]) if len(sys.argv) > 4 else 0.5
out.mkdir(parents=True, exist_ok=True)
classes = json.loads((dataset / "classes.json").read_text())
det = build_detector("student", Path("models"), load_species(), student_dir=student_dir)
random.seed(0)


def sharp(img, box):
    x0, y0, x1, y1 = [int(round(v)) for v in box]
    crop = img[max(y0, 0):max(y1, 1), max(x0, 0):max(x1, 1)]
    if crop.size == 0:
        return 0.0, 0.0, 0.0
    g = cv2.cvtColor(crop, cv2.COLOR_BGR2GRAY)
    # contrast against the ring around the box: how much the bird stands out
    px0, py0 = max(x0 - (x1 - x0) // 2, 0), max(y0 - (y1 - y0) // 2, 0)
    ring = cv2.cvtColor(img[py0:y1 + (y1 - y0) // 2, px0:x1 + (x1 - x0) // 2], cv2.COLOR_BGR2GRAY)
    return float(cv2.Laplacian(g, cv2.CV_64F).var()), float(g.mean()), float(abs(float(g.mean()) - float(ring.mean())))


records, alarms, frames_info = [], [], []
paths = sorted((dataset / "images" / "test").glob("*.jpg"))
for n, path in enumerate(paths):
    img = cv2.imread(str(path))
    H, W = img.shape[:2]
    truth = ev.read_truth(dataset / "labels" / "test" / f"{path.stem}.txt", (W, H), classes)
    pred = det.detect(img)
    named = [t for t in truth if t.species != "unidentified"]
    unknown = [t for t in truth if t.species == "unidentified"]
    free = list(range(len(named)))
    match = {}  # truth index -> pred
    loose = {}
    left = []
    for p in sorted(pred, key=lambda d: -d.confidence):
        cands = [(ev.box_iou(p, named[i]), i) for i in free]
        cands = [c for c in cands if c[0] >= 0.5]
        if cands:
            _, i = max(cands)
            free.remove(i)
            match[i] = p
        else:
            left.append(p)
    for i in free:
        best = max(((ev.box_iou(p, named[i]), p) for p in left), key=lambda c: c[0], default=(0.0, None))
        if best[0] >= 0.1:
            loose[i] = best
    for i, t in enumerate(named):
        x0, y0, x1, y1 = t.box
        w, h = x1 - x0, y1 - y0
        p = match.get(i)
        if p is not None:
            right = p.species == t.species
            sure = p.confidence >= CUT
            group = ("hit" if sure else "unsure_right") if right else ("wrong_sure" if sure else "wrong_unsure")
        elif i in loose:
            group, p = "poor_box", loose[i][1]
        else:
            group = "not_seen"
        lap, bright, contrast = sharp(img, t.box)
        others = [ev.box_iou(t, o) for j, o in enumerate(named) if j != i]
        records.append(dict(
            frame=path.stem, group=group, species=t.species, w=round(w, 1), h=round(h, 1), box=[round(v, 1) for v in t.box],
            pred=None if p is None else p.species, conf=None if p is None else round(p.confidence, 3),
            pbox=None if p is None else [round(v, 1) for v in p.box],
            lap=round(lap, 1), bright=round(bright, 1), contrast=round(contrast, 1), n_in_frame=len(named),
            overlap=round(max(others, default=0.0), 2), edge=bool(x0 < 4 or y0 < 4 or x1 > W - 4 or y1 > H - 4),
            cx=round((x0 + x1) / 2 / W, 3), cy=round((y0 + y1) / 2 / H, 3), W=W, H=H))
    used = {id(p) for p in match.values()} | {id(v[1]) for v in loose.values()}
    for p in left:
        if p.confidence < CUT or p.species == "unidentified":
            continue
        if any(ev.iou(p.box, u.box) >= 0.5 for u in unknown):
            continue
        near = max((ev.box_iou(p, t) for t in named), default=0.0)
        x0, y0, x1, y1 = p.box
        alarms.append(dict(frame=path.stem, group="false_alarm", species=p.species, conf=round(p.confidence, 3),
                           box=[round(v, 1) for v in p.box], w=round(x1 - x0, 1), h=round(y1 - y0, 1),
                           near=round(near, 2), dup=id(p) in used, W=W, H=H))
    if n % 100 == 0:
        print("frame", n, len(paths), flush=True)

(out / "records.jsonl").write_text("\n".join(json.dumps(r) for r in records + alarms))

# ---------- numbers ----------
G = ["hit", "unsure_right", "wrong_sure", "wrong_unsure", "poor_box", "not_seen"]


def table(title, key, order=None):
    rows = defaultdict(Counter)
    for r in records:
        rows[key(r)][r["group"]] += 1
    print(f"\n== {title} ==")
    print(f"{'':28s}" + "".join(f"{g:>13s}" for g in G) + f"{'total':>8s}{'hit%':>7s}")
    for k in (order or sorted(rows, key=lambda k: -sum(rows[k].values()))):
        if k not in rows:
            continue
        c = rows[k]; tot = sum(c.values())
        print(f"{str(k):28s}" + "".join(f"{c[g]:13d}" for g in G) + f"{tot:8d}{100 * c['hit'] / tot:7.1f}")


def bucket(v, edges, names):
    for e, nm in zip(edges, names):
        if v < e:
            return nm
    return names[-1]


print("frames", len(paths), "labelled birds", len(records), "false alarms", len(alarms), "frame size", records[0]["W"], records[0]["H"])
table("all", lambda r: "all")
table("by species", lambda r: r["species"])
SZ = ["<16px", "16-24", "24-32", "32-48", "48-72", "72-120", ">=120"]
table("by smaller side of the box (pixels in the full frame)", lambda r: bucket(min(r["w"], r["h"]), [16, 24, 32, 48, 72, 120], SZ), SZ)
table("by longer side of the box", lambda r: bucket(max(r["w"], r["h"]), [16, 24, 32, 48, 72, 120], SZ), SZ)
laps = sorted(r["lap"] for r in records)
q = [laps[len(laps) * i // 4] for i in (1, 2, 3)]
LQ = ["blurriest quarter", "2nd", "3rd", "sharpest quarter"]
table(f"by sharpness (Laplacian variance, quartile edges {q})", lambda r: bucket(r["lap"], q, LQ), LQ)
cons = sorted(r["contrast"] for r in records)
qc = [cons[len(cons) * i // 4] for i in (1, 2, 3)]
CQ = ["least contrast", "2nd", "3rd", "most contrast"]
table(f"by contrast with surroundings (quartile edges {qc})", lambda r: bucket(r["contrast"], qc, CQ), CQ)
NB = ["1 bird", "2-3", "4-6", "7+"]
table("by birds in the frame", lambda r: bucket(r["n_in_frame"], [2, 4, 7], NB), NB)
table("by overlap with another labelled bird", lambda r: "overlaps (IoU>=0.1)" if r["overlap"] >= 0.1 else "alone")
table("at the picture edge", lambda r: "edge" if r["edge"] else "inside")
table("by position (column of the frame)", lambda r: f"x {int(r['cx'] * 4)}/4", [f"x {i}/4" for i in range(4)])
table("by position (row of the frame)", lambda r: f"y {int(r['cy'] * 3)}/3", [f"y {i}/3" for i in range(3)])
table("by hour of the stream", lambda r: f"hour {int(r['frame'].rsplit('_', 1)[1]) // 3600000:02d}",
      sorted({f"hour {int(r['frame'].rsplit('_', 1)[1]) // 3600000:02d}" for r in records}))
print("\n== wrong names (label -> model), sure and unsure ==")
conf = Counter((r["species"], r["pred"], r["group"]) for r in records if r["group"].startswith("wrong"))
for (a, b, g), c in conf.most_common(25):
    print(f"  {a:26s} -> {b:26s} {g:13s} {c}")
print("\n== false alarms (sure predictions with no label under them) ==")
fa = Counter((a["species"], "near a label (IoU .1-.5)" if a["near"] >= 0.1 else "nothing labelled there") for a in alarms)
for k, c in fa.most_common():
    print("  ", k, c)
print("  size of false alarms, smaller side:", Counter(bucket(min(a["w"], a["h"]), [16, 24, 32, 48, 72, 120], SZ) for a in alarms).most_common())
print("\n== unsure_right: confidence spread ==", Counter(round(r["conf"], 1) for r in records if r["group"] == "unsure_right").most_common())
# frames: which kind of error breaks the exact count
per = defaultdict(Counter)
for r in records:
    per[r["frame"]][r["group"]] += 1
for a in alarms:
    per[a["frame"]]["false_alarm"] += 1
bad = {f: c for f, c in per.items() if any(c[g] for g in c if g != "hit")}
print("\n== frames ==", "with a labelled bird:", len(per), "with at least one problem:", len(bad))
only = Counter()
for f, c in bad.items():
    kinds = tuple(sorted(g for g in c if g != "hit" and c[g]))
    only[kinds] += 1
for k, c in only.most_common(12):
    print("  ", c, k)

# ---------- pictures ----------
cache = {}


def frame_img(stem):
    if stem not in cache:
        if len(cache) > 40:
            cache.clear()
        cache[stem] = cv2.imread(str(dataset / "images" / "test" / f"{stem}.jpg"))
    return cache[stem]


T = 224


def tile(r):
    img = frame_img(r["frame"])
    H, W = img.shape[:2]
    x0, y0, x1, y1 = r["box"]
    side = int(max(3 * max(x1 - x0, y1 - y0), 110))
    cx, cy = (x0 + x1) / 2, (y0 + y1) / 2
    ax = int(min(max(cx - side / 2, 0), max(W - side, 0))); ay = int(min(max(cy - side / 2, 0), max(H - side, 0)))
    crop = img[ay:ay + side, ax:ax + side]
    s = T / max(crop.shape[0], crop.shape[1])
    crop = cv2.resize(crop, (int(crop.shape[1] * s), int(crop.shape[0] * s)), interpolation=cv2.INTER_CUBIC)
    canvas = np.zeros((T + 34, T, 3), np.uint8)
    canvas[:crop.shape[0], :crop.shape[1]] = crop

    def rect(b, colour):
        cv2.rectangle(canvas, (int((b[0] - ax) * s), int((b[1] - ay) * s)), (int((b[2] - ax) * s), int((b[3] - ay) * s)), colour, 1)

    if r["group"] != "false_alarm":
        rect(r["box"], (255, 255, 255))
        if r.get("pbox"):
            rect(r["pbox"], (0, 220, 255))
        l1 = f"L {r['species'][:14]} {int(r['w'])}x{int(r['h'])}"
        l2 = "M -" if r["pred"] is None else f"M {r['pred'][:14]} {r['conf']:.2f}"
    else:
        rect(r["box"], (0, 220, 255))
        l1 = f"M {r['species'][:14]} {r['conf']:.2f}"
        l2 = f"{int(r['w'])}x{int(r['h'])} near {r['near']:.1f}"
    cv2.putText(canvas, l1, (2, T + 13), cv2.FONT_HERSHEY_SIMPLEX, 0.4, (255, 255, 255), 1, cv2.LINE_AA)
    cv2.putText(canvas, l2, (2, T + 28), cv2.FONT_HERSHEY_SIMPLEX, 0.4, (0, 220, 255), 1, cv2.LINE_AA)
    return canvas


def sheets(name, items, per_sheet=48, cols=8, max_sheets=2):
    items = list(items)
    random.shuffle(items)
    for k in range(min(max_sheets, (len(items) + per_sheet - 1) // per_sheet)):
        part = items[k * per_sheet:(k + 1) * per_sheet]
        rows = (len(part) + cols - 1) // cols
        sheet = np.zeros((rows * (T + 38), cols * (T + 4), 3), np.uint8)
        for j, r in enumerate(part):
            t = tile(r)
            yy, xx = (j // cols) * (T + 38), (j % cols) * (T + 4)
            sheet[yy:yy + t.shape[0], xx:xx + T] = t
        cv2.imwrite(str(out / f"{name}-{k + 1}.jpg"), sheet, [cv2.IMWRITE_JPEG_QUALITY, 88])
    print("sheets", name, len(items))


by = defaultdict(list)
for r in records:
    by[r["group"]].append(r)
sheets("not_seen", by["not_seen"], max_sheets=3)
sheets("poor_box", by["poor_box"], max_sheets=1)
sheets("wrong_sure", by["wrong_sure"], max_sheets=2)
sheets("wrong_unsure", by["wrong_unsure"], max_sheets=1)
sheets("unsure_right", by["unsure_right"], max_sheets=2)
sheets("false_alarm", alarms, max_sheets=2)
sheets("hit", by["hit"], max_sheets=1)
for sp in ("blue_tit", "magpie", "bullfinch", "great_spotted_woodpecker"):
    sheets(f"missed-{sp}", [r for r in records if r["species"] == sp and r["group"] != "hit"], max_sheets=1)

# full frames with both sets of boxes: the frames with the most problems
worst = sorted(bad, key=lambda f: -sum(v for g, v in bad[f].items() if g != "hit"))
pick = worst[:12] + random.sample(worst[12:], min(18, max(len(worst) - 12, 0)))
COL = {"hit": (80, 200, 80), "unsure_right": (0, 200, 255), "wrong_sure": (0, 0, 255), "wrong_unsure": (0, 120, 255),
       "poor_box": (255, 0, 255), "not_seen": (255, 255, 255), "false_alarm": (0, 0, 255)}
(out / "frames").mkdir(exist_ok=True)
for f in pick:
    img = frame_img(f).copy()
    for r in [r for r in records if r["frame"] == f] + [a for a in alarms if a["frame"] == f]:
        b = [int(v) for v in r["box"]]
        c = COL[r["group"]]
        cv2.rectangle(img, (b[0], b[1]), (b[2], b[3]), c, 2)
        text = {"hit": "", "not_seen": "not seen: " + r["species"], "false_alarm": "false: " + r["species"],
                "poor_box": "poor box: " + r["species"], "unsure_right": f"unsure {r.get('conf') or 0:.2f}: " + r["species"],
                }.get(r["group"], f"{r['species']} named {r.get('pred')}")
        if text:
            cv2.putText(img, text, (b[0], max(b[1] - 5, 12)), cv2.FONT_HERSHEY_SIMPLEX, 0.5, (0, 0, 0), 3, cv2.LINE_AA)
            cv2.putText(img, text, (b[0], max(b[1] - 5, 12)), cv2.FONT_HERSHEY_SIMPLEX, 0.5, c, 1, cv2.LINE_AA)
    cv2.imwrite(str(out / "frames" / f"{f}.jpg"), img, [cv2.IMWRITE_JPEG_QUALITY, 88])
print("done", len(pick), "frames")
