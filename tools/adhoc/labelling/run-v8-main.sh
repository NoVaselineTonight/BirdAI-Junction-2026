#!/bin/bash
cd ~/birdai
L=data/logs/v8main.log; echo "v8main start $(date +%H:%M:%S)" > $L
rm -rf data/dataset_v8
for s in test val; do OMP_NUM_THREADS=1 .venv/bin/python data/truth.py data/dataset_v5 data/check_$s data/dataset_v8 $s --procs 24 > data/logs/truth-main-$s.log 2>&1; echo "truth $s $? $(date +%H:%M:%S)" >> $L; done
mkdir -p data/dataset_v8/images/train data/dataset_v8/labels/train
echo "v8main done $(date +%H:%M:%S)" >> $L
