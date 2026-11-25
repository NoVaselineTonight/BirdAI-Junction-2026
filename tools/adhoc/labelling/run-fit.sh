#!/bin/bash
# main: build machine-checked labels for frames of days the v8 lineage never trained on (the 19 extra October days,
# validation-split frames, minus the frozen-camera day 30 Oct). 13 days -> fitness set, 5 days -> exam set.
export PATH=$HOME/vlm/bin:$HOME/.local/bin:$PATH
cd ~/birdai
L=data/logs/fit.log; echo "fit start $(date +%H:%M:%S)" > $L
rm -rf data/dataset_x data/check_x data/dataset_xk data/dataset_fit data/dataset_exam
mkdir -p data/dataset_x/images/test data/dataset_x/labels/test
cp data/dataset_v5/classes.json data/dataset_v5/split.json data/dataset_x/
sed "s#data/dataset_v5#data/dataset_x#" data/dataset_v5/data.yaml > data/dataset_x/data.yaml
ls data/dataset_v5/images/val | grep -E "talvilintulive-202610(01|02|03|04|06|07|09|10|11|13|14|16|17|19|21|23|25|27)-h" > /tmp/x-list.txt
while read f; do ln data/dataset_v5/images/val/$f data/dataset_x/images/test/$f; cp data/dataset_v5/labels/val/${f%.jpg}.txt data/dataset_x/labels/test/ 2>/dev/null || : > data/dataset_x/labels/test/${f%.jpg}.txt; done < /tmp/x-list.txt
echo "staged $(ls data/dataset_x/images/test | wc -l) frames $(date +%H:%M:%S)" >> $L
.venv/bin/python data/cand.py data/dataset_x test data/check_x > data/logs/cand-x.log 2>&1; echo "cand $? $(wc -l < data/check_x/cands-0of1.jsonl) $(date +%H:%M:%S)" >> $L
OMP_NUM_THREADS=1 setsid -f $HOME/vlm/bin/vllm serve Qwen/Qwen3-VL-8B-Instruct --port 8000 --max-model-len 4096 --gpu-memory-utilization 0.30 --limit-mm-per-prompt.video 0 --mm-processor-cache-gb 0 --max-num-seqs 128 > ~/vlm-server.log 2>&1
until curl -s -m 3 http://127.0.0.1:8000/v1/models | grep -q Qwen; do sleep 5; done
echo "judge server up $(date +%H:%M:%S)" >> $L
~/vlm/bin/python data/judge.py data/check_x --workers 128 > data/logs/judge-x.log 2>&1
~/vlm/bin/python data/judge.py data/check_x --workers 64 >> data/logs/judge-x.log 2>&1
echo "judged $(wc -l < data/check_x/verdicts.jsonl) $(date +%H:%M:%S)" >> $L
pkill -f "vllm[ ]serve"
OMP_NUM_THREADS=1 .venv/bin/python data/truth.py data/dataset_x data/check_x data/dataset_xk test --procs 24 > data/logs/truth-x.log 2>&1; echo "truth $? $(date +%H:%M:%S)" >> $L
for d in fit exam; do mkdir -p data/dataset_$d/images/test data/dataset_$d/labels/test; cp data/dataset_xk/classes.json data/dataset_$d/; done
for f in data/dataset_xk/images/test/*.jpg; do b=$(basename $f .jpg)
  if echo $b | grep -qE "talvilintulive-202610(03|09|14|19|25)-h"; then d=exam; else d=fit; fi
  ln $f data/dataset_$d/images/test/$b.jpg; cp data/dataset_xk/labels/test/$b.txt data/dataset_$d/labels/test/
done
echo "fit frames $(ls data/dataset_fit/images/test | wc -l) exam frames $(ls data/dataset_exam/images/test | wc -l) $(date +%H:%M:%S)" >> $L
echo "fit done $(date +%H:%M:%S)" >> $L
