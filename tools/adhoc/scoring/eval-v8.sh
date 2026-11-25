#!/bin/bash
export PATH=$HOME/.local/bin:$PATH
cd ~/birdai
L=data/logs/v8eval.log; echo "v8eval start $(date +%H:%M:%S)" > $L
rm -rf models_v8; mkdir -p models_v8/student
ln -sfn ../../models/student_v8a_960/960 models_v8/student/960
ln -sfn ../../models/student_v8a_640/640 models_v8/student/640
ln -sfn ../models/pretrained models_v8/pretrained
uv run --group train python tools/evaluate.py --dataset data/dataset_v8 --candidates two_stage student:640 student:960 \
  --models-dir models_v8 --board-ms two_stage=169.8,960=1108.5,640=506.6 --promote > data/logs/eval-v8.log 2>&1
echo "eval exit $? $(date +%H:%M:%S)" >> $L
ls -la models_v8 models_v8/student >> $L 2>&1
echo "v8eval done $(date +%H:%M:%S)" >> $L
