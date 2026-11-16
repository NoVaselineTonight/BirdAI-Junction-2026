#!/bin/bash
# 8-GPU machine: snapshot each v9 run's latest weights and score them on the exam days, 12 Nov and the selection days.
cd ~/birdai; T=$(date +%H%M); L=data/logs/snap-$T.log; mkdir -p data/snap/$T; : > $L
cp models/student_v8a_960/runs/960/weights/best.pt data/snap/$T/base_960.pt
cp models/student_v8a_640/runs/640/weights/best.pt data/snap/$T/base_640.pt
for n in v9_960_e8 v9_960_e14 v9_640_e8 v8_960_e8_control; do
  cp data/v9runs/$n/t/weights/last.pt data/snap/$T/$n.pt
  echo "epochs $n $(($(wc -l < data/v9runs/$n/t/results.csv) - 1)) $( [ -f data/v9runs/$n/done ] && echo finished || echo running)" >> $L
done
g=0
for n in base_960 v9_960_e8 v9_960_e14 v8_960_e8_control base_640 v9_640_e8; do
  sz=960; case $n in *640*) sz=640;; esac
  ( for ds in exam:data/dataset_exam nov12:data/dataset_v8 fit:data/dataset_fit; do
      CUDA_VISIBLE_DEVICES=$g PYTHONPATH=.:tools .venv/bin/python data/evo_one.py --score-only --parent data/snap/$T/$n.pt --out /tmp/snap-$T-$n --imgsz $sz --fit-dataset ${ds#*:} --fit-split test --val-every 1 2>&1 | grep RESULT | sed "s#^#${ds%%:*} $n #" >> $L
    done ) &
  g=$((g+1))
done; wait
echo "snap done $(date +%H:%M:%S)" >> $L
