"""Train the nano student detector on the dataset from build_dataset.py and export it to ONNX.

    python tools/train_student.py --data data/dataset/data.yaml --imgsz 640 416 \
        [--epochs 60] [--base yolo26n.pt] --out models/student

Runs on the GPU machine under `uv run --group train`. For each size S it writes
<out>/<S>/feeder.onnx and <out>/<S>/feeder.json (the card the detector reads) as soon as that size is
done; a size that fails is reported and the next one still runs (exit code 1 at the end).
Training stops early and picks `best.pt` on the `val` split; the `test` split (the demo footage) is
only scored once, on the finished checkpoint. If yolo26 will not train, use --base yolo11n.pt;
the export then bakes the NMS in.
"""

import argparse
import json
import shutil
import sys
import traceback
from collections.abc import Callable, Sequence
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


def check_output_shape(shape: Sequence) -> None:
    """Accepts `[1, N, 6]` where the batch or N may be symbolic (a string or None) in the ONNX file."""
    symbolic = lambda d: d is None or isinstance(d, str)  # noqa: E731
    if len(shape) != 3 or not (shape[0] == 1 or symbolic(shape[0])) or shape[2] != 6:
        raise ValueError(f"exported model output has shape {list(shape)}, expected [1, N, 6]")


def resolve_best(trainer) -> Path:
    best = Path(trainer.best)
    if not best.is_file():
        raise RuntimeError(f"training finished but the best weights {best} do not exist (run directory {trainer.save_dir})")
    return best


def resolve_exported(returned, best: Path) -> Path:
    """The exported ONNX file: the path `export` returned, else `best.onnx` beside `best.pt`."""
    path = Path(str(returned))
    if path.suffix == ".onnx" and path.is_file():
        return path
    beside = best.with_suffix(".onnx")
    if beside.is_file():
        return beside
    raise RuntimeError(f"export returned {returned!r}, which is not an existing .onnx file, and {beside} does not exist")


def format_metrics(imgsz: int, split: str, map50: float, map5095: float, note: str) -> str:
    return f"imgsz {imgsz}: {split} mAP50 {map50:.3f} / mAP50-95 {map5095:.3f} ({note})"


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
    """Video stems of the test frames (`<stem>_<milliseconds>.jpg`): footage the training never saw."""
    return sorted({p.stem.rsplit("_", 1)[0] for p in (dataset / "images" / "test").glob("*.jpg")})


def build_card(base: str, imgsz: int, classes: list[str], train_boxes: dict[str, int],
               held_out: list[str], val_fraction: float, trained_at: str) -> dict:
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
        "val_footage": f"last {round(val_fraction * 100, 6):g}% of each training video",
        "metrics": None,
    }


def train_one(data: Path, base: str, imgsz: int, epochs: int, out: Path) -> None:
    from ultralytics import YOLO

    dataset = data.parent
    classes = json.loads((dataset / "classes.json").read_text())
    val_fraction = json.loads((dataset / "split.json").read_text())["val_fraction"]
    runs = str((out / "runs").resolve())  # every ultralytics output goes under here

    model = YOLO(base)
    model.train(data=str(data), imgsz=imgsz, epochs=epochs, batch=32, patience=15, cache=False,
                project=runs, name=str(imgsz), exist_ok=True)
    best = resolve_best(model.trainer)

    model = YOLO(str(best))
    for split, note in (("val", "used to pick the checkpoint"), ("test", "held-out footage")):
        metrics = model.val(data=str(data), imgsz=imgsz, split=split, plots=False, verbose=False,
                            project=runs, name=f"{imgsz}_{split}", exist_ok=True)
        print(format_metrics(imgsz, split, metrics.box.map50, metrics.box.map, note), flush=True)

    exported = resolve_exported(model.export(**export_args(base, imgsz)), best)
    check_exported_model(exported)
    target = out / str(imgsz)
    target.mkdir(parents=True, exist_ok=True)
    shutil.copyfile(exported, target / "feeder.onnx")
    card = build_card(base, imgsz, classes, count_train_boxes(dataset, classes), held_out_footage(dataset),
                      val_fraction, datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ"))
    (target / "feeder.json").write_text(json.dumps(card, indent=2) + "\n")
    print(f"wrote {target / 'feeder.onnx'} and {target / 'feeder.json'}", flush=True)


def run_sizes(sizes: Sequence[int], train: Callable[[int], None]) -> list[int]:
    """Runs `train(size)` for every size; a size that raises is reported and returned, the rest still run."""
    failed = []
    for imgsz in sizes:
        try:
            train(imgsz)
        except Exception:
            print(f"error: image size {imgsz} failed:", file=sys.stderr)
            traceback.print_exc()
            failed.append(imgsz)
    return failed


def main(argv: list[str] | None = None) -> None:
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--data", type=Path, required=True)
    ap.add_argument("--imgsz", type=int, nargs="+", required=True)
    ap.add_argument("--epochs", type=int, default=60)
    ap.add_argument("--base", default="yolo26n.pt")
    ap.add_argument("--out", type=Path, required=True)
    args = ap.parse_args(argv)

    for needed in ("classes.json", "split.json"):
        if not (args.data.parent / needed).is_file():
            print(f"error: no {needed} next to {args.data}; build the dataset with tools/build_dataset.py",
                  file=sys.stderr)
            raise SystemExit(2)
    failed = run_sizes(args.imgsz, lambda imgsz: train_one(args.data, args.base, imgsz, args.epochs, args.out))
    if failed:
        print(f"error: failed image sizes: {', '.join(map(str, failed))}", file=sys.stderr)
        raise SystemExit(1)


if __name__ == "__main__":
    main()
