#!/bin/bash
cd ~/birdai
L=data/logs/v8main.log
rm -rf data/dataset_v8/images/train data/dataset_v8/labels/train
OMP_NUM_THREADS=1 .venv/bin/python data/truth.py data/dataset_v5 data/check_train data/dataset_v8 train --procs 26 > data/logs/truth-main-train.log 2>&1; echo "truth train $? $(date +%H:%M:%S)" >> $L
cd data/dataset_v8
for d in images/train labels/train; do find $d -type f | grep -E "talvilintulive-202610(01|02|03|04|06|07|09|10|11|13|14|16|17|19|21|23|25|27|30)-h" | xargs -r rm -f; done
cd ~/birdai
echo "train frames $(ls data/dataset_v8/images/train | wc -l) labels $(ls data/dataset_v8/labels/train | wc -l) $(date +%H:%M:%S)" >> $L
rm -f data/dataset_v8/labels/*.cache
echo "v8 train ready $(date +%H:%M:%S)" >> $L
