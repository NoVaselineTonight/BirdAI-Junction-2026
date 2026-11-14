#!/usr/bin/env bash
# Start the demo on the Arduino UNO Q and forward its page to http://localhost:8088.
# Usage: board/run.sh [--detector two_stage|student] [--fast] [--fresh]    |    board/run.sh --stop
# --fresh deletes the board's data/census.db and data/evidence first, so the counts and the clock start over.
# Safe to run twice: an earlier run is stopped first (SIGTERM, up to 10 s) and the forward is replaced.
set -euo pipefail
source "$(dirname "$0")/common.sh"

DETECTOR=two_stage
EXTRA=""
STOP=0
FRESH=0
while [ $# -gt 0 ]; do
    case "$1" in
        --detector) DETECTOR=${2:?--detector needs a value}; shift 2 ;;
        --fast) EXTRA="--fast"; shift ;;
        --fresh) FRESH=1; shift ;;
        --stop) STOP=1; shift ;;
        *) echo "usage: board/run.sh [--detector two_stage|student] [--fast] [--fresh] | --stop" >&2; exit 2 ;;
    esac
done

require_one_board

if [ "$STOP" -eq 1 ]; then
    stop_on_board
    adb forward --remove "tcp:$PORT" 2>/dev/null || true
    echo "stopped; forward removed"
    exit 0
fi

# the laptop port must be free, or already be our own forward
if [ -n "$(ss -ltn | grep ":$PORT " || true)" ] && [ -z "$(adb forward --list | grep "tcp:$PORT tcp:$PORT" || true)" ]; then
    echo "error: port $PORT on this computer is in use (see: ss -ltnp | grep $PORT)" >&2
    exit 1
fi

stop_on_board
if [ "$FRESH" -eq 1 ]; then
    adb shell "cd $BOARD_DIR/data && rm -rf census.db* evidence"
    echo "fresh start: census.db and evidence deleted on the board"
fi
adb shell "cd $BOARD_DIR; nohup .venv/bin/python -m feeder_census --videos videos --detector $DETECTOR \
    --db data/census.db --port $PORT $EXTRA > run.log 2>&1 < /dev/null & echo \$! > run.pid"
adb forward "tcp:$PORT" "tcp:$PORT" > /dev/null

for _ in $(seq 60); do
    if curl -sf "localhost:$PORT/api/live" > /dev/null; then
        echo "running: http://localhost:$PORT (stop with: board/run.sh --stop)"
        exit 0
    fi
    sleep 0.5
done
echo "error: the page did not come up; board log:" >&2
adb shell "tail -n 20 $BOARD_DIR/run.log" >&2
exit 1
