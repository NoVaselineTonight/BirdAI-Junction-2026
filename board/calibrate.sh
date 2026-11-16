#!/usr/bin/env bash
# Start the latch calibration page on the Arduino UNO Q and forward it to http://localhost:8090.
# Usage: board/calibrate.sh
#        board/calibrate.sh --stop
# The page turns the latch servo by hand and saves its open and closed angles in data/latch_angles.json on the
# board; the demo (board/run.sh --latch router) sends them to the sketch at its next start.
# It does not start or stop the census demo. Stop the demo first (board/run.sh --stop) when it runs with
# --latch router: both would command the same servo.
# Safe to run twice: an earlier calibration page is stopped first (SIGTERM, up to 10 s) and the forward is replaced.
set -euo pipefail
source "$(dirname "$0")/common.sh"

CAL_PORT=8090  # PORT in common.sh is the demo's; the calibration page has its own

STOP=0
case "${1:-}" in
    "") ;;
    --stop) STOP=1 ;;
    *) echo "usage: board/calibrate.sh | board/calibrate.sh --stop" >&2; exit 2 ;;
esac
if [ $# -gt 1 ]; then
    echo "usage: board/calibrate.sh | board/calibrate.sh --stop" >&2; exit 2
fi

# Stop a running calibration page with SIGTERM and wait up to 10 s. Says so when it did; does nothing when none runs.
stop_calibration_on_board() {
    adb shell sh -eu <<REMOTE
cd $BOARD_DIR 2>/dev/null || exit 0
if [ -f calibrate.pid ]; then
    pid=\$(cat calibrate.pid)
    # only signal the pid if it is still our page, not a process that reused the number
    if grep -qa feeder_census.calibrate /proc/\$pid/cmdline 2>/dev/null; then
        kill \$pid
        for _ in \$(seq 20); do kill -0 \$pid 2>/dev/null || break; sleep 0.5; done
        if kill -0 \$pid 2>/dev/null; then echo "error: calibration page \$pid did not stop within 10 s" >&2; exit 1; fi
        echo "stopped the calibration page (pid \$pid)"
    fi
    rm -f calibrate.pid
fi
REMOTE
}

require_one_board

if [ "$STOP" -eq 1 ]; then
    stop_calibration_on_board
    adb forward --remove "tcp:$CAL_PORT" 2>/dev/null || true
    echo "stopped; forward removed (the census demo was not touched)"
    exit 0
fi

# the laptop port must be free, or already be our own forward
if [ -n "$(ss -ltn | grep ":$CAL_PORT " || true)" ] && [ -z "$(adb forward --list | grep "tcp:$CAL_PORT tcp:$CAL_PORT" || true)" ]; then
    echo "error: port $CAL_PORT on this computer is in use (see: ss -ltnp | grep $CAL_PORT)" >&2
    exit 1
fi

if [ -n "$(adb shell "[ -f $BOARD_DIR/run.pid ] && grep -qa feeder_census /proc/\$(cat $BOARD_DIR/run.pid)/cmdline 2>/dev/null && echo yes" | tr -d '\r' || true)" ]; then
    echo "note: the census demo is running on the board. If it runs with --latch router it commands the servo too; stop it with board/run.sh --stop"
fi

stop_calibration_on_board
adb shell "cd $BOARD_DIR || exit 1; nohup .venv/bin/python -m feeder_census.calibrate --port $CAL_PORT \
    --angles-file data/latch_angles.json > calibrate.log 2>&1 < /dev/null & echo \$! > calibrate.pid"
adb forward "tcp:$CAL_PORT" "tcp:$CAL_PORT" > /dev/null

for _ in $(seq 20); do
    if curl -sf "localhost:$CAL_PORT/state" > /dev/null; then
        echo "running: http://localhost:$CAL_PORT (stop with: board/calibrate.sh --stop)"
        exit 0
    fi
    sleep 0.5
done
echo "error: the calibration page did not come up; board log:" >&2
adb shell "tail -n 20 $BOARD_DIR/calibrate.log" >&2
exit 1
