#!/usr/bin/env bash
# Runs the training-side work on the rented GPU machine.
#
#   VERDA_HOST=root@203.0.113.7 tools/remote.sh push
#   VERDA_HOST=... tools/remote.sh run "<command>"    # runs in ~/birdai under `uv run --group train`
#   VERDA_HOST=... tools/remote.sh pull
set -euo pipefail

usage() {
  echo "usage: VERDA_HOST=user@host tools/remote.sh push | run \"<command>\" | pull" >&2
  exit 2
}

if [ -z "${VERDA_HOST:-}" ]; then
  echo "VERDA_HOST is not set. Set it to the GPU machine, for example: export VERDA_HOST=root@203.0.113.7" >&2
  exit 1
fi
[ $# -ge 1 ] || usage

cd "$(dirname "$0")/.."
REMOTE_DIR='~/birdai'   # expanded by the remote shell
SSH=(ssh -o ServerAliveInterval=30)
RSYNC=(rsync -az --info=stats1 -e "ssh -o ServerAliveInterval=30")

case "$1" in
  push)
    "${SSH[@]}" "$VERDA_HOST" "mkdir -p $REMOTE_DIR/data/videos $REMOTE_DIR/models/pretrained"
    "${RSYNC[@]}" --exclude .git --exclude .venv --exclude .superpowers --exclude /data/ \
      --exclude /models/ --exclude /build/ --exclude __pycache__ ./ "$VERDA_HOST:$REMOTE_DIR/"
    for dir in data/videos models/pretrained; do
      if [ -d "$dir" ]; then
        "${RSYNC[@]}" "$dir/" "$VERDA_HOST:$REMOTE_DIR/$dir/"
      else
        echo "note: $dir does not exist locally, skipped" >&2
      fi
    done
    ;;
  run)
    [ $# -eq 2 ] || usage
    # The whole command (chains with && included) must run inside `uv run`, so it goes to
    # `bash -c` as ONE argument. printf %q quotes it for the remote shell; uv is installed on first use.
    quoted=$(printf '%q' "$2")
    "${SSH[@]}" "$VERDA_HOST" "export PATH=\"\$HOME/.local/bin:\$PATH\"; \
      command -v uv >/dev/null || curl -LsSf https://astral.sh/uv/install.sh | sh; \
      cd $REMOTE_DIR && uv run --group train bash -c $quoted"
    ;;
  pull)
    mkdir -p data/labels data/review data/dataset models/student
    # --ignore-missing-args: a step that has not run yet has not produced its folder
    fetch() { "${RSYNC[@]}" --ignore-missing-args "${@:3}" "$VERDA_HOST:$REMOTE_DIR/$1" "$2"; }
    fetch data/labels/ data/labels/
    # corrections.csv is edited here by hand; a later pull must not overwrite it with the remote's copy
    fetch data/review/ data/review/ --exclude corrections.csv
    [ -e data/review/corrections.csv ] || fetch data/review/corrections.csv data/review/
    fetch data/dataset/classes.json data/dataset/
    fetch models/student/ models/student/
    ;;
  *)
    usage
    ;;
esac
