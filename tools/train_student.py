"""Train the nano student detector on the dataset from build_dataset.py and export it to ONNX.

    python tools/train_student.py --data data/dataset/data.yaml --imgsz 640 416 \
        [--epochs 60] [--base yolo26n.pt] --out models/student

Runs on the GPU machine under `uv run --group train`. For each size S it writes
<out>/<S>/feeder.onnx and <out>/<S>/feeder.json (the card the detector reads).
If yolo26 will not train, use --base yolo11n.pt; the export then bakes the NMS in.
"""

import argparse
import json
import shutil
import sys
from datetime import datetime, timezone
from pathlib import Path

COUNT_THRESHOLD = 0.60


def export_args(base: str, imgsz: int) -> dict:
    """ONNX export arguments giving `[1, N, 6]` rows of x1, y1, x2, y2, score, class_index.

    YOLO26 has an end-to-end head that already does this; YOLO11 needs the NMS exported with it.
    """
    args = dict(format="onnx", imgsz=imgsz)
    if Path(base).stem.startswith("yolo26"):
        return {**args, "nms": False, "simplify": True}
    return {**args, "nms": True, "conf": 0.05, "simplify": True}


def check_output_shape(shape) -> None:
    if len(shape) != 3 or shape[0] != 1 or not isinstance(shape[1], int) or shape[2] != 6:
        raise ValueError(f"exported model output has shape {list(shape)}, expected [1, N, 6]")


def check_exported_model(model: Path) -> None:
    import onnxruntime as ort

    session = ort.InferenceSession(str(model), providers=["CPUExecutionProvider"])
    check_output_shape(session.get_outputs()[0].shape)


def count_train_boxes(dataset: Path, classes: list[str]) -> dict[str, int]:
    counts = {key: 0 for key in classes}
    for label_file in sorted((dataset / "labels" / "train").glob("*.txt")):
        for line in label_file.read_text().splitlines():
            if line.strip():
                counts[classes[int(line.split()[0])]] += 1
    return counts


def held_out_footage(dataset: Path) -> list[str]:
    """Video stems of the validation frames (`<stem>_<milliseconds>.jpg`)."""
    return sorted({p.stem.rsplit("_", 1)[0] for p in (dataset / "images" / "val").glob("*.jpg")})


def build_card(base: str, imgsz: int, classes: list[str], train_boxes: dict[str, int],
               held_out: list[str], trained_at: str) -> dict:
    return {
        "name": f"Feeder student {imgsz}",
        "kind": "student",
        "base": Path(base).stem,
        "imgsz": imgsz,
        "classes": classes,
        "count_threshold": COUNT_THRESHOLD,
        "trained_at": trained_at,
        "train_boxes": train_boxes,
        "held_out_footage": held_out,
        "metrics": None,
    }


def train_one(data: Path, base: str, imgsz: int, epochs: int, out: Path) -> None:
    from ultralytics import YOLO

    dataset = data.parent
    classes = json.loads((dataset / "classes.json").read_text())
    runs = out / "runs"
    YOLO(base).train(data=str(data), imgsz=imgsz, epochs=epochs, batch=32, patience=15, cache=True,
                     project=str(runs.resolve()), name=str(imgsz), exist_ok=True)
    best = runs / str(imgsz) / "weights" / "best.pt"
    model = YOLO(str(best))
    metrics = model.val(data=str(data), imgsz=imgsz, verbose=False)
    print(f"imgsz {imgsz}: validation mAP50 {metrics.box.map50:.3f}, mAP50-95 {metrics.box.map:.3f}", flush=True)

    exported = Path(model.export(**export_args(base, imgsz)))
    check_exported_model(exported)
    target = out / str(imgsz)
    target.mkdir(parents=True, exist_ok=True)
    shutil.copyfile(exported, target / "feeder.onnx")
    card = build_card(base, imgsz, classes, count_train_boxes(dataset, classes), held_out_footage(dataset),
                      datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ"))
    (target / "feeder.json").write_text(json.dumps(card, indent=2) + "\n")
    print(f"wrote {target / 'feeder.onnx'} and {target / 'feeder.json'}", flush=True)


def main(argv: list[str] | None = None) -> None:
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--data", type=Path, required=True)
    ap.add_argument("--imgsz", type=int, nargs="+", required=True)
    ap.add_argument("--epochs", type=int, default=60)
    ap.add_argument("--base", default="yolo26n.pt")
    ap.add_argument("--out", type=Path, required=True)
    args = ap.parse_args(argv)

    if not (args.data.parent / "classes.json").is_file():
        print(f"error: no classes.json next to {args.data}; build the dataset with tools/build_dataset.py",
              file=sys.stderr)
        raise SystemExit(2)
    for imgsz in args.imgsz:
        train_one(args.data, args.base, imgsz, args.epochs, args.out)


if __name__ == "__main__":
    main()
