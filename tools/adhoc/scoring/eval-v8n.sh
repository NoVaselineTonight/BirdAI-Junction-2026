#!/bin/bash
# main: choose model and cut-off with the 13 never-trained days as validation footage; test stays 12 Nov
export PATH=$HOME/.local/bin:$PATH
cd ~/birdai
D=data/dataset_v8n; M=${1:-models_v8n}; shift
C=${@:-two_stage student:640 student:960}
L=data/logs/v8neval.log; echo "v8neval start $(date +%H:%M:%S) -> $M ($C)" > $L
if [ ! -d $D ]; then
  mkdir -p $D/images $D/labels; cp data/dataset_v8/classes.json $D/
  ln -sfn ../../dataset_fit/images/test $D/images/val; ln -sfn ../../dataset_fit/labels/test $D/labels/val
  ln -sfn ../../dataset_v8/images/test $D/images/test; ln -sfn ../../dataset_v8/labels/test $D/labels/test
fi
echo "val $(ls $D/images/val | wc -l) frames, test $(ls $D/images/test | wc -l) frames" >> $L
if [ ! -d $M ]; then
  mkdir -p $M/student
  ln -sfn ../../models/student_v8a_960/960 $M/student/960
  ln -sfn ../../models/student_v8a_640/640 $M/student/640
  ln -sfn ../models/pretrained $M/pretrained
fi
uv run --group train python tools/evaluate.py --dataset $D --candidates $C \
  --models-dir $M --board-ms two_stage=169.8,960=1108.5,640=506.6 --promote > data/logs/eval-v8n.log 2>&1
echo "eval exit $? $(date +%H:%M:%S)" >> $L
grep -a "threshold\|SHIP" data/logs/eval-v8n.log | cut -c1-200 >> $L
echo "v8neval done $(date +%H:%M:%S)" >> $L
