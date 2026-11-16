#!/bin/bash
# main: push code, environment, checked training set, fitness/exam sets and seed weights to a new machine
cd ~/birdai
IP=$1; T=$(echo $IP | tr . -)
L=data/logs/push-$T.log; echo "push start $(date +%H:%M:%S)" > $L
R="ssh -o ConnectTimeout=15 -o StrictHostKeyChecking=accept-new"
rsync -a -e "$R" --exclude '/data' --exclude '/models*' --exclude '/.git' --exclude '/runs*' --exclude '/keep_from_fast' --exclude '/weights' --exclude '*.pt' ./ root@$IP:birdai/ >> $L 2>&1
echo "code+env $? $(date +%H:%M:%S)" >> $L
rsync -a -e "$R" --relative models/student_v8a_640/runs/640/weights/best.pt data/evo_one.py data/evolve.py data/train_big.py data/score_loop.sh yolo26n.pt root@$IP:birdai/ >> $L 2>&1
S=data/evo/run1/best-weights.pt; [ -f $S ] || S=models/student_v8a_640/runs/640/weights/best.pt
rsync -a -e "$R" $S root@$IP:birdai/data/seed.pt >> $L 2>&1
echo "weights $? (seed $S) $(date +%H:%M:%S)" >> $L
cd data/dataset_v8
( ls classes.json split.json data.yaml; find images/train labels/train -type f \( -name '*.jpg' -o -name '*.txt' \) ) > /tmp/push-$T-list.txt
rm -f /tmp/push-$T-part-*; split -n l/8 /tmp/push-$T-list.txt /tmp/push-$T-part-
for f in /tmp/push-$T-part-*; do rsync -a -e "$R" --files-from=$f ./ root@$IP:birdai/data/dataset_v8/ & done
wait
cd ~/birdai
echo "train set $(date +%H:%M:%S)" >> $L
rsync -a -e "$R" data/dataset_fit data/dataset_exam root@$IP:birdai/data/ >> $L 2>&1
rsync -a -e "$R" --relative data/dataset_v8/images/test data/dataset_v8/labels/test root@$IP:birdai/ >> $L 2>&1
echo "push done $(date +%H:%M:%S)" >> $L
