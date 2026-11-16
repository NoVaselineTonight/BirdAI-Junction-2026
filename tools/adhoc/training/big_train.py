"""Ad-hoc: train a large detector on this camera (the in-domain teacher). It only ever sees the training split."""
from ultralytics import YOLO

model = YOLO("yolo26m.pt")
model.train(data="data/dataset_v2a/data.yaml", imgsz=1280, epochs=12, batch=24, device=0, workers=12, close_mosaic=2,
            patience=100, project="/root/birdai/runs_big", name="t1", exist_ok=True, amp=True, plots=False, val=True)
print("DONE")
