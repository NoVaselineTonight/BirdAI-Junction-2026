import argparse
from pathlib import Path
from ultralytics import YOLO
ap = argparse.ArgumentParser()
for a, d in (("--model", None), ("--data", None), ("--name", None), ("--device", "0")):
    ap.add_argument(a, default=d)
ap.add_argument("--imgsz", type=int); ap.add_argument("--epochs", type=int); ap.add_argument("--batch", type=int)
ap.add_argument("--workers", type=int, default=20); ap.add_argument("--seed", type=int, default=0)
a = ap.parse_args()
out = (Path("data/v9runs") / a.name).resolve(); out.mkdir(parents=True, exist_ok=True)
YOLO(a.model).train(data=a.data, imgsz=a.imgsz, epochs=a.epochs, batch=a.batch, workers=a.workers, cache=False, patience=100, seed=a.seed,
                    val=False, plots=False, save=True, device=[int(d) for d in a.device.split(",")], project=str(out), name="t", exist_ok=True)
(out / "done").write_text("done")
