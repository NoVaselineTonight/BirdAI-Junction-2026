#!/bin/bash
# main: fetch the v6 students from birdai-fast and score them like the others (rescore.py, dataset_v5 test labels)
cd ~/birdai
L=data/logs/v6eval.log; : > $L
mkdir -p models/student_v6_960 models/student_v6_640
rsync -a -e "ssh -o ConnectTimeout=15" root@MACHINE_IP:birdai/models/student_v6_960/960 models/student_v6_960/ >> $L 2>&1
rsync -a -e "ssh -o ConnectTimeout=15" root@MACHINE_IP:birdai/models/student_v6_640/640 models/student_v6_640/ >> $L 2>&1
for s in 640 960; do
  ( PYTHONPATH=. .venv/bin/python data/rescore.py data/dataset_v5 models/student_v6_$s/$s v6-$s 2>&1 | grep -v "Warning\|warn\|INFO" > data/logs/rescore-v6-$s.log ) &
done
wait
cat data/logs/rescore-v6-640.log data/logs/rescore-v6-960.log >> $L
echo "v6eval done $(date +%H:%M:%S)" >> $L
