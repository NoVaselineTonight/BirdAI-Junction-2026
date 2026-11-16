#!/usr/bin/env bash
# Final round, stage B1 (main): degraded copies, squirrel composites, dataset_v4; then send the dataset to birdai-fast.
export PATH=$HOME/.local/bin:$PATH
cd ~/birdai || exit 1
L=data/logs/v4build.log
echo "v4build start $(date +%H:%M:%S)" > $L
uv run --group train python data/degrade.py v4 4 >> $L 2>&1 || { echo "degrade failed" >> $L; exit 1; }
uv run --group train python data/squirrel_paste.py v4 1500 >> $L 2>&1 || { echo "paste failed" >> $L; exit 1; }
cat data/labels/v4.jsonl data/labels/lowq_v4.jsonl data/labels/squirrel_raw.jsonl data/labels/squirrel_synth.jsonl > data/labels/v4f.jsonl
rm -rf data/dataset_v4
uv run --group train python tools/build_dataset.py --labels data/labels/v4f.jsonl --corrections data/review/corrections_v4.csv \
  --frames data/frames --out data/dataset_v4 >> $L 2>&1
echo "dataset exit $? $(date +%H:%M:%S)" >> $L
grep -q "dataset exit 0" $L || exit 1
du -sh data/dataset_v4 >> $L
rsync -a -e "ssh -o StrictHostKeyChecking=accept-new -o ConnectTimeout=15" data/dataset_v4 root@MACHINE_IP:birdai/data/ >> $L 2>&1
echo "push exit $? $(date +%H:%M:%S)" >> $L
ssh -o ConnectTimeout=15 root@MACHINE_IP 'touch ~/birdai/data/dataset_v4.READY' >> $L 2>&1
