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
