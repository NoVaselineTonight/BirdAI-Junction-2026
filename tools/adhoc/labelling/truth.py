"""Ad-hoc: turn candidates + the judge's verdicts into checked labels.

    python data/truth.py <dataset> <check dir> <out dataset> <split> [<split> ...] [--procs N]

Feeder-camera frames (stem starts with talvilintulive-): every label comes from a candidate.
  - judge says no animal: dropped (kept as an ignore zone only when label, teacher and two students all saw a bird);
  - judge says part of a bird / several birds: ignore zone;
  - one bird: the species needs two agreeing votes among the old label, the camera-tuned teacher (conf >= 0.4) and
    the judge (only when it says it is sure); the students' majority (conf >= 0.25) counts as one supporting vote.
    No two agreeing votes: ignore zone.
Other frames (photos, documentary, forest feeders, pasted squirrels): labels kept; `unidentified` boxes are ignore zones.
Test split: ignore zones are written as `unidentified` boxes (the scorer skips them).
Train/val: no `unidentified` label is written. The ignore zone is blurred out of a copy of the image; when it
overlaps a kept bird the whole frame is left out.
"""
import json, os, sys
from collections import Counter, defaultdict
from multiprocessing import Pool
from pathlib import Path

import cv2

cv2.setNumThreads(1)

args = [a for i, a in enumerate(sys.argv[1:]) if not a.startswith("--") and sys.argv[i] != "--procs"]
src, check, dst = Path(args[0]), Path(args[1]), Path(args[2])
splits = args[3:]
procs = int(sys.argv[sys.argv.index("--procs") + 1]) if "--procs" in sys.argv else 32
classes = json.loads((src / "classes.json").read_text())
UN = classes.index("unidentified")
REAL = set(classes) - {"unidentified"}

verdicts = {}
for f in check.glob("verdicts*.jsonl"):
    if "prompt1" in f.name:
        continue
    for l in f.read_text().splitlines():
        if l.strip():
            r = json.loads(l)
            verdicts[r["id"]] = r
by_frame = defaultdict(list)
for f in sorted(check.glob("cands-*.jsonl")):
    for l in f.read_text().splitlines():
        c = json.loads(l)
        by_frame[c["frame"]].append(c)


def decide(c):
    """-> (kind, species): kind is 'keep', 'ignore' or 'drop'."""
    v = verdicts.get(c["id"])
    votes = c["votes"]
    lab = next((x["species"] for x in votes if x["src"] == "label" and x["species"] in REAL), None)
    tea = next((x["species"] for x in sorted(votes, key=lambda x: -x["conf"]) if x["src"] == "teacher" and x["species"] in REAL and x["conf"] >= 0.4), None)
    stu = Counter(x["species"] for x in votes if x["src"].startswith("s") and x["species"] in REAL and x["conf"] >= 0.25)
    stu = stu.most_common(1)[0][0] if stu else None
    n_students = len({x["src"] for x in votes if x["src"].startswith("s")})
    has_label = any(x["src"] == "label" for x in votes)
    has_teacher = any(x["src"] == "teacher" for x in votes)
    if v is None:
        return "ignore", None
    if v["what"] == "no_animal":
        return ("ignore", None) if (has_label and has_teacher and n_students >= 2) else ("drop", None)
    if v["what"] in ("part_of_a_bird", "two_or_more_birds"):
        return "ignore", None
    jud = None
    if v["what"] == "squirrel":
        jud = "red_squirrel"
    elif v["sure"] == "yes" and v["species"] in REAL:
        jud = v["species"]
    tally = Counter(s for s in (lab, tea, jud) if s)
    if stu:
        tally[stu] += 1
    if not tally:
        return "ignore", None
    (top, n), *rest = tally.most_common(2)
    if n >= 2 and not (rest and rest[0][1] >= 2):
        return "keep", top
    return "ignore", None


def frame(job):
    split, stem = job
    img_src = src / "images" / split / f"{stem}.jpg"
    img_dst = dst / "images" / split / f"{stem}.jpg"
    lab_dst = dst / "labels" / split / f"{stem}.txt"
    st = Counter()
    keep, ignore = [], []  # (class index, x0, y0, x1, y1) in pixels / normalised rows
    W = H = None
    if stem.startswith("talvilintulive-"):
        for c in by_frame.get(stem, []):
            W, H = c["W"], c["H"]
            kind, sp = decide(c)
            st[kind] += 1
            had = next((x["species"] for x in c["votes"] if x["src"] == "label"), None)
            if kind == "keep":
                keep.append((classes.index(sp), *c["box"]))
                st["kept, no old label" if had is None else ("kept, same as old label" if had == sp else "kept, old label said " + ("unidentified" if had == "unidentified" else "another species"))] += 1
            elif kind == "ignore":
                ignore.append((UN, *c["box"]))
                if had in REAL:
                    st["old named label now ignored"] += 1
            elif had is not None:
                st["old label dropped as no animal"] += 1
        rows = lambda items: "".join(f"{k} {(a + c2) / 2 / W:.6f} {(b + d) / 2 / H:.6f} {(c2 - a) / W:.6f} {(d - b) / H:.6f}\n" for k, a, b, c2, d in items)
    else:
        text = (src / "labels" / split / f"{stem}.txt")
        lines = [l.split() for l in (text.read_text().splitlines() if text.exists() else []) if len(l.split()) >= 5]
        keep_l = [l for l in lines if int(l[0]) != UN]
        ign_l = [l for l in lines if int(l[0]) == UN]
        if split == "test" or not ign_l:
            lab_dst.write_text("".join(" ".join(l[:5]) + "\n" for l in (lines if split == "test" else keep_l)))
            if not img_dst.exists():
                os.link(img_src, img_dst)
            st["other-source frame"] += 1
            return st
        img = cv2.imread(str(img_src)); H, W = img.shape[:2]
        px = lambda l: (int(l[0]), (float(l[1]) - float(l[3]) / 2) * W, (float(l[2]) - float(l[4]) / 2) * H, (float(l[1]) + float(l[3]) / 2) * W, (float(l[2]) + float(l[4]) / 2) * H)
        keep, ignore = [px(l) for l in keep_l], [px(l) for l in ign_l]
        rows = lambda items: "".join(f"{k} {(a + c2) / 2 / W:.6f} {(b + d) / 2 / H:.6f} {(c2 - a) / W:.6f} {(d - b) / H:.6f}\n" for k, a, b, c2, d in items)
        st["other-source frame"] += 1
    if split == "test":
        lab_dst.write_text(rows(keep + ignore) if (keep or ignore) else "")
        if not img_dst.exists():
            os.link(img_src, img_dst)
        return st
    if not ignore:
        lab_dst.write_text(rows(keep) if keep else "")
        if not img_dst.exists():
            os.link(img_src, img_dst)
        st["train frame as is"] += 1
        return st
    # blur the ignore zones out, unless one overlaps a kept bird
    for _, a, b, c2, d in ignore:
        for _, ka, kb, kc, kd in keep:
            iw, ih = min(c2, kc) - max(a, ka), min(d, kd) - max(b, kb)
            if iw > 0 and ih > 0 and iw * ih >= 0.15 * (kc - ka) * (kd - kb):
                st["train frame left out (ignore zone on a kept bird)"] += 1
                return st
    img = cv2.imread(str(img_src))
    Hh, Ww = img.shape[:2]
    for _, a, b, c2, d in ignore:
        mx, my = 0.1 * (c2 - a), 0.1 * (d - b)
        x0, y0, x1, y1 = int(max(a - mx, 0)), int(max(b - my, 0)), int(min(c2 + mx, Ww)), int(min(d + my, Hh))
        if x1 - x0 > 2 and y1 - y0 > 2:
            img[y0:y1, x0:x1] = cv2.GaussianBlur(img[y0:y1, x0:x1], (0, 0), sigmaX=max(x1 - x0, y1 - y0) / 3)
    cv2.imwrite(str(img_dst), img, [cv2.IMWRITE_JPEG_QUALITY, 92])
    lab_dst.write_text(rows(keep) if keep else "")
    st["train frame with a blurred zone"] += 1
    return st


if __name__ == "__main__":
    dst.mkdir(parents=True, exist_ok=True)
    (dst / "classes.json").write_text((src / "classes.json").read_text())
    if (src / "split.json").exists():
        (dst / "split.json").write_text((src / "split.json").read_text())
    (dst / "data.yaml").write_text((src / "data.yaml").read_text().replace(str(src.resolve()), str(dst.resolve())))
    for split in splits:
        (dst / "images" / split).mkdir(parents=True, exist_ok=True)
        (dst / "labels" / split).mkdir(parents=True, exist_ok=True)
        jobs = [(split, p.stem) for p in sorted((src / "images" / split).glob("*.jpg"))]
        total = Counter()
        with Pool(procs) as pool:
            for st in pool.imap_unordered(frame, jobs, chunksize=64):
                total.update(st)
        print(f"== {split}: {len(jobs)} frames ==")
        for k in sorted(total):
            print(f"   {total[k]:7d}  {k}")
