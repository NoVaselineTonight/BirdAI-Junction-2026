#!/usr/bin/env bash
# Build build/board/ and push it to the Arduino UNO Q, then set up its Python environment.
# Usage: board/deploy.sh [--detector two_stage|student] [--videos DIR] [--dry-run]
# Safe to run twice: code, videos and models are replaced, .venv and data/ are kept. A running demo is stopped first.
# --dry-run builds build/board/ and checks the board's free space, then stops (nothing is pushed or installed).
# The space check keeps FEEDER_MARGIN_KB (default 1000000, about 1 GB) free after the push.
set -euo pipefail
source "$(dirname "$0")/common.sh"

DETECTOR=two_stage
VIDEOS=data/videos/demo
DRY_RUN=0
while [ $# -gt 0 ]; do
    case "$1" in
        --detector) DETECTOR=${2:?--detector needs a value}; shift 2 ;;
        --videos) VIDEOS=${2:?--videos needs a directory}; shift 2 ;;
        --dry-run) DRY_RUN=1; shift ;;
        *) echo "usage: board/deploy.sh [--detector two_stage|student] [--videos DIR] [--dry-run]" >&2; exit 2 ;;
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

echo "== checking space on the board"
# The push replaces videos/, so the old clips' space counts as free.
BUILD_KB=$(du -sk build/board | cut -f1)
FREE_KB=$(adb shell "df -k /home/arduino | awk 'NR == 2 {print \$4}'" | tr -d '\r')
OLD_VIDEOS_KB=$(adb shell "du -sk $BOARD_DIR/videos 2>/dev/null | cut -f1" | tr -d '\r')
OLD_VIDEOS_KB=${OLD_VIDEOS_KB:-0}
case "$FREE_KB$OLD_VIDEOS_KB" in
    ''|*[!0-9]*) echo "error: could not read the board's disk space (got '$FREE_KB' and '$OLD_VIDEOS_KB')" >&2; exit 1 ;;
esac
MARGIN_KB=${FEEDER_MARGIN_KB:-1000000}
REQUIRED_KB=$((BUILD_KB + MARGIN_KB - OLD_VIDEOS_KB))
echo "build/board: $BUILD_KB kB; board free: $FREE_KB kB; current videos/ on board: $OLD_VIDEOS_KB kB; margin: $MARGIN_KB kB; required free: $REQUIRED_KB kB"
if [ "$FREE_KB" -lt "$REQUIRED_KB" ]; then
    echo "REFUSED: not enough space on /home/arduino (free $FREE_KB kB, need $REQUIRED_KB kB); nothing was pushed" >&2
    exit 1
fi
echo "space ok"
if [ "$DRY_RUN" -eq 1 ]; then
    echo "dry run: nothing pushed or installed"
    exit 0
fi

echo "== pushing to $BOARD_DIR"
stop_on_board  # the running demo would lose its clips
adb shell "mkdir -p $BOARD_DIR && cd $BOARD_DIR && rm -rf feeder_census videos"
adb push build/board/. "$BOARD_DIR/"

echo "== installing on the board"
adb shell sh -eu <<REMOTE
cd $BOARD_DIR
export TMPDIR=/tmp  # adb shell points it at a folder this board does not have
export UV_NO_MODIFY_PATH=1  # the uv installer must not edit root's shell profile
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
