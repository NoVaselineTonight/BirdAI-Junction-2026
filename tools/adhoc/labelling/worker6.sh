#!/usr/bin/env bash
# On scan4: when the videos have arrived from scan3, mine frames, label with the teachers, embed.
export PATH=$HOME/.local/bin:$PATH
cd ~/birdai || exit 1
L=data/logs/worker6.log
echo "worker6 waiting $(date +%H:%M:%S)" > $L
until [ -f data/videos/READY ]; do sleep 15; done
ls -la data/videos/train >> $L
rm -rf data/frames data/labels/auto4*
uv run --group train python -c "import torch; print('cuda', torch.cuda.is_available())" >> $L 2>&1
uv run --group train python tools/mine_frames.py --videos data/videos --out data/frames --workers 10 > data/logs/mine.log 2>&1
echo "mine exit $? $(date +%H:%M:%S)" >> $L
uv run --group train python tools/autolabel.py --frames data/frames --out data/labels/auto4.jsonl > data/logs/label4.log 2>&1
echo "label exit $? $(date +%H:%M:%S)" >> $L
uv run --group train python data/embed.py data/labels/auto4.jsonl data/frames > data/logs/embed4.log 2>&1
echo "embed exit $? $(date +%H:%M:%S)" >> $L
