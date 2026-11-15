#!/usr/bin/env bash
# After mining on the worker: label its frames with the teachers and score bird-or-not, here on its own GPU.
export PATH=$HOME/.local/bin:$PATH
cd ~/birdai || exit 1
L=data/logs/worker2.log
echo "worker2 waiting $(date +%H:%M:%S)" > $L
until grep -q "mine exit" data/logs/worker.log 2>/dev/null; do sleep 20; done
grep "mine exit" data/logs/worker.log >> $L
mkdir -p data/labels data/check
uv run --group train python tools/autolabel.py --frames data/frames --out data/labels/auto3.jsonl > data/logs/label3.log 2>&1
echo "label exit $? $(date +%H:%M:%S)" >> $L
uv run --group train python data/birdness.py data/labels/auto3.jsonl data/frames > data/logs/birdness3.log 2>&1
echo "birdness exit $? $(date +%H:%M:%S)" >> $L
