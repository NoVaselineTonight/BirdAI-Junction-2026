#!/bin/bash
# birdai-check: after the checked dataset exists, stop the judge servers and train four students side by side.
export PATH=$HOME/.local/bin:$PATH
cd ~/birdai
L=data/logs/train8.log; echo "train8 waiting $(date +%H:%M:%S)" > $L
until grep -q "judge done" data/logs/judge.log; do sleep 3; done
pkill -f "vllm serve"; sleep 8
echo "train8 start $(date +%H:%M:%S)" >> $L
K=keep_from_fast/models
run() { # gpu name imgsz epochs base
  ( CUDA_VISIBLE_DEVICES=$1 PYTHONPATH=.:tools .venv/bin/python data/train_v8.py --data data/dataset_v8/data.yaml --imgsz $3 --epochs $4 --base $5 --out models/student_$2 > data/logs/train-$2.log 2>&1
    echo "$2 exit $? $(date +%H:%M:%S)" >> $L
    PYTHONPATH=. .venv/bin/python data/rescore.py data/dataset_v8 models/student_$2/$3 $2 2>&1 | grep "labels-as-is\|birds [0-9]" > data/logs/k8-$2.log
    echo "$2 scored $(date +%H:%M:%S)" >> $L ) &
}
run 0 v8a_640 640 8 $K/student_v4_640/runs/640/weights/best.pt
run 1 v8a_960 960 6 $K/student_v4_960/runs/960/weights/best.pt
run 2 v8b_640 640 20 yolo26n.pt
run 3 v8b_960 960 14 yolo26n.pt
for spec in "models_v4/student v4-640" "models_v4/student/960 v4-960"; do set -- $spec
  ( PYTHONPATH=. .venv/bin/python data/rescore.py data/dataset_v8 $1 $2 2>&1 | grep "labels-as-is\|birds [0-9]" > data/logs/k8-$2.log ) &
done
wait
echo "train8 done $(date +%H:%M:%S)" >> $L
