#!/usr/bin/env bash
# Main: when the big teacher is trained, hand its weights to the workers; when main's relabel is done, merge the
# 9-11 Nov frames in and let the big teacher propose missed birds on main's training frames; embed the proposals.
export PATH=$HOME/.local/bin:$PATH
cd ~/birdai || exit 1
L=data/logs/after-big.log
echo "after-big waiting $(date +%H:%M:%S)" > $L
until grep -q "big exit" data/logs/big.log 2>/dev/null; do sleep 10; done
cat data/logs/big.log >> $L
cp runs_big/t1/weights/best.pt data/big.pt || { echo "no weights" >> $L; exit 1; }
for ip in MACHINE_IP MACHINE_IP; do
  scp -o ConnectTimeout=15 data/big.pt root@$ip:birdai/data/big.pt.part >> $L 2>&1 && ssh -o ConnectTimeout=15 root@$ip 'mv ~/birdai/data/big.pt.part ~/birdai/data/big.pt' >> $L 2>&1
  echo "weights to $ip exit $? $(date +%H:%M:%S)" >> $L
done
until grep -q "all done" data/logs/relabel-main.log 2>/dev/null; do sleep 10; done
if [ -d data/frames2/train ]; then mv data/frames2/train/* data/frames/train/ && rmdir data/frames2/train && echo "frames2 merged" >> $L; fi
for pair in "autoB bigB" "auto2B big2B"; do
  set -- $pair
  uv run --group train python data/big_propose.py data/big.pt data/labels/$1.jsonl data/frames data/labels/$2.jsonl > data/logs/propose-$2.log 2>&1
  echo "propose $2 exit $? $(date +%H:%M:%S)" >> $L
  uv run --group train python data/embed.py data/labels/$2.jsonl data/frames > data/logs/embed-$2.log 2>&1
  echo "embed $2 exit $? $(date +%H:%M:%S)" >> $L
done
echo "after-big done $(date +%H:%M:%S)" >> $L
