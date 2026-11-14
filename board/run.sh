#!/usr/bin/env bash
# Start the demo on the Arduino UNO Q and forward its page to http://localhost:8088.
# Usage: board/run.sh [--detector two_stage|student] [--fast]    |    board/run.sh --stop
# Safe to run twice: an earlier run is stopped first (SIGTERM, up to 10 s) and the forward is replaced.
set -euo pipefail
source "$(dirname "$0")/common.sh"

DETECTOR=two_stage
EXTRA=""
STOP=0
while [ $# -gt 0 ]; do
    case "$1" in
        --detector) DETECTOR=${2:?--detector needs a value}; shift 2 ;;
        --fast) EXTRA="--fast"; shift ;;
        --stop) STOP=1; shift ;;
        *) echo "usage: board/run.sh [--detector two_stage|student] [--fast] | --stop" >&2; exit 2 ;;
    esac
done

require_one_board

stop_on_board() {
    adb shell sh -eu <<REMOTE
cd $BOARD_DIR
if [ -f run.pid ]; then
    pid=\$(cat run.pid)
    # only signal the pid if it is still our run, not a process that reused the number
    if grep -qa feeder_census /proc/\$pid/cmdline 2>/dev/null; then
        kill \$pid
        for _ in \$(seq 20); do kill -0 \$pid 2>/dev/null || break; sleep 0.5; done
        if kill -0 \$pid 2>/dev/null; then echo "error: run \$pid did not stop within 10 s" >&2; exit 1; fi
    fi
    rm -f run.pid
fi
REMOTE
}

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
