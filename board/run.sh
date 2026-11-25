#!/usr/bin/env bash
# Start the demo on the Arduino UNO Q and forward its page to http://localhost:8088.
# Usage: board/run.sh [--detector auto|two_stage|student] [--latch off|sim|router] [--photo-every-s N] [--footage-note TEXT]
#                     [--pest-threshold X] [--latch-close-frames N] [--latch-open-frames N] [--fast] [--fresh] [--dry-run]
#        board/run.sh --stop
# --detector auto (the default) lets the program on the board pick: the kind in the board's models/model_card.json,
# or two_stage when it has none. deploy.sh keeps that card in step with the model it ships.
# --photo-every-s N (seconds of footage, e.g. 5 or 2.5) shows one analysed photo every N s, held until the next,
# as the board's camera would take them, instead of video.
# --footage-note TEXT is the sentence the page shows under the video's name, e.g. to say the reel is an edited cut.
#   Only letters, digits, space and . , : - are allowed (it is passed to a shell command on the board).
# --latch (default off) closes the feeder latch when a squirrel or rat is seen: sim only shows it on the page,
# router moves the servo through board/latch/latch.ino (upload that sketch to the board first).
# --pest-threshold X (0 to 1), --latch-close-frames N and --latch-open-frames N (whole numbers from 1) set the latch
#   rule; they are passed to the program as they are (see "Latch" in the README for what they mean).
# --dry-run only reads from the board: it says which detector would run and what would be deleted.
# --fresh deletes the board's data/census.db and data/evidence first, so the counts and the clock start over.
# Safe to run twice: an earlier run is stopped first (SIGTERM, up to 10 s) and the forward is replaced.
set -euo pipefail
source "$(dirname "$0")/common.sh"

DETECTOR=auto
LATCH=off
EXTRA=""
FAST=""
PHOTO=""
PEST=""
CLOSE=""
OPEN=""
NOTE=""
NOTE_SET=0
STOP=0
FRESH=0
DRY_RUN=0
while [ $# -gt 0 ]; do
    case "$1" in
        --detector) DETECTOR=${2:?--detector needs a value}; shift 2 ;;
        --latch) LATCH=${2:?--latch needs a value}; shift 2 ;;
        --photo-every-s) PHOTO=${2:?--photo-every-s needs a value}; shift 2 ;;
        --pest-threshold) PEST=${2:?--pest-threshold needs a value}; shift 2 ;;
        --latch-close-frames) CLOSE=${2:?--latch-close-frames needs a value}; shift 2 ;;
        --latch-open-frames) OPEN=${2:?--latch-open-frames needs a value}; shift 2 ;;
        --footage-note) NOTE=${2?--footage-note needs a value}; NOTE_SET=1; shift 2 ;;
        --fast) FAST="--fast"; shift ;;
        --fresh) FRESH=1; shift ;;
        --stop) STOP=1; shift ;;
        --dry-run) DRY_RUN=1; shift ;;
        *) echo "usage: board/run.sh [--detector auto|two_stage|student] [--latch off|sim|router] [--photo-every-s N] [--footage-note TEXT] [--pest-threshold X] [--latch-close-frames N] [--latch-open-frames N] [--fast] [--fresh] [--dry-run] | --stop" >&2; exit 2 ;;
    esac
done
case "$DETECTOR" in
    auto|two_stage|student) ;;
    *) echo "error: unknown detector '$DETECTOR' (auto, two_stage or student)" >&2; exit 2 ;;
esac
case "$LATCH" in
    off|sim|router) ;;
    *) echo "error: unknown latch mode '$LATCH' (off, sim or router)" >&2; exit 2 ;;
esac

if [ -n "$PHOTO" ]; then
    if ! [[ "$PHOTO" =~ ^([0-9]+\.?[0-9]*|\.[0-9]+)$ ]] || [[ "$PHOTO" =~ ^0*\.?0*$ ]]; then
        echo "error: --photo-every-s needs a number of seconds above 0, got '$PHOTO'" >&2; exit 2
    fi
    EXTRA="--photo-every-s $PHOTO"
fi
if [ -n "$PEST" ]; then
    if ! [[ "$PEST" =~ ^(0(\.[0-9]*)?|1(\.0*)?|\.[0-9]+)$ ]]; then
        echo "error: --pest-threshold needs a number from 0 to 1, got '$PEST'" >&2; exit 2
    fi
    EXTRA="$EXTRA --pest-threshold $PEST"
fi
for pair in "--latch-close-frames:$CLOSE" "--latch-open-frames:$OPEN"; do
    if [ -n "${pair#*:}" ]; then
        if ! is_uint "${pair#*:}" || [ "$((10#${pair#*:}))" -lt 1 ]; then
            echo "error: ${pair%%:*} needs a whole number from 1, got '${pair#*:}'" >&2; exit 2
        fi
        EXTRA="$EXTRA ${pair%%:*} $((10#${pair#*:}))"
    fi
done
if [ "$NOTE_SET" -eq 1 ]; then
    if ! [[ "$NOTE" =~ ^[A-Za-z0-9\ .,:-]+$ ]]; then
        echo "error: --footage-note must be non-empty and use only letters, digits, space and . , : - characters" >&2; exit 2
    fi
    EXTRA="$EXTRA --footage-note '$NOTE'"
fi
EXTRA="$EXTRA $FAST"

require_one_board

if [ "$STOP" -eq 1 ]; then
    stop_on_board
    adb forward --remove "tcp:$PORT" 2>/dev/null || true
    echo "stopped; forward removed"
    exit 0
fi

if [ "$DRY_RUN" -eq 1 ]; then
    if [ "$DETECTOR" = auto ]; then
        BOARD_CARD=$(mktemp)
        trap 'rm -f "$BOARD_CARD"' EXIT
        adb shell "cat $BOARD_DIR/models/model_card.json 2>/dev/null" | tr -d '\r' > "$BOARD_CARD" || true
        if [ -s "$BOARD_CARD" ]; then
            KIND=$(card_kind "$BOARD_CARD") || { echo "(that file is $BOARD_DIR/models/model_card.json on the board)" >&2; exit 2; }
            echo "detector: $KIND (model card on the board)"
        else
            echo "detector: two_stage (no model card on the board)"
        fi
    else
        echo "detector: $DETECTOR (asked for)"
    fi
    echo "would stop a running demo on the board"
    if [ "$FRESH" -eq 1 ]; then echo "would delete census.db* and evidence in $BOARD_DIR/data (when it exists)"; fi
    echo "would start: python -m feeder_census --videos videos --detector $DETECTOR --latch $LATCH --db data/census.db --port $PORT $EXTRA"
    echo "dry run: nothing stopped, deleted or started"
    exit 0
fi

# the laptop port must be free, or already be our own forward
if [ -n "$(ss -ltn | grep ":$PORT " || true)" ] && [ -z "$(adb forward --list | grep "tcp:$PORT tcp:$PORT" || true)" ]; then
    echo "error: port $PORT on this computer is in use (see: ss -ltnp | grep $PORT)" >&2
    exit 1
fi

stop_on_board
if [ "$FRESH" -eq 1 ]; then
    if adb shell "[ -d $BOARD_DIR/data ]"; then
        adb shell "cd $BOARD_DIR/data && rm -rf census.db* evidence"
        echo "fresh start: census.db and evidence deleted on the board"
    else
        echo "fresh start: the board has no data/ yet, nothing to delete"
    fi
fi
adb shell "cd $BOARD_DIR || exit 1; nohup .venv/bin/python -m feeder_census --videos videos --detector $DETECTOR \
    --latch $LATCH --db data/census.db --port $PORT $EXTRA > run.log 2>&1 < /dev/null & echo \$! > run.pid"
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
