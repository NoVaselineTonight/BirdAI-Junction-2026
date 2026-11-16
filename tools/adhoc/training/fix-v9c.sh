#!/bin/bash
export PATH=$HOME/.local/bin:$PATH
cd ~/birdai
pkill -f "data/run-v9b.s[h]"; pkill -f "data/evo_one.p[y]"
cp -r ~/vlm/lib/python3.12/site-packages/cloudpickle .venv/lib/python3.12/site-packages/
.venv/bin/python -c "import cloudpickle; print('cloudpickle', cloudpickle.__version__)" || exit 1
n=$(grep -n '^W960=' data/run-v9b.sh | cut -d: -f1)
{ sed -n '1,5p' data/run-v9b.sh
  echo 'L=data/logs/v9.log; V=data/dataset_v9; echo "restart from training $(date +%H:%M:%S)" >> $L'
  sed -n "$n,\$p" data/run-v9b.sh; } > data/run-v9c.sh
rm -rf data/v9runs
setsid -f bash data/run-v9c.sh > data/logs/run-v9c.out 2>&1 < /dev/null
sleep 45; tail -n 3 data/logs/v9_960_e8.log | cut -c1-200; nvidia-smi --query-gpu=utilization.gpu --format=csv,noheader | tr "\n" " "
