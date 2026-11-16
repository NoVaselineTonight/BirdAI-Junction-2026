#!/usr/bin/env bash
# Second round of proposals with teacher 2 (weights data/big2.pt), on top of the first teacher's proposals.
# Usage: bash data/propose2.sh <marker log> <marker text> <auto> <big1> <out> [<auto> <big1> <out> ...]
export PATH=$HOME/.local/bin:$PATH
cd ~/birdai || exit 1
L=data/logs/propose2.log
MLOG=$1; MTEXT=$2; shift 2
echo "propose2 waiting $(date +%H:%M:%S)" > $L
until grep -q "$MTEXT" "$MLOG" 2>/dev/null && [ -f data/big2.pt ]; do sleep 10; done
echo "propose2 start $(date +%H:%M:%S)" >> $L
while [ $# -ge 3 ]; do
  cat data/labels/$1.jsonl data/labels/$2.jsonl > data/labels/_tmp_$3.jsonl
  uv run --group train python data/big_propose.py data/big2.pt data/labels/_tmp_$3.jsonl data/frames data/labels/$3.jsonl > data/logs/propose-$3.log 2>&1
  echo "propose $3 exit $? $(date +%H:%M:%S)" >> $L
  sed -i 's/#big\([0-9]\)/#bigT2_\1/' data/labels/$3.jsonl   # ids must not collide with the first round's
  uv run --group train python data/embed.py data/labels/$3.jsonl data/frames > data/logs/embed-$3.log 2>&1
  echo "embed $3 exit $? $(date +%H:%M:%S)" >> $L
  shift 3
done
echo "propose2 done $(date +%H:%M:%S)" >> $L
