#!/usr/bin/env bash
# Extra-days round, stage A (main): collect the new frames and labels from the three workers, relabel all as tag v5.
# Usage: bash data/run-v5-a.sh [scan3] [scan4] [fast]   (everything already on main is always included)
export PATH=$HOME/.local/bin:$PATH
cd ~/birdai || exit 1
L=data/logs/v5a.log
echo "v5a start $(date +%H:%M:%S) workers: $*" > $L
declare -A IP=( [scan3]=MACHINE_IP [scan4]=MACHINE_IP [fast]=MACHINE_IP )
declare -A TAG=( [scan3]=5 [scan4]=6 [fast]=7 )
for w in "$@"; do
  ip=${IP[$w]}; t=${TAG[$w]}
  rsync -a -e "ssh -o StrictHostKeyChecking=accept-new -o ConnectTimeout=15" root@$ip:birdai/data/frames8/train/ data/frames/train/ >> $L 2>&1
  echo "$w frames copied exit $? $(date +%H:%M:%S)" >> $L
  for n in auto$t big$t big${t}b; do
    rsync -a -e "ssh -o ConnectTimeout=15" root@$ip:birdai/data/labels/$n.jsonl root@$ip:birdai/data/labels/$n.jsonl.emb.npz data/labels/ >> $L 2>&1
    [ -f data/labels/$n.jsonl.emb.npz ] || echo "MISSING $w $n" >> $L
  done
done
labels=""
for n in autoB auto2B bigB big2B bigBb big2Bb auto3 big3 big3b auto4 big4 big4b auto5 big5 big5b auto6 big6 big6b auto7 big7 big7b; do
  [ -f data/labels/$n.jsonl.emb.npz ] && labels="$labels data/labels/$n.jsonl" || echo "not used: $n" >> $L
done
ls data/frames/train | wc -l >> $L
echo "labels: $labels" >> $L
rm -f data/check/r3_*.jpg
uv run --group train python data/relabel3.py v5 $labels 2>&1 | grep -v "Warning\|warn" >> $L
echo "relabel exit ${PIPESTATUS[0]} $(date +%H:%M:%S)" >> $L
