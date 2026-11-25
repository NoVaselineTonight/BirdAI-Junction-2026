#!/usr/bin/env bash
# Final round, stage B (main machine): degraded copies, squirrel composites, dataset, training at 960 and 640, measurement.
# Usage: bash data/run-v3-b.sh <epochs>
export PATH=$HOME/.local/bin:$PATH
cd ~/birdai || exit 1
E=${1:-20}
L=data/logs/v3b.log
echo "v3b start $(date +%H:%M:%S) epochs $E" > $L
uv run --group train python data/degrade.py v3 4 >> $L 2>&1 || { echo "degrade failed" >> $L; exit 1; }
uv run --group train python data/squirrel_paste.py v3 1500 >> $L 2>&1 || { echo "paste failed" >> $L; exit 1; }
cat data/labels/v3.jsonl data/labels/lowq_v3.jsonl data/labels/squirrel_raw.jsonl data/labels/squirrel_synth.jsonl > data/labels/v3f.jsonl
rm -rf data/dataset_v3
uv run --group train python tools/build_dataset.py --labels data/labels/v3f.jsonl --corrections data/review/corrections_v3.csv \
  --frames data/frames --out data/dataset_v3 >> $L 2>&1
echo "dataset exit $? $(date +%H:%M:%S)" >> $L
grep -q "dataset exit 0" $L || exit 1
( uv run --group train python tools/train_student.py --data data/dataset_v3/data.yaml --imgsz 960 --epochs $E \
    --out models/student_v3_960 > data/logs/train-v3-960.log 2>&1; echo "960 exit $? $(date +%H:%M:%S)" >> $L ) &
( uv run --group train python tools/train_student.py --data data/dataset_v3/data.yaml --imgsz 640 --epochs $E \
    --out models/student_v3_640 > data/logs/train-v3-640.log 2>&1; echo "640 exit $? $(date +%H:%M:%S)" >> $L ) &
wait
mkdir -p models_v3/student
ln -sfn ../../models/student_v3_960/960 models_v3/student/960
ln -sfn ../../models/student_v3_640/640 models_v3/student/640
ln -sfn ../models/pretrained models_v3/pretrained
uv run --group train python tools/evaluate.py --dataset data/dataset_v3 --candidates two_stage student:960 student:640 \
  --models-dir models_v3 > data/logs/eval-v3.log 2>&1
echo "eval exit $? $(date +%H:%M:%S)" >> $L
