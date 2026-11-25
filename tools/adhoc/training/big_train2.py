"""Ad-hoc: a second, larger in-domain teacher (yolo26l at 1280 on two GPUs). Training split only."""
from ultralytics import YOLO

if __name__ == "__main__":
    model = YOLO("yolo26l.pt")
    model.train(data="data/dataset_v2a/data.yaml", imgsz=1280, epochs=12, batch=48, device=[0, 1], workers=24, close_mosaic=2,
                patience=100, project="/root/birdai/runs_big", name="t2", exist_ok=True, amp=True, plots=False, val=True)
    print("DONE")
