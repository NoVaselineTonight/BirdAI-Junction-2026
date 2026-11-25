#!/bin/bash
# main: give a machine what it needs to label new footage: checker environment and model, teachers, the three vote students
cd ~/birdai
IP=$1; L=data/logs/push-proc.log; echo "proc push start $(date +%H:%M:%S)" > $L
R="ssh -o ConnectTimeout=15 -o StrictHostKeyChecking=accept-new"
until ssh -o ConnectTimeout=10 -o StrictHostKeyChecking=accept-new root@$IP 'mkdir -p ~/birdai/data/logs ~/.cache' 2>/dev/null; do sleep 5; done
rsync -a -e "$R" ~/vlm root@$IP: >> $L 2>&1 &
rsync -a -e "$R" ~/.cache/huggingface root@$IP:.cache/ >> $L 2>&1 &
rsync -a -e "$R" --relative models/pretrained yolo26x.pt yolo26s.pt data/big2.pt data/cand.py data/judge.py data/truth.py data/stage_xf.py data/proc-new.sh \
  keep_from_fast/models/student_v4_640/runs/640/weights/best.pt keep_from_fast/models/student_v4_960/runs/960/weights/best.pt keep_from_fast/models/student_v5_960/runs/960/weights/best.pt \
  root@$IP:birdai/ >> $L 2>&1
wait
ssh -o ConnectTimeout=10 root@$IP 'touch ~/proc-assets-done'
echo "proc push done $(date +%H:%M:%S)" >> $L
