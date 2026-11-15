#!/usr/bin/env bash
# Extra-days round, stage B (main): degraded copies, squirrel composites, dataset_v5; then send the dataset to birdai-fast.
export PATH=$HOME/.local/bin:$PATH
cd ~/birdai || exit 1
L=data/logs/v5build.log
echo "v5build start $(date +%H:%M:%S)" > $L
# the two preparation steps do not depend on each other, so they run side by side
( uv run --group train python data/degrade.py v5 4 > data/logs/v5degrade.log 2>&1; echo "degrade exit $? $(date +%H:%M:%S)" >> $L ) &
( uv run --group train python data/squirrel_paste.py v5 1500 > data/logs/v5paste.log 2>&1; echo "paste exit $? $(date +%H:%M:%S)" >> $L ) &
wait
grep -q "degrade exit 0" $L && grep -q "paste exit 0" $L || { echo "preparation failed" >> $L; exit 1; }
cat data/labels/v5.jsonl data/labels/lowq_v5.jsonl data/labels/squirrel_raw.jsonl data/labels/squirrel_synth.jsonl > data/labels/v5f.jsonl
rm -rf data/dataset_v5
uv run --group train python tools/build_dataset.py --labels data/labels/v5f.jsonl --corrections data/review/corrections_v5.csv \
  --frames data/frames --out data/dataset_v5 >> $L 2>&1
echo "dataset exit $? $(date +%H:%M:%S)" >> $L
grep -q "dataset exit 0" $L || exit 1
du -sh data/dataset_v5 >> $L
rsync -a -e "ssh -o StrictHostKeyChecking=accept-new -o ConnectTimeout=15" data/dataset_v5 root@MACHINE_IP:birdai/data/ >> $L 2>&1
echo "push exit $? $(date +%H:%M:%S)" >> $L
ssh -o ConnectTimeout=15 root@MACHINE_IP 'touch ~/birdai/data/dataset_v5.READY' >> $L 2>&1
