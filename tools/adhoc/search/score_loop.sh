#!/bin/bash
# rented machine: score every new checkpoint of a size-test run on the never-trained days (same measure as the evolution runs)
NAME=$1; IMGSZ=$2
cd ~/birdai; D=data/sweep/$NAME; last=""; mkdir -p $D
while true; do
  f=$D/t/weights/last.pt
  if [ -f $f ]; then s=$(stat -c %Y $f)
    if [ "$s" != "$last" ]; then last=$s; cp $f $D/snap.pt
      ep=$(.venv/bin/python -c "import torch; print(torch.load('$D/snap.pt', map_location='cpu', weights_only=False).get('epoch'))" 2>/dev/null | tail -1)
      r=$(PYTHONPATH=.:tools .venv/bin/python data/evo_one.py --score-only --parent $D/snap.pt --out $D/score --imgsz $IMGSZ --fit-dataset data/dataset_fit --fit-split test --val-every 2 2>&1 | grep RESULT)
      echo "$(date +%H:%M:%S) epoch $ep $r" >> $D/scores.log; cp $D/snap.pt $D/scored.pt
    fi
    [ -f $D/done ] && [ "$(stat -c %Y $f)" = "$last" ] && { echo "$(date +%H:%M:%S) finished" >> $D/scores.log; break; }
  fi
  sleep 20
done
