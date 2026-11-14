# Shared by deploy.sh and run.sh (sourced, not run).
BOARD_DIR=/home/arduino/feeder-census
PORT=8088

cd "$(dirname "${BASH_SOURCE[0]}")/.."  # the repository root

require_one_board() {
    local boards
    boards=$(adb devices | awk 'NR > 1 && $2 == "device"' | wc -l)
    if [ "$boards" -ne 1 ]; then
        echo "error: expected exactly one adb device, found $boards (see: adb devices)" >&2
        exit 1
    fi
}

# Stop a running demo with SIGTERM and wait up to 10 s. Says so when it did; does nothing when none runs.
stop_on_board() {
    adb shell sh -eu <<REMOTE
cd $BOARD_DIR 2>/dev/null || exit 0
if [ -f run.pid ]; then
    pid=\$(cat run.pid)
    # only signal the pid if it is still our run, not a process that reused the number
    if grep -qa feeder_census /proc/\$pid/cmdline 2>/dev/null; then
        kill \$pid
        for _ in \$(seq 20); do kill -0 \$pid 2>/dev/null || break; sleep 0.5; done
        if kill -0 \$pid 2>/dev/null; then echo "error: run \$pid did not stop within 10 s" >&2; exit 1; fi
        echo "stopped the running demo (pid \$pid)"
    fi
    rm -f run.pid
fi
REMOTE
}
