#!/usr/bin/env bash
# birdai-fast: clean the 25-day labels (clean_labels.py), then fine-tune both sizes from the v4 weights.
export PATH=$HOME/.local/bin:$PATH
cd ~/birdai || exit 1
E9=${1:-3}; E6=${2:-5}
L=data/logs/v6train.log
echo "v6 start $(date +%H:%M:%S) epochs 960:$E9 640:$E6" > $L
rm -rf data/dataset_v4c
.venv/bin/python data/clean_labels.py data/dataset_v4 data/dataset_v4c >> $L 2>&1 || { echo "clean failed" >> $L; exit 1; }
echo "labels cleaned $(date +%H:%M:%S)" >> $L
( CUDA_VISIBLE_DEVICES=0 uv run --group train python tools/train_student.py --data data/dataset_v4c/data.yaml --imgsz 960 --epochs $E9 \
    --base models/student_v4_960/runs/960/weights/best.pt --out models/student_v6_960 > data/logs/train-v6-960.log 2>&1; echo "960 exit $? $(date +%H:%M:%S)" >> $L ) &
( CUDA_VISIBLE_DEVICES=1 uv run --group train python tools/train_student.py --data data/dataset_v4c/data.yaml --imgsz 640 --epochs $E6 \
    --base models/student_v4_640/runs/640/weights/best.pt --out models/student_v6_640 > data/logs/train-v6-640.log 2>&1; echo "640 exit $? $(date +%H:%M:%S)" >> $L ) &
wait
echo "v6train done $(date +%H:%M:%S)" >> $L
