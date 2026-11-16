#!/bin/bash
# main: score the finished size tests on the 5 exam days and on 12 Nov (same scorer as exam-more.sh)
cd ~/birdai; L=data/logs/exam-more2.log; echo "start $(date +%H:%M:%S)" > $L
sc() { # name weights imgsz
  for ds in exam:data/dataset_exam nov12:data/dataset_v8; do
    PYTHONPATH=.:tools .venv/bin/python data/evo_one.py --score-only --parent $2 --out /tmp/exam-score-$1 --imgsz $3 --fit-dataset ${ds#*:} --fit-split test --val-every 1 2>&1 | grep RESULT | sed "s#^#${ds%%:*} $1 #" >> $L
  done
}
sc s640_e30 data/sweep/birdai-g12/scored.pt 640
sc s960_e12 data/sweep/birdai-g5/scored.pt 960
sc m640_e12 data/sweep/birdai-g9/scored.pt 640
sc nano800 data/sweep/birdai-g15/scored.pt 800
sc nano960 models/student_v8a_960/runs/960/weights/best.pt 960
sc nano640 models/student_v8a_640/runs/640/weights/best.pt 640
echo "done $(date +%H:%M:%S)" >> $L
