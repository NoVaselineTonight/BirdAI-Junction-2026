"""Ad-hoc: one individual of the evolution run: train a little from the parent's weights, then score.

    python data/evo_one.py --parent W.pt --hyp '{"lr0": ...}' --out DIR [--epochs 1] [--data data/dataset_v8/data.yaml]

Fitness mirrors the project's own selection rule, on checked validation footage (never the held-out day):
the lowest cut-off between 0.30 and 0.90 at which at least 90 % of named birds are right, and the share of frames
counted exactly right at that cut-off. Writes DIR/result.json and DIR/weights.pt.
"""
import argparse, json, shutil, sys, time
from pathlib import Path

ap = argparse.ArgumentParser()
ap.add_argument("--parent", required=True)
ap.add_argument("--hyp", default="{}")
ap.add_argument("--out", required=True)
ap.add_argument("--epochs", type=int, default=1)
ap.add_argument("--data", default="data/dataset_v8/data.yaml")
ap.add_argument("--imgsz", type=int, default=640)
ap.add_argument("--val-every", type=int, default=3, help="score on every n-th validation frame")
ap.add_argument("--workers", type=int, default=12)
ap.add_argument("--batch", type=int, default=64)
ap.add_argument("--score-only", action="store_true")
ap.add_argument("--fit-dataset", default="", help="dataset whose frames score the member (default: the training dataset)")
ap.add_argument("--fit-split", default="val")
a = ap.parse_args()

sys.path.insert(0, "tools"); sys.path.insert(0, ".")
import evaluate as ev  # noqa: E402
from feeder_census.types import Detection  # noqa: E402
from ultralytics import YOLO  # noqa: E402

out = Path(a.out); out.mkdir(parents=True, exist_ok=True)
hyp = json.loads(a.hyp)
dataset = Path(a.data).parent
classes = json.loads((dataset / "classes.json").read_text())
species = [c for c in classes if c != "unidentified"]
t0 = time.time()
weights = Path(a.parent)
if not a.score_only:
    model = YOLO(a.parent)
    model.train(data=a.data, imgsz=a.imgsz, epochs=a.epochs, batch=a.batch, workers=a.workers, cache=False,
                optimizer="AdamW", cos_lr=False, patience=100, val=False, plots=False, save=True, verbose=False,
                amp=True, close_mosaic=0, project=str((out / "runs").resolve()), name="t", exist_ok=True, **hyp)
    weights = Path(model.trainer.last)
    shutil.copyfile(weights, out / "weights.pt")
    weights = out / "weights.pt"
t1 = time.time()

model = YOLO(str(weights))
fit = Path(a.fit_dataset) if a.fit_dataset else dataset
paths = sorted((fit / "images" / a.fit_split).glob("*.jpg"))[:: a.val_every]
frames = []
for i in range(0, len(paths), 128):
    chunk = paths[i:i + 128]
    for p, r in zip(chunk, model.predict([str(c) for c in chunk], imgsz=a.imgsz, conf=0.25, verbose=False)):
        H, W = r.orig_shape
        pred = [Detection(model.names[int(c)], float(s), tuple(float(v) for v in b))
                for b, s, c in zip(r.boxes.xyxy.tolist(), r.boxes.conf.tolist(), r.boxes.cls.tolist())]
        truth = ev.read_truth(fit / "labels" / a.fit_split / f"{p.stem}.txt", (W, H), classes)
        frames.append((pred, truth))
rows = []
for k in range(13):
    thr = round(0.30 + 0.05 * k, 2)
    tall = ev._tally_frames(frames, thr, species)
    tp = sum(t.tp for t in tall.values()); fp = sum(t.fp for t in tall.values()); fn = sum(t.fn for t in tall.values())
    exact = sum(ev.frame_is_exact(p, t, thr, species) for p, t in frames) / len(frames)
    rows.append(dict(thr=thr, P=tp / max(tp + fp, 1), R=tp / max(tp + fn, 1), exact=exact))
ok = [r for r in rows if r["P"] >= 0.90]
pick = ok[0] if ok else rows[-1]
res = dict(fitness=round(pick["exact"], 5), thr=pick["thr"], P=round(pick["P"], 4), R=round(pick["R"], 4),
           exact50=round(next(r["exact"] for r in rows if r["thr"] == 0.5), 5), frames=len(frames), hyp=hyp,
           parent=a.parent, weights=str(weights), train_s=round(t1 - t0), score_s=round(time.time() - t1), curve=rows)
(out / "result.json").write_text(json.dumps(res))
print("RESULT", json.dumps({k: res[k] for k in ("fitness", "thr", "P", "R", "exact50", "train_s", "score_s")}), flush=True)
