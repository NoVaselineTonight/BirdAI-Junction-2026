#!/bin/bash
cd ~/birdai
L=data/logs/judge.log
rm -rf data/dataset_v8/images/train data/dataset_v8/labels/train
OMP_NUM_THREADS=1 .venv/bin/python data/truth.py data/dataset_v5 data/check_train data/dataset_v8 train --procs 200 > data/logs/truth-train.log 2>&1; echo "truth train $? $(date +%H:%M:%S)" >> $L
echo "judge done $(date +%H:%M:%S)" >> $L
