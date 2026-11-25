#!/usr/bin/env bash
# On birdai-fast: install tools, sync the Python environment, wait for the dataset from main, train teacher 2.
export DEBIAN_FRONTEND=noninteractive
export PATH=$HOME/.local/bin:$PATH
mkdir -p ~/birdai/data/logs
L=~/birdai/data/logs/fast.log
echo "fast start $(date +%H:%M:%S)" > $L
command -v uv >/dev/null || (curl -LsSf https://astral.sh/uv/install.sh | UV_NO_MODIFY_PATH=1 sh) >> $L 2>&1
cd ~/birdai || exit 1
uv sync --group train >> $L 2>&1
echo "env ready exit $? $(date +%H:%M:%S)" >> $L
uv run --group train python -c "import torch; print('cuda', torch.cuda.is_available(), torch.cuda.device_count())" >> $L 2>&1
until [ -f data/dataset_v2a.READY ]; do sleep 5; done
echo "dataset here $(date +%H:%M:%S)" >> $L
uv run --group train python data/big_train2.py > data/logs/big2-train.log 2>&1
echo "big2 exit $? $(date +%H:%M:%S)" >> $L
ls -la runs_big/t2/weights >> $L 2>&1
