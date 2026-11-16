#!/bin/bash
# main -> birdai-check: code, env, weights, and the 25-day part of dataset_v5 (the 19 extra October days left out)
cd ~/birdai
IP=MACHINE_IP
L=data/logs/push-check.log; echo "push start $(date +%H:%M:%S)" > $L
R="ssh -o ConnectTimeout=15"
rsync -a -e "$R" --exclude '/data' --exclude '/models*' --exclude '/.git' --exclude '/runs*' --exclude '/keep_from_fast' --exclude '/weights' --exclude '*.pt' ./ root@$IP:birdai/ >> $L 2>&1
echo "code+env $? $(date +%H:%M:%S)" >> $L
rsync -a -e "$R" --relative keep_from_fast/models data/big2.pt data/cand.py data/judge.py data/rescore.py models_v4/student models/pretrained root@$IP:birdai/ >> $L 2>&1
echo "weights $? $(date +%H:%M:%S)" >> $L
cd data/dataset_v5
SKIP='talvilintulive-202610(01|02|03|04|06|07|09|10|11|13|14|16|17|19|21|23|25|27|30)'
( ls classes.json split.json data.yaml; find images/train images/val labels/train labels/val -type f \( -name '*.jpg' -o -name '*.txt' \) | grep -Ev "$SKIP"; find images/test labels/test -type f ) > /tmp/push-list.txt
echo "files $(wc -l < /tmp/push-list.txt) $(date +%H:%M:%S)" >> ../../$L
split -n l/8 /tmp/push-list.txt /tmp/push-part-
for f in /tmp/push-part-*; do rsync -a -e "$R" --files-from=$f ./ root@$IP:birdai/data/dataset_v5/ & done
wait
cd ~/birdai
echo "push done $(date +%H:%M:%S)" >> $L
