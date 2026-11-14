#!/usr/bin/env bash
# Build build/board/ and push it to the Arduino UNO Q, then set up its Python environment.
# Usage: board/deploy.sh [--detector two_stage|student] [--videos DIR]
# Safe to run twice: code, videos and models are replaced, .venv and data/ are kept.
set -euo pipefail
source "$(dirname "$0")/common.sh"

DETECTOR=two_stage
VIDEOS=data/videos/demo
while [ $# -gt 0 ]; do
    case "$1" in
        --detector) DETECTOR=${2:?--detector needs a value}; shift 2 ;;
        --videos) VIDEOS=${2:?--videos needs a directory}; shift 2 ;;
        *) echo "usage: board/deploy.sh [--detector two_stage|student] [--videos DIR]" >&2; exit 2 ;;
    esac
done

require_one_board

# The model files each detector needs (see feeder_census/detectors/__init__.py).
case "$DETECTOR" in
    two_stage) MODELS=(models/pretrained/yolox_nano.onnx models/pretrained/inat_bird.tflite models/pretrained/inat_bird_labels.txt) ;;
    student) MODELS=(models/student/feeder.onnx models/student/feeder.json) ;;
    *) echo "error: unknown detector '$DETECTOR' (two_stage or student)" >&2; exit 2 ;;
esac
for model in "${MODELS[@]}"; do
    [ -f "$model" ] || { echo "error: missing $model (two_stage: uv run python tools/fetch_models.py)" >&2; exit 1; }
done

shopt -s nullglob nocaseglob
CLIPS=("$VIDEOS"/*.mp4 "$VIDEOS"/*.mov "$VIDEOS"/*.avi "$VIDEOS"/*.mkv)
shopt -u nullglob nocaseglob
if [ ${#CLIPS[@]} -eq 0 ]; then
    echo "error: no video (mp4, mov, avi, mkv) in '$VIDEOS'; pass --videos DIR" >&2
    exit 1
fi

echo "== building build/board/"
rm -rf build/board
mkdir -p build/board/videos
for clip in "${CLIPS[@]}"; do
    uv run python tools/prepare_video.py "$clip" "build/board/videos/$(basename "${clip%.*}").mp4"
done
cp -r feeder_census species.toml build/board/
find build/board -name __pycache__ -prune -exec rm -rf {} +
for model in "${MODELS[@]}"; do
    mkdir -p "build/board/$(dirname "$model")"
    cp "$model" "build/board/$model"
done

echo "== pushing to $BOARD_DIR"
adb shell "mkdir -p $BOARD_DIR && cd $BOARD_DIR && rm -rf feeder_census videos"
adb push build/board/. "$BOARD_DIR/"

echo "== installing on the board"
adb shell sh -eu <<REMOTE
cd $BOARD_DIR
export TMPDIR=/tmp  # adb shell points it at a folder this board does not have
export UV_LINK_MODE=copy  # the uv cache and /home/arduino are on different disks
UV=\$HOME/.local/bin/uv
if [ ! -x "\$UV" ]; then curl -LsSf https://astral.sh/uv/install.sh | sh; fi
if [ ! -d .venv ]; then
    free_kb=\$(df -k /home/arduino | awk 'NR == 2 {print \$4}')
    [ "\$free_kb" -ge 1000000 ] || { echo "error: less than 1 GB free on /home/arduino" >&2; exit 1; }
    "\$UV" venv --python /usr/bin/python3 .venv
fi
"\$UV" pip install --python .venv/bin/python numpy opencv-python-headless onnxruntime ai-edge-litert fastapi uvicorn
.venv/bin/python -c "import cv2, onnxruntime, ai_edge_litert, fastapi, uvicorn; print('board python ok:', cv2.__version__, onnxruntime.__version__)"
mkdir -p data
REMOTE
echo "== deployed ($DETECTOR). Run it with: board/run.sh --detector $DETECTOR"
