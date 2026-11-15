#!/usr/bin/env bash
# Worker: when its own labels are embedded and the big teacher's weights have arrived, let the big teacher
# propose missed birds on its training frames, then embed the proposals.  Usage: bash data/propose-run.sh auto3 big3
export PATH=$HOME/.local/bin:$PATH
cd ~/birdai || exit 1
L=data/logs/propose.log
echo "propose waiting $(date +%H:%M:%S)" > $L
until grep -q "embed exit" data/logs/worker7.log 2>/dev/null && [ -f data/big.pt ]; do sleep 10; done
echo "propose start $(date +%H:%M:%S)" >> $L
uv run --group train python data/big_propose.py data/big.pt data/labels/$1.jsonl data/frames data/labels/$2.jsonl > data/logs/propose-$2.log 2>&1
echo "propose exit $? $(date +%H:%M:%S)" >> $L
uv run --group train python data/embed.py data/labels/$2.jsonl data/frames > data/logs/embed-$2.log 2>&1
echo "propose-embed exit $? $(date +%H:%M:%S)" >> $L
