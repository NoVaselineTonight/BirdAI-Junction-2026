#!/bin/bash
# 8-GPU machine: machine-check the training frames of 13 more days of our camera, build a 38-day training set (v9),
# fine-tune on it, and score on the 5 exam days (never trained, never used to choose) and the 12 Nov test day.
export PATH=$HOME/vlm/bin:$HOME/.local/bin:$PATH
cd ~/birdai
L=data/logs/v9.log; echo "v9 start $(date +%H:%M:%S)" > $L
pkill -f "data/run-job.s[h]"; pkill -f "data/evolve.p[y]"; pkill -f "data/evo_one.p[y]"
command -v ninja >/dev/null || { DEBIAN_FRONTEND=noninteractive apt-get update > data/logs/apt.log 2>&1; DEBIAN_FRONTEND=noninteractive apt-get install -y python3.12-dev ninja-build build-essential >> data/logs/apt.log 2>&1; }
until [ -f ~/x2-frames-done ] && [ -f ~/proc-assets-done ] && [ -d data/dataset_v8/images/train ] && [ -f data/dataset_exam/classes.json ]; do sleep 5; done
D=data/dataset_x2; C=data/check_x2
sed "s#/root/birdai/data/dataset_v8#/root/birdai/data/dataset_x2#" data/dataset_v8/data.yaml > $D/data.yaml
echo "inputs here: $(ls $D/images/train | wc -l) frames $(date +%H:%M:%S)" >> $L
for i in 0 1 2 3 4 5 6 7; do CUDA_VISIBLE_DEVICES=$i .venv/bin/python data/cand.py $D train $C --shard $i/8 > data/logs/cand-x2-$i.log 2>&1 & done; wait
echo "cand done $(cat $C/cands-*.jsonl | wc -l) candidates $(date +%H:%M:%S)" >> $L
for i in 0 1 2 3 4 5 6 7; do
  CUDA_VISIBLE_DEVICES=$i OMP_NUM_THREADS=1 setsid -f $HOME/vlm/bin/vllm serve Qwen/Qwen3-VL-8B-Instruct --port $((8000+i)) --max-model-len 4096 --gpu-memory-utilization 0.5 --limit-mm-per-prompt.video 0 --mm-processor-cache-gb 0 --max-num-seqs 128 > ~/vlm-server-$i.log 2>&1
done
for i in $(seq 1 240); do n=0; for p in 0 1 2 3 4 5 6 7; do curl -s -m 3 http://127.0.0.1:$((8000+p))/v1/models | grep -q Qwen && n=$((n+1)); done; [ $n = 8 ] && break; sleep 5; done
echo "judge servers up: $n of 8 $(date +%H:%M:%S)" >> $L
PORTS=$(for p in 0 1 2 3 4 5 6 7; do curl -s -m 3 http://127.0.0.1:$((8000+p))/v1/models | grep -q Qwen && printf "%s," $((8000+p)); done | sed 's/,$//')
~/vlm/bin/python data/judge.py $C --ports $PORTS --workers 640 > data/logs/judge-x2.log 2>&1
~/vlm/bin/python data/judge.py $C --ports $PORTS --workers 128 >> data/logs/judge-x2.log 2>&1
echo "judged $(wc -l < $C/verdicts.jsonl) $(date +%H:%M:%S)" >> $L
pkill -f "vllm[ ]serve"; sleep 8
OMP_NUM_THREADS=1 .venv/bin/python data/truth.py $D $C ${D}k train --procs 96 > data/logs/truth-x2.log 2>&1
echo "truth exit $? kept frames $(ls ${D}k/images/train | wc -l) $(date +%H:%M:%S)" >> $L
tail -25 data/logs/truth-x2.log >> $L
# v9 = the 25 checked days + the 13 newly checked days
V=data/dataset_v9; rm -rf $V; mkdir -p $V/images $V/labels
cp -al data/dataset_v8/images/train $V/images/train; cp -a data/dataset_v8/labels/train $V/labels/train
cp -al ${D}k/images/train/. $V/images/train/; cp -a ${D}k/labels/train/. $V/labels/train/
cp -al data/dataset_v8/images/val $V/images/val; cp -a data/dataset_v8/labels/val $V/labels/val
cp data/dataset_v8/classes.json $V/; cp data/dataset_v8/split.json $V/ 2>/dev/null
sed "s#/root/birdai/data/dataset_v8#/root/birdai/data/dataset_v9#" data/dataset_v8/data.yaml > $V/data.yaml
echo "v9 built: $(ls $V/images/train | wc -l) train frames $(date +%H:%M:%S)" >> $L
cat > data/train_v9.py <<'PY'
import argparse
from pathlib import Path
from ultralytics import YOLO
ap = argparse.ArgumentParser()
for a, d in (("--model", None), ("--data", None), ("--name", None), ("--device", "0")):
    ap.add_argument(a, default=d)
ap.add_argument("--imgsz", type=int); ap.add_argument("--epochs", type=int); ap.add_argument("--batch", type=int); ap.add_argument("--workers", type=int, default=20)
a = ap.parse_args()
out = (Path("data/v9runs") / a.name).resolve(); out.mkdir(parents=True, exist_ok=True)
YOLO(a.model).train(data=a.data, imgsz=a.imgsz, epochs=a.epochs, batch=a.batch, workers=a.workers, cache=False, patience=100,
                    val=False, plots=False, save=True, device=[int(d) for d in a.device.split(",")], project=str(out), name="t", exist_ok=True)
(out / "done").write_text("done")
PY
W960=models/student_v8a_960/runs/960/weights/best.pt; W640=models/student_v8a_640/runs/640/weights/best.pt
.venv/bin/python data/train_v9.py --model $W960 --data $V/data.yaml --imgsz 960 --epochs 8  --batch 64  --name v9_960_e8  --device 0,1 > data/logs/v9_960_e8.log 2>&1 &
.venv/bin/python data/train_v9.py --model $W960 --data $V/data.yaml --imgsz 960 --epochs 14 --batch 64  --name v9_960_e14 --device 2,3 > data/logs/v9_960_e14.log 2>&1 &
.venv/bin/python data/train_v9.py --model $W640 --data $V/data.yaml --imgsz 640 --epochs 8  --batch 128 --name v9_640_e8  --device 4,5 > data/logs/v9_640_e8.log 2>&1 &
.venv/bin/python data/train_v9.py --model $W960 --data data/dataset_v8/data.yaml --imgsz 960 --epochs 8 --batch 64 --name v8_960_e8_control --device 6,7 > data/logs/v8_960_control.log 2>&1 &
wait
echo "training done $(date +%H:%M:%S)" >> $L
sc() { # name weights imgsz
  for ds in exam fit; do
    PYTHONPATH=.:tools .venv/bin/python data/evo_one.py --score-only --parent $2 --out /tmp/sc-$1 --imgsz $3 --fit-dataset data/dataset_$ds --fit-split test --val-every 1 2>&1 | grep RESULT | sed "s#^#$ds $1 #" >> $L
  done
  PYTHONPATH=.:tools .venv/bin/python data/evo_one.py --score-only --parent $2 --out /tmp/sc-$1 --imgsz $3 --fit-dataset data/dataset_v8 --fit-split test --val-every 1 2>&1 | grep RESULT | sed "s#^#nov12 $1 #" >> $L
}
sc base_960 $W960 960
for n in v9_960_e8 v9_960_e14 v8_960_e8_control; do sc $n data/v9runs/$n/t/weights/last.pt 960; done
sc v9_640_e8 data/v9runs/v9_640_e8/t/weights/last.pt 640
echo "v9 done $(date +%H:%M:%S)" >> $L
