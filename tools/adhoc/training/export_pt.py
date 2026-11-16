"""Ad-hoc: export a trained .pt to the project's student layout (<out>/<name>/feeder.onnx + feeder.json).

    python data/export_pt.py WEIGHTS.pt BASE_NAME IMGSZ OUT_DIR NAME [DATASET]
"""
import json, shutil, sys
from datetime import datetime, timezone
from pathlib import Path
sys.path.insert(0, "data"); sys.path.insert(0, "tools"); sys.path.insert(0, ".")
import train_v8 as ts
from ultralytics import YOLO

weights, base, imgsz, out, name = Path(sys.argv[1]), sys.argv[2], int(sys.argv[3]), Path(sys.argv[4]), sys.argv[5]
dataset = Path(sys.argv[6]) if len(sys.argv) > 6 else Path("data/dataset_v8")
work = out / "export" / name; work.mkdir(parents=True, exist_ok=True)
pt = work / "best.pt"; shutil.copyfile(weights, pt)
model = YOLO(str(pt))
exported = ts.resolve_exported(model.export(**ts.export_args(base, imgsz)), pt)
ts.check_exported_model(exported)
target = out / name; target.mkdir(parents=True, exist_ok=True)
shutil.copyfile(exported, target / "feeder.onnx")
classes = json.loads((dataset / "classes.json").read_text())
vf = json.loads((dataset / "split.json").read_text())["val_fraction"]
card = ts.build_card(base, imgsz, classes, ts.count_train_boxes(dataset, classes), ts.held_out_footage(dataset), vf,
                     datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ"))
(target / "feeder.json").write_text(json.dumps(card, indent=2) + "\n")
print("wrote", target / "feeder.onnx", (target / "feeder.onnx").stat().st_size, "bytes")
