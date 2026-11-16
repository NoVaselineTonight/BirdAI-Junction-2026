#!/usr/bin/env bash
# After mining on the worker: label its frames with the teachers and compute embeddings, on its own GPU.
export PATH=$HOME/.local/bin:$PATH
cd ~/birdai || exit 1
L=data/logs/worker3.log
echo "worker3 waiting $(date +%H:%M:%S)" > $L
until grep -q "mine exit" data/logs/worker.log 2>/dev/null; do sleep 20; done
grep "mine exit" data/logs/worker.log >> $L
mkdir -p data/labels data/check
uv run --group train python tools/autolabel.py --frames data/frames --out data/labels/auto3.jsonl > data/logs/label3.log 2>&1
echo "label exit $? $(date +%H:%M:%S)" >> $L
uv run --group train python data/embed.py data/labels/auto3.jsonl data/frames > data/logs/embed3.log 2>&1
echo "embed exit $? $(date +%H:%M:%S)" >> $L
