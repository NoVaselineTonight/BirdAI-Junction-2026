#!/usr/bin/env bash
# Version 2a: cleaned labels (relabel3 already run as tag v2) + squirrel frames; train 960 and 640 side by side.
export PATH=$HOME/.local/bin:$PATH
cd ~/birdai || exit 1
L=data/logs/v2a.log
echo "v2a start $(date +%H:%M:%S)" > $L
uv run --group train python data/squirrel_paste.py v2 1200 >> $L 2>&1 || { echo "paste failed" >> $L; exit 1; }
cat data/labels/v2.jsonl data/labels/squirrel_raw.jsonl data/labels/squirrel_synth.jsonl > data/labels/v2a.jsonl
rm -rf data/dataset_v2a
uv run --group train python tools/build_dataset.py --labels data/labels/v2a.jsonl --corrections data/review/corrections_v2.csv \
  --frames data/frames --out data/dataset_v2a >> $L 2>&1
echo "dataset exit $? $(date +%H:%M:%S)" >> $L
grep -q "dataset exit 0" $L || exit 1
( uv run --group train python tools/train_student.py --data data/dataset_v2a/data.yaml --imgsz 960 --epochs 60 \
    --out models/student_v2a_960 > data/logs/train-v2a-960.log 2>&1; echo "960 exit $? $(date +%H:%M:%S)" >> $L ) &
( uv run --group train python tools/train_student.py --data data/dataset_v2a/data.yaml --imgsz 640 --epochs 60 \
    --out models/student_v2a_640 > data/logs/train-v2a-640.log 2>&1; echo "640 exit $? $(date +%H:%M:%S)" >> $L ) &
wait
mkdir -p models_v2a/student
ln -sfn ../../models/student_v2a_960/960 models_v2a/student/960
ln -sfn ../../models/student_v2a_640/640 models_v2a/student/640
ln -sfn ../models/pretrained models_v2a/pretrained
uv run --group train python tools/evaluate.py --dataset data/dataset_v2a --candidates two_stage student:960 student:640 \
  --models-dir models_v2a > data/logs/eval-v2a.log 2>&1
echo "eval exit $? $(date +%H:%M:%S)" >> $L
