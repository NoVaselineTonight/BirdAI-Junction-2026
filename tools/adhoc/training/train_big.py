"""Ad-hoc: one plain training run of a student of another size on the checked labels (model size test).

    python data/train_big.py --model yolo26s.pt --imgsz 640 --epochs 16 --batch 64 --name s640 --device 0
"""
import argparse
from pathlib import Path
from ultralytics import YOLO

ap = argparse.ArgumentParser()
ap.add_argument("--model", required=True); ap.add_argument("--imgsz", type=int, default=640)
ap.add_argument("--epochs", type=int, default=16); ap.add_argument("--batch", type=int, default=64)
ap.add_argument("--workers", type=int, default=16); ap.add_argument("--name", required=True)
ap.add_argument("--device", default="0")
a = ap.parse_args()
out = (Path("data/sweep") / a.name).resolve(); out.mkdir(parents=True, exist_ok=True)
dev = [int(d) for d in a.device.split(",")] if "," in a.device else int(a.device)
YOLO(a.model).train(data="data/dataset_v8/data.yaml", imgsz=a.imgsz, epochs=a.epochs, batch=a.batch, workers=a.workers,
                    cache=False, patience=100, val=False, plots=False, save=True, save_period=1, device=dev,
                    project=str(out), name="t", exist_ok=True)
(out / "done").write_text("done")
