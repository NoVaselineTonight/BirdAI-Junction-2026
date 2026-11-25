#!/usr/bin/env bash
# Main: fetch the two final students from birdai-fast and measure them on the held-out day.
export PATH=$HOME/.local/bin:$PATH
cd ~/birdai || exit 1
L=data/logs/v5eval.log
echo "v5eval start $(date +%H:%M:%S)" > $L
mkdir -p models/student_v5_960 models/student_v5_640 models_v5/student
rsync -a -e "ssh -o ConnectTimeout=15" root@MACHINE_IP:birdai/models/student_v5_960/960 models/student_v5_960/ >> $L 2>&1
rsync -a -e "ssh -o ConnectTimeout=15" root@MACHINE_IP:birdai/models/student_v5_640/640 models/student_v5_640/ >> $L 2>&1
ln -sfn ../../models/student_v5_960/960 models_v5/student/960
ln -sfn ../../models/student_v5_640/640 models_v5/student/640
ln -sfn ../models/pretrained models_v5/pretrained
ls -la models_v5/student/960/ models_v5/student/640/ >> $L 2>&1
uv run --group train python tools/evaluate.py --dataset data/dataset_v5 --candidates two_stage student:960 student:640 \
  --models-dir models_v5 > data/logs/eval-v5.log 2>&1
echo "eval exit $? $(date +%H:%M:%S)" >> $L
for s in 960 640; do uv run --group train python data/curve.py data/dataset_v5 models_v5 $s 2>&1 | grep -v "Warning\|warn\|INFO" > data/logs/curve-v5-$s.log; done
echo "curves done $(date +%H:%M:%S)" >> $L
