#!/usr/bin/env bash
# Measures the quick first model on the held-out day as soon as its training ends.
export PATH=$HOME/.local/bin:$PATH
cd ~/birdai || exit 1
until grep -q "quick exit" data/logs/v1.log 2>/dev/null; do sleep 5; done
L=data/logs/eval-quick.log
echo "eval start $(date +%H:%M:%S)" > $L
grep "quick exit" data/logs/v1.log >> $L
mkdir -p models_quick
ln -sfn ../models/student_quick models_quick/student
ln -sfn ../models/pretrained models_quick/pretrained
ls -la models/student_quick models/student_quick/640 >> $L 2>&1
uv run --group train python tools/evaluate.py --dataset data/dataset_v1 --candidates two_stage student:640 \
  --models-dir models_quick --promote >> $L 2>&1
echo "eval exit $? $(date +%H:%M:%S)" >> $L
