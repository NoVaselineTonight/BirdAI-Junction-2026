#!/usr/bin/env bash
# Final round, stage A (main machine): collect frames and labels from the workers, then relabel everything as tag v3.
# Usage: bash data/run-v3-a.sh [scan3] [scan4]     (main's own files autoB/auto2B/bigB/big2B are always included)
export PATH=$HOME/.local/bin:$PATH
cd ~/birdai || exit 1
L=data/logs/v3a.log
echo "v3a start $(date +%H:%M:%S) workers: $*" > $L
declare -A IP=( [scan3]=MACHINE_IP [scan4]=MACHINE_IP )
declare -A LAB=( [scan3]="auto3 big3 big3b" [scan4]="auto4 big4 big4b" )
labels=""
for n in autoB auto2B bigB big2B bigBb big2Bb; do
  [ -f data/labels/$n.jsonl.emb.npz ] && labels="$labels data/labels/$n.jsonl" || echo "MISSING main $n" >> $L
done
for w in "$@"; do
  ip=${IP[$w]}
  rsync -a -e "ssh -o ConnectTimeout=15" root@$ip:birdai/data/frames/train/ data/frames/train/ >> $L 2>&1
  echo "$w frames copied exit $? $(date +%H:%M:%S)" >> $L
  for n in ${LAB[$w]}; do
    rsync -a -e "ssh -o ConnectTimeout=15" root@$ip:birdai/data/labels/$n.jsonl root@$ip:birdai/data/labels/$n.jsonl.emb.npz data/labels/ >> $L 2>&1
    [ -f data/labels/$n.jsonl.emb.npz ] && labels="$labels data/labels/$n.jsonl" || echo "MISSING $w $n" >> $L
  done
done
ls data/frames/train | tr "\n" " " >> $L; echo >> $L
echo "labels: $labels" >> $L
rm -f data/check/r3_*.jpg
uv run --group train python data/relabel3.py v3 $labels 2>&1 | grep -v "Warning\|warn" >> $L
echo "relabel exit ${PIPESTATUS[0]} $(date +%H:%M:%S)" >> $L
