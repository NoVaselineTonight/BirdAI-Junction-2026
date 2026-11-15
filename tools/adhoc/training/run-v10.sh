#!/bin/bash
# 8-GPU machine, second round: (A) v9 + other-feeder wave 1 at 960, (B) small 640 fine-tuned on v9, (C) v9 960 repeat with another seed
cd ~/birdai; L=data/logs/v10.log; echo "v10 start $(date +%H:%M:%S)" > $L
V=data/dataset_v10; rm -rf $V; mkdir -p $V/images $V/labels
cp -al data/dataset_v9/images/train $V/images/train; cp -a data/dataset_v9/labels/train $V/labels/train
cp -al data/dataset_xf1k/images/train/. $V/images/train/; cp -a data/dataset_xf1k/labels/train/. $V/labels/train/
cp -al data/dataset_v9/images/val $V/images/val; cp -a data/dataset_v9/labels/val $V/labels/val
cp data/dataset_v9/classes.json $V/; sed "s#dataset_v9#dataset_v10#" data/dataset_v9/data.yaml > $V/data.yaml
echo "v10 built: $(ls $V/images/train | wc -l) train frames ($(ls data/dataset_xf1k/images/train | wc -l) from other feeders) $(date +%H:%M:%S)" >> $L
cat > data/train_v10.py <<'PY'
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
PY
W960=models/student_v8a_960/runs/960/weights/best.pt
.venv/bin/python data/train_v10.py --model $W960 --data $V/data.yaml --imgsz 960 --epochs 8 --batch 64 --name v10_960_e8 --device 0,1 > data/logs/v10_960_e8.log 2>&1 &
.venv/bin/python data/train_v10.py --model data/s640_e30.pt --data data/dataset_v9/data.yaml --imgsz 640 --epochs 8 --batch 128 --name v9_s640_e8 --device 4,5 > data/logs/v9_s640_e8.log 2>&1 &
.venv/bin/python data/train_v10.py --model $W960 --data data/dataset_v9/data.yaml --imgsz 960 --epochs 8 --batch 64 --seed 1 --name v9_960_e8_seed1 --device 6,7 > data/logs/v9_960_e8_seed1.log 2>&1 &
wait
echo "training done $(date +%H:%M:%S)" >> $L
g=0
for n in v10_960_e8 v9_s640_e8 v9_960_e8_seed1; do
  sz=960; case $n in *640*) sz=640;; esac
  ( for ds in exam:data/dataset_exam nov12:data/dataset_v8; do
      CUDA_VISIBLE_DEVICES=$g PYTHONPATH=.:tools .venv/bin/python data/evo_one.py --score-only --parent data/v9runs/$n/t/weights/last.pt --out /tmp/v10-$n --imgsz $sz --fit-dataset ${ds#*:} --fit-split test --val-every 1 2>&1 | grep RESULT | sed "s#^#${ds%%:*} $n #" >> $L
    done ) &
  g=$((g+1)); [ $g = 2 ] && g=4
done; wait
echo "v10 done $(date +%H:%M:%S)" >> $L
