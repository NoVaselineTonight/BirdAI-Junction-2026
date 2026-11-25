#!/usr/bin/env bash
# Worker, second attempt with the GPU ready: scan the eight days, then label and embed all its frames.
export PATH=$HOME/.local/bin:$PATH
cd ~/birdai || exit 1
L=data/logs/worker4.log
echo "worker4 start $(date +%H:%M:%S)" > $L
nvidia-smi conf-compute -srs 1 >> $L 2>&1
mkdir -p data/videos_done/train data/labels data/check
mv data/videos/train/catv-*.mp4 data/videos_done/train/ 2>/dev/null
uv run --group train python tools/mine_frames.py --videos data/videos --out data/frames_b --workers 8 > data/logs/mine_b.log 2>&1
echo "mine exit $? $(date +%H:%M:%S)" >> $L
mv data/frames_b/train/* data/frames/train/ && echo "moved" >> $L
ls data/frames/train >> $L
uv run --group train python tools/autolabel.py --frames data/frames --out data/labels/auto3.jsonl > data/logs/label3.log 2>&1
echo "label exit $? $(date +%H:%M:%S)" >> $L
uv run --group train python data/embed.py data/labels/auto3.jsonl data/frames > data/logs/embed3.log 2>&1
echo "embed exit $? $(date +%H:%M:%S)" >> $L
