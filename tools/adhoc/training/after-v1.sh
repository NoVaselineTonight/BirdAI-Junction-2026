#!/usr/bin/env bash
# When the v1 960 model has been exported: stop the v1 640 run (same labels, not worth the GPU) and measure v1 960.
export PATH=$HOME/.local/bin:$PATH
cd ~/birdai || exit 1
L=data/logs/after-v1.log
echo "waiting $(date +%H:%M:%S)" > $L
until [ -f models/student_v1/960/feeder.json ]; do sleep 10; done
sleep 5
pkill -f "out models/student_v1"
echo "v1 640 stopped $(date +%H:%M:%S)" >> $L
mkdir -p models_v1
ln -sfn ../models/student_v1 models_v1/student
ln -sfn ../models/pretrained models_v1/pretrained
uv run --group train python tools/evaluate.py --dataset data/dataset_v1 --candidates student:960 --models-dir models_v1 >> $L 2>&1
echo "eval exit $? $(date +%H:%M:%S)" >> $L
