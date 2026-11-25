#!/bin/bash
# main: send the unchecked training frames of the 13 selection days (dataset_v5 train split) and the checking assets
cd ~/birdai
IP=$1; L=data/logs/push-x2.log; echo "x2 push start $(date +%H:%M:%S)" > $L
R="ssh -o ConnectTimeout=15 -o StrictHostKeyChecking=accept-new"
until ssh -o ConnectTimeout=10 -o StrictHostKeyChecking=accept-new root@$IP 'mkdir -p ~/birdai/data/dataset_x2/images/train ~/birdai/data/dataset_x2/labels/train ~/birdai/data/logs' 2>/dev/null; do sleep 5; done
cd data/dataset_v5
ls images/train | grep -E "talvilintulive-202610(01|02|04|06|07|10|11|13|16|17|21|23|27)-h" > /tmp/x2-stems.txt
( sed 's#^#images/train/#' /tmp/x2-stems.txt; sed 's#^#labels/train/#; s#\.jpg$#.txt#' /tmp/x2-stems.txt; echo classes.json ) > /tmp/x2-list.txt
rm -f /tmp/x2-part-*; split -n l/8 /tmp/x2-list.txt /tmp/x2-part-
for f in /tmp/x2-part-*; do rsync -a --ignore-missing-args -e "$R" --files-from=$f ./ root@$IP:birdai/data/dataset_x2/ & done
wait
cd ~/birdai
rsync -a -e "$R" --relative models/student_v8a_960/runs/960/weights/best.pt data/run-v9.sh root@$IP:birdai/ >> $L 2>&1
echo "x2 frames sent $(wc -l < /tmp/x2-stems.txt) $(date +%H:%M:%S)" >> $L
bash data/push-proc.sh $IP
ssh -o ConnectTimeout=10 root@$IP 'touch ~/x2-frames-done'
echo "x2 push done $(date +%H:%M:%S)" >> $L
