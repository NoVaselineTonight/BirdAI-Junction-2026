"""Ad-hoc: sample sheets of the checker's decisions. python data/sheet2.py <dataset> <check dir> <out dir>"""
import json, random, sys, importlib.util
from pathlib import Path
import cv2, numpy as np
sys.argv = [sys.argv[0], sys.argv[1], sys.argv[2], "/tmp/unused"] + sys.argv[3:]
spec = importlib.util.spec_from_file_location("truth", "data/truth.py"); T = importlib.util.module_from_spec(spec); spec.loader.exec_module(T)
check, out = Path(sys.argv[2]), Path(sys.argv[4]); out.mkdir(parents=True, exist_ok=True)
random.seed(3)
groups = {"added": [], "ignored": [], "changed": [], "dropped": [], "named_from_unidentified": [], "same": []}
for cs in T.by_frame.values():
    for c in cs:
        kind, sp = T.decide(c)
        had = next((x["species"] for x in c["votes"] if x["src"] == "label"), None)
        c["_d"] = (kind, sp)
        if kind == "drop": groups["dropped"].append(c)
        elif kind == "ignore": groups["ignored"].append(c)
        elif had is None: groups["added"].append(c)
        elif had == "unidentified": groups["named_from_unidentified"].append(c)
        elif had != sp: groups["changed"].append(c)
        else: groups["same"].append(c)
S = 224
for name, items in groups.items():
    random.shuffle(items); items = items[:40]
    if not items: continue
    cols = 8; rows = (len(items) + cols - 1) // cols
    sheet = np.zeros((rows * (S + 50), cols * (S + 4), 3), np.uint8)
    for j, c in enumerate(items):
        im = cv2.imread(str(check / "crops" / f"{c['id']}.jpg"))
        s = S / max(im.shape[:2]); im = cv2.resize(im, (int(im.shape[1] * s), int(im.shape[0] * s)))
        y, x = (j // cols) * (S + 50), (j % cols) * (S + 4)
        sheet[y:y + im.shape[0], x:x + im.shape[1]] = im
        cv2.circle(sheet, (x + im.shape[1] // 2, y + im.shape[0] // 2), 3, (255, 0, 255), -1)
        v = T.verdicts.get(c["id"], {})
        lab = next((q["species"] for q in c["votes"] if q["src"] == "label"), "-")
        tea = next((q["species"] for q in c["votes"] if q["src"] == "teacher"), "-")
        stu = ",".join(sorted({q["species"][:8] for q in c["votes"] if q["src"].startswith("s")})) or "-"
        for k, (txt, col) in enumerate([(f"-> {c['_d'][0]} {c['_d'][1] or ''}", (255, 255, 255)), (f"J {v.get('what','?')[:9]} {v.get('species','?')[:11]} {v.get('sure','')}", (0, 220, 255)), (f"L {lab[:9]} T {tea[:9]} S {stu[:14]}", (180, 180, 180))]):
            cv2.putText(sheet, txt, (x + 2, y + S + 13 + 15 * k), cv2.FONT_HERSHEY_SIMPLEX, 0.36, col, 1, cv2.LINE_AA)
    cv2.imwrite(str(out / f"decision-{name}.jpg"), sheet, [cv2.IMWRITE_JPEG_QUALITY, 88])
    print(name, len(groups[name]))
