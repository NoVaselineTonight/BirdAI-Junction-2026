#!/bin/bash
cd ~/birdai
IP=MACHINE_IP
L=data/logs/push-evo.log; echo "push start $(date +%H:%M:%S)" > $L
R="ssh -o ConnectTimeout=15 -o StrictHostKeyChecking=accept-new"
rsync -a -e "$R" --exclude '/data' --exclude '/models*' --exclude '/.git' --exclude '/runs*' --exclude '/keep_from_fast' --exclude '/weights' --exclude '*.pt' ./ root@$IP:birdai/ >> $L 2>&1
echo "code+env $? $(date +%H:%M:%S)" >> $L
rsync -a -e "$R" --relative models/student_v8a_640/runs/640/weights/best.pt data/evo_one.py data/evolve.py data/rescore.py yolo26n.pt root@$IP:birdai/ >> $L 2>&1
echo "weights $? $(date +%H:%M:%S)" >> $L
cd data/dataset_v8
( ls classes.json split.json data.yaml; find images/train labels/train -type f \( -name '*.jpg' -o -name '*.txt' \) ) > /tmp/push-evo-list.txt
split -n l/8 /tmp/push-evo-list.txt /tmp/push-evo-part-
for f in /tmp/push-evo-part-*; do rsync -a -e "$R" --files-from=$f ./ root@$IP:birdai/data/dataset_v8/ & done
wait
cd ~/birdai
echo "train set $? $(date +%H:%M:%S)" >> $L
until grep -q 'fit done' data/logs/fit.log; do sleep 5; done
rsync -a -e "$R" data/dataset_fit data/dataset_exam root@$IP:birdai/data/ >> $L 2>&1
rsync -a -e "$R" --relative data/dataset_v8/images/test data/dataset_v8/labels/test root@$IP:birdai/ >> $L 2>&1
echo "push done $(date +%H:%M:%S)" >> $L
