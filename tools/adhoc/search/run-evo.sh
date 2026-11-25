#!/bin/bash
# birdai-evo: population-based training on 8 GPUs, fitness = days the lineage never trained on.
cd ~/birdai
L=data/logs/evo.log; echo "evo waiting for data $(date +%H:%M:%S)" > $L
until [ -f data/dataset_fit/classes.json ] && [ -d data/dataset_v8/images/test ]; do sleep 3; done
sleep 5
echo "evo start $(date +%H:%M:%S) fit frames $(ls data/dataset_fit/images/test | wc -l) train frames $(ls data/dataset_v8/images/train | wc -l)" >> $L
.venv/bin/python data/evolve.py --root data/evo/run1 --start models/student_v8a_640/runs/640/weights/best.pt \
  --gpus 0,1,2,3,4,5,6,7 --per-gpu 2 --generations 60 --workers 9 --fit-dataset data/dataset_fit --fit-split test --val-every 2 >> $L 2>&1
echo "evo exit $? $(date +%H:%M:%S)" >> $L
