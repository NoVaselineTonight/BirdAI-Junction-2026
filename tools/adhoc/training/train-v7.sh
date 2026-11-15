#!/usr/bin/env bash
# main: small re-training of the 44-day 960 px student (from its own weights, dataset_v5 as it is), then score it.
export PATH=$HOME/.local/bin:$PATH
cd ~/birdai || exit 1
E=${1:-2}
L=data/logs/v7train.log
echo "v7 start $(date +%H:%M:%S) epochs $E" > $L
PYTHONPATH=.:tools uv run --group train python data/train_student_nocache.py --data data/dataset_v5/data.yaml --imgsz 960 --epochs $E \
  --base keep_from_fast/models/student_v5_960/runs/960/weights/best.pt --out models/student_v7_960 > data/logs/train-v7-960.log 2>&1
echo "960 exit $? $(date +%H:%M:%S)" >> $L
PYTHONPATH=. .venv/bin/python data/rescore.py data/dataset_v5 models/student_v7_960/960 v7-960 2>&1 | grep -v "Warning\|warn\|INFO" >> $L
echo "v7 done $(date +%H:%M:%S)" >> $L
