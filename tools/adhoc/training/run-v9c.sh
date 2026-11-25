#!/bin/bash
# 8-GPU machine: machine-check the training frames of 13 more days of our camera, build a 38-day training set (v9),
# fine-tune on it, and score on the 5 exam days (never trained, never used to choose) and the 12 Nov test day.
export PATH=$HOME/vlm/bin:$HOME/.local/bin:$PATH
cd ~/birdai
L=data/logs/v9.log; V=data/dataset_v9; echo "restart from training $(date +%H:%M:%S)" >> $L
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
