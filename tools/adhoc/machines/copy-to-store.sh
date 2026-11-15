#!/bin/bash
# main: copy everything the project needs to the store machine on another account (footage, frames, labels, datasets, models)
cd ~; IP=$1; L=~/birdai/data/logs/copy-to-store.log; echo "copy start $(date +%H:%M:%S)" > $L
R="ssh -o ConnectTimeout=15 -o StrictHostKeyChecking=accept-new"
ssh-keygen -R $IP >/dev/null 2>&1
for d in birdai/data/labels birdai/data/dataset_v8 birdai/data/dataset_fit birdai/data/dataset_exam birdai/data/v9keep birdai/data/sweep birdai/data/evo birdai/data/highlights birdai/data/squirrel_src birdai/data/squirrel_demo birdai/data/check_x birdai/data/review birdai/models birdai/models_v9 birdai/models_v8n birdai/models_s640b birdai/keep_from_fast birdai/data/dataset_v5 birdai/data/frames birdai/data/videos; do
  [ -e ~/$d ] || continue
  rsync -a --relative -e "$R" ./$d root@$IP: >> $L 2>&1; echo "$d exit $? $(date +%H:%M:%S)" >> $L
done
rsync -a --relative -e "$R" --exclude .venv --exclude 'data/frames' --exclude 'data/videos' --exclude 'data/dataset_v5' ./birdai root@$IP: >> $L 2>&1; echo "rest exit $? $(date +%H:%M:%S)" >> $L
echo "copy done $(date +%H:%M:%S)" >> $L
