#!/usr/bin/env bash
# Version 1 of the student: relabel, build the dataset, then train a quick model and the full models.
export PATH=$HOME/.local/bin:$PATH
cd ~/birdai || exit 1
L=data/logs/v1.log
echo "v1 start $(date +%H:%M:%S)" > $L
uv run --group train python data/relabel.py auto.jsonl v1 >> $L 2>&1 || { echo "relabel failed" >> $L; exit 1; }
rm -rf data/dataset_v1
uv run --group train python tools/build_dataset.py --labels data/labels/v1.jsonl --corrections data/review/corrections_v1.csv \
  --frames data/frames --out data/dataset_v1 >> $L 2>&1
echo "dataset exit $? $(date +%H:%M:%S)" >> $L
grep -q "dataset exit 0" $L || exit 1
# fetch the base weights once so the two runs do not race on the download
uv run --group train python -c "from ultralytics import YOLO; YOLO('yolo26n.pt')" >> $L 2>&1
# quick first model and the full models side by side
( uv run --group train python tools/train_student.py --data data/dataset_v1/data.yaml --imgsz 640 --epochs 20 \
    --out models/student_quick > data/logs/train-quick.log 2>&1; echo "quick exit $? $(date +%H:%M:%S)" >> $L ) &
( uv run --group train python tools/train_student.py --data data/dataset_v1/data.yaml --imgsz 960 640 --epochs 60 \
    --out models/student_v1 > data/logs/train-v1.log 2>&1; echo "full exit $? $(date +%H:%M:%S)" >> $L ) &
wait
echo "v1 done $(date +%H:%M:%S)" >> $L
