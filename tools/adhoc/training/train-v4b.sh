#!/usr/bin/env bash
# birdai-fast: when dataset_v4 has arrived, train the final student at 960 (GPU 0) and 640 (GPU 1) side by side,
# each starting from the 16-day model's weights (which never saw the held-out day).
# Usage: bash data/train-v4.sh <epochs>
export PATH=$HOME/.local/bin:$PATH
cd ~/birdai || exit 1
E=${1:-20}
L=data/logs/v4train.log
echo "v4train waiting $(date +%H:%M:%S) epochs $E" > $L
until [ -f data/dataset_v4.READY ]; do sleep 5; done
echo "dataset here $(date +%H:%M:%S)" >> $L
uv run --group train python -c "from ultralytics import YOLO; YOLO('yolo26n.pt')" >> $L 2>&1
( CUDA_VISIBLE_DEVICES=0 uv run --group train python tools/train_student.py --data data/dataset_v4/data.yaml --imgsz 960 --epochs $E \
    --base models/student_v3_960/runs/960/weights/best.pt --out models/student_v4_960 > data/logs/train-v4-960.log 2>&1; echo "960 exit $? $(date +%H:%M:%S)" >> $L ) &
( CUDA_VISIBLE_DEVICES=1 uv run --group train python tools/train_student.py --data data/dataset_v4/data.yaml --imgsz 640 --epochs $E \
    --base models/student_v3_640/runs/640/weights/best.pt --out models/student_v4_640 > data/logs/train-v4-640.log 2>&1; echo "640 exit $? $(date +%H:%M:%S)" >> $L ) &
wait
echo "v4train done $(date +%H:%M:%S)" >> $L
