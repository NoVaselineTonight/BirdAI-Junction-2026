#!/bin/bash
# main: score more models on the 5 exam days (never used for any choice) and on the 13 selection days, same scorer
cd ~/birdai; L=data/logs/exam-more.log; echo "start $(date +%H:%M:%S)" > $L
sc() { # name weights imgsz
  for ds in exam fit; do
    PYTHONPATH=.:tools .venv/bin/python data/evo_one.py --score-only --parent $2 --out /tmp/exam-score-$1 --imgsz $3 --fit-dataset data/dataset_$ds --fit-split test --val-every 1 2>&1 | grep RESULT | sed "s#^#$ds $1 #" >> $L
  done
}
sc nano640 models/student_v8a_640/runs/640/weights/best.pt 640
sc nano960 models/student_v8a_960/runs/960/weights/best.pt 960
sc evolved640 data/evo/run1/best-weights.pt 640
sc s640 data/sweep/s640-main/t/weights/last.pt 640
echo "done $(date +%H:%M:%S)" >> $L
