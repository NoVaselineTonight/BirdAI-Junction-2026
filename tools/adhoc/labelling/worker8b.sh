#!/usr/bin/env bash
# birdai-fast only: the miner handles one piece at a time in its second pass, so the pieces not yet mined are
# split over K miners that run side by side; labelling is then split over the two GPUs.
# Usage: bash data/worker8b.sh <tag number> <K miners> <decoders per miner>
export PATH=$HOME/.local/bin:$PATH
cd ~/birdai || exit 1
N=$1; K=${2:-6}; W=${3:-6}
L=data/logs/worker8.log
echo "worker8b start $(date +%H:%M:%S) K=$K W=$W" >> $L
# pieces already mined: every frame folder except the newest one (the miner was stopped inside it)
newest=$(ls -t data/frames8/train | head -1)
[ -n "$newest" ] && rm -rf "data/frames8/train/$newest"
echo "kept $(ls data/frames8/train | wc -l) mined pieces, redoing from $newest" >> $L
i=0
for v in data/videos8c/train/*.mp4; do
  s=$(basename "$v" .mp4)
  [ -d "data/frames8/train/$s" ] && continue
  k=$((i % K)); i=$((i + 1))
  mkdir -p data/videos8c_$k/train
  ln -f "$v" data/videos8c_$k/train/
done
echo "pieces to mine: $i" >> $L
for k in $(seq 0 $((K - 1))); do
  [ -d data/videos8c_$k ] || continue
  ( uv run --group train python tools/mine_frames.py --videos data/videos8c_$k --out data/frames8_$k --workers $W --max-per-video 300 \
      > data/logs/mine8_$k.log 2>&1; echo "mine $k exit $? $(date +%H:%M:%S)" >> $L ) &
done
wait
for k in $(seq 0 $((K - 1))); do
  [ -d data/frames8_$k/train ] && mv data/frames8_$k/train/* data/frames8/train/ 2>> $L
done
echo "mined pieces: $(ls data/frames8/train | wc -l), frames: $(find data/frames8/train -name '*.jpg' | wc -l) $(date +%H:%M:%S)" >> $L
rm -rf data/videos8c data/videos8c_*
# label in two halves, one per GPU
mkdir -p data/frames8A/train data/frames8B/train
j=0
for d in data/frames8/train/*; do
  if [ $((j % 2)) -eq 0 ]; then mv "$d" data/frames8A/train/; else mv "$d" data/frames8B/train/; fi
  j=$((j + 1))
done
( CUDA_VISIBLE_DEVICES=1 uv run --group train python tools/autolabel.py --frames data/frames8A --out data/labels/auto${N}A.jsonl --box-conf 0.05 > data/logs/label-auto${N}A.log 2>&1; echo "label A exit $? $(date +%H:%M:%S)" >> $L ) &
( CUDA_VISIBLE_DEVICES=0 uv run --group train python tools/autolabel.py --frames data/frames8B --out data/labels/auto${N}B.jsonl --box-conf 0.05 > data/logs/label-auto${N}B.log 2>&1; echo "label B exit $? $(date +%H:%M:%S)" >> $L ) &
wait
mv data/frames8A/train/* data/frames8B/train/* data/frames8/train/
cat data/labels/auto${N}A.jsonl data/labels/auto${N}B.jsonl > data/labels/auto$N.jsonl
echo "label exit 0 rows $(wc -l < data/labels/auto$N.jsonl) $(date +%H:%M:%S)" >> $L
export CUDA_VISIBLE_DEVICES=1
uv run --group train python data/embed.py data/labels/auto$N.jsonl data/frames8 > data/logs/embed-auto$N.log 2>&1
echo "embed exit $? $(date +%H:%M:%S)" >> $L
uv run --group train python data/big_propose.py data/big.pt data/labels/auto$N.jsonl data/frames8 data/labels/big$N.jsonl > data/logs/propose-big$N.log 2>&1
echo "propose exit $? $(date +%H:%M:%S)" >> $L
uv run --group train python data/embed.py data/labels/big$N.jsonl data/frames8 > data/logs/embed-big$N.log 2>&1
cat data/labels/auto$N.jsonl data/labels/big$N.jsonl > data/labels/_tmp_big${N}b.jsonl
uv run --group train python data/big_propose.py data/big2.pt data/labels/_tmp_big${N}b.jsonl data/frames8 data/labels/big${N}b.jsonl > data/logs/propose-big${N}b.log 2>&1
echo "propose2 exit $? $(date +%H:%M:%S)" >> $L
sed -i 's/#big\([0-9]\)/#bigT2_\1/' data/labels/big${N}b.jsonl
uv run --group train python data/embed.py data/labels/big${N}b.jsonl data/frames8 > data/logs/embed-big${N}b.log 2>&1
echo "worker8 done $(date +%H:%M:%S)" >> $L
