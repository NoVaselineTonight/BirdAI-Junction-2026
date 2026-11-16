#!/bin/bash
# 8-GPU machine: more days of our own feeder camera. Videos arrive by relay as data/videos_$TAG/train/talvilintulive-YYYYMMDD.mp4.
# pick bird frames -> teacher labels (8 GPUs) -> candidates (8 GPUs) -> judge (8 servers) -> checked labels (data/dataset_${TAG}k)
export PATH=$HOME/vlm/bin:$HOME/.local/bin:$PATH
cd ~/birdai
TAG=$1; L=data/logs/proc-$TAG.log; echo "proc-own $TAG start $(date +%H:%M:%S)" > $L
pkill -f "data/run-job.s[h]"; pkill -f "data/evolve.p[y]"; pkill -f "data/evo_one.p[y]"
if ! command -v ffmpeg >/dev/null || ! command -v ninja >/dev/null; then
  DEBIAN_FRONTEND=noninteractive apt-get update > data/logs/apt.log 2>&1
  DEBIAN_FRONTEND=noninteractive apt-get install -y ffmpeg python3.12-dev ninja-build build-essential >> data/logs/apt.log 2>&1
fi
V=data/videos_$TAG; F=data/frames_$TAG; mkdir -p $V/train data/labels
until [ -f ~/proc-assets-done ] && [ -f data/dataset_v8/classes.json ] && [ -x .venv/bin/python ]; do sleep 10; done
echo "tools here $(date +%H:%M:%S)" >> $L
# pick frames from each day as its video arrives (complete files only: the relay renames a file into place when it is whole), then delete the video
mkdir -p $F/train ${F}_parts ${V}_work
mine_one() {
  v=$1; n=$(basename $v); stem=${n%.*}
  mkdir -p ${V}_work/$stem/train; mv $v ${V}_work/$stem/train/
  .venv/bin/python tools/mine_frames.py --videos ${V}_work/$stem --out ${F}_parts/$stem --workers 28 > data/logs/mine-$TAG-$stem.log 2>&1
  rc=$?; k=$(find ${F}_parts/$stem -name '*.jpg' | wc -l)
  [ -d ${F}_parts/$stem/train/$stem ] && mv ${F}_parts/$stem/train/$stem $F/train/
  rm -rf ${V}_work/$stem
  echo "mined $stem exit $rc frames $k $(date +%H:%M:%S)" >> $L
}
while true; do
  started=0
  for v in $V/train/*.mp4; do
    [ -f "$v" ] || continue
    while [ $(jobs -rp | wc -l) -ge 4 ]; do sleep 5; done
    mine_one $v & started=1; sleep 2
  done
  if [ -f $V/READY ] && [ -z "$(ls $V/train/*.mp4 2>/dev/null)" ]; then break; fi
  sleep 15
done
wait
echo "mining done: $(ls $F/train | wc -l) days, $(find $F -name '*.jpg' | wc -l) frames $(date +%H:%M:%S)" >> $L
rm -rf $V ${V}_work
i=0; for d in $F/train/*/; do s=$((i % 8)); mkdir -p ${F}_s$s/train; ln -sfn $(realpath $d) ${F}_s$s/train/$(basename $d); i=$((i+1)); done
for s in 0 1 2 3 4 5 6 7; do [ -d ${F}_s$s ] && CUDA_VISIBLE_DEVICES=$s .venv/bin/python tools/autolabel.py --frames ${F}_s$s --out data/labels/auto_${TAG}_$s.jsonl --box-conf 0.05 > data/logs/label-$TAG-$s.log 2>&1 & done; wait
cat data/labels/auto_${TAG}_?.jsonl > data/labels/auto_$TAG.jsonl
echo "label done rows $(wc -l < data/labels/auto_$TAG.jsonl) $(date +%H:%M:%S)" >> $L
D=data/dataset_$TAG; C=data/check_$TAG; rm -rf $D $C ${D}k
.venv/bin/python data/stage_xf.py $D data/labels/auto_$TAG.jsonl:$F > data/logs/stage-$TAG.log 2>&1
echo "stage exit $? $(ls $D/images/train | wc -l) frames $(date +%H:%M:%S)" >> $L
for s in 0 1 2 3 4 5 6 7; do CUDA_VISIBLE_DEVICES=$s .venv/bin/python data/cand.py $D train $C --shard $s/8 > data/logs/cand-$TAG-$s.log 2>&1 & done; wait
echo "cand done $(cat $C/cands-*.jsonl | wc -l) candidates $(date +%H:%M:%S)" >> $L
for s in 0 1 2 3 4 5 6 7; do
  CUDA_VISIBLE_DEVICES=$s OMP_NUM_THREADS=1 setsid -f $HOME/vlm/bin/vllm serve Qwen/Qwen3-VL-8B-Instruct --port $((8000+s)) --max-model-len 4096 --gpu-memory-utilization 0.5 --limit-mm-per-prompt.video 0 --mm-processor-cache-gb 0 --max-num-seqs 128 > ~/vlm-server-$s.log 2>&1
done
for i in $(seq 1 240); do n=0; for p in 0 1 2 3 4 5 6 7; do curl -s -m 3 http://127.0.0.1:$((8000+p))/v1/models | grep -q Qwen && n=$((n+1)); done; [ $n = 8 ] && break; sleep 5; done
echo "judge servers up: $n of 8 $(date +%H:%M:%S)" >> $L
PORTS=$(for p in 0 1 2 3 4 5 6 7; do curl -s -m 3 http://127.0.0.1:$((8000+p))/v1/models | grep -q Qwen && printf "%s," $((8000+p)); done | sed 's/,$//')
~/vlm/bin/python data/judge.py $C --ports $PORTS --workers 640 > data/logs/judge-$TAG.log 2>&1
~/vlm/bin/python data/judge.py $C --ports $PORTS --workers 128 >> data/logs/judge-$TAG.log 2>&1
echo "judged $(wc -l < $C/verdicts.jsonl) $(date +%H:%M:%S)" >> $L
pkill -f "vllm[ ]serve"; sleep 8
OMP_NUM_THREADS=1 .venv/bin/python data/truth.py $D $C ${D}k train --procs 120 > data/logs/truth-$TAG.log 2>&1
echo "truth exit $? kept frames $(ls ${D}k/images/train 2>/dev/null | wc -l) $(date +%H:%M:%S)" >> $L
tail -25 data/logs/truth-$TAG.log >> $L
echo "proc-own $TAG done $(date +%H:%M:%S)" >> $L
