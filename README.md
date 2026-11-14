# Feeder Census

Feeder Census counts the birds at a winter feeder from video and shows the counts on a local web page: birds in frame now, the highest count per hour, per day and per half-month, and one evidence photo per day. It runs on a laptop or on an Arduino UNO Q, where the board does the detection, the counting and the page, and the laptop is only the screen.

## Run on the laptop

```
uv sync
uv run python tools/fetch_models.py
uv run python -m feeder_census --videos data/videos/demo --detector two_stage
```

Then open http://localhost:8088. `--fast` plays the footage unpaced, `--no-web` prints a line per detection instead.

## Deploy and run on the Arduino UNO Q

The board must be connected over USB (`adb devices` lists exactly one).

```
board/deploy.sh --videos data/videos/demo   # prepares the videos, pushes the code and models, installs the Python packages
board/deploy.sh --videos data/videos/demo --dry-run   # builds and checks the board's free space, pushes nothing
board/run.sh                                # starts the demo on the board and forwards its page to http://localhost:8088
board/run.sh --fresh                        # the same, after deleting the board's counts first (see below)
board/run.sh --stop                         # stops it and removes the forward
```

`deploy.sh` refuses to push when the board would be left with less than 1 GB free (`FEEDER_MARGIN_KB` changes the margin), and it stops a running demo before replacing its files. It is safe to run again; it keeps `.venv/` and `data/`. The board plays a 720p, 15 fps copy of each video (`tools/prepare_video.py`), because decoding 1080p30 in software wastes its CPU.

Where things are on the board:

- `/home/arduino/feeder-census`: the code, `models/`, `videos/`, `data/` (the census database and evidence photos), `.venv/` and `run.log`. Delete this folder to remove the demo.
- `/root/.local/bin/` (`uv`, `uvx`, `env`, `env.fish`) and `/root/.cache/uv`: the package installer `deploy.sh` fetches (adb shell is root). Delete these too to remove everything; the installer is told not to edit any shell profile.

The board remembers its counts. `data/census.db` holds the census and the demo clock, so a new `board/run.sh` continues the same days, hours and counts from where the last run stopped. For a clean start of the demo, use `board/run.sh --fresh`: it stops any run, deletes `data/census.db*` and `data/evidence` on the board (nothing else) and starts over at 08:00 on 1 November.

## Measured speed

Milliseconds per frame for the pretrained two-stage detector (`python -m feeder_census.bench --detector two_stage --frames 30`), measured on 14 November 2026. Both rows use the same 60 s, 1280x720, 15 fps test clip. **That clip is a stand-in, not feeder footage: it is made of three still photos of a great tit, a blue tit and a bullfinch, panned and zoomed.** Real footage with several birds and more background will give different numbers.

| Where | median | p90 | birds per frame |
|---|---|---|---|
| Arduino UNO Q (4-core Kryo-V2) | 264 ms | 287 ms | 1.3 |
| Laptop (Intel Core Ultra 5 228V) | 28 ms | 42 ms | 1.2 |

The board keeps well inside the 1.5 s budget, so the demo detects every 2 s of footage, the default. While running, the board had about 1.2 GB of memory available.

## What the demo shows

This is footage from a feeder, standing in for our camera.

## Licences

The pretrained two-stage detector's models come from Apache-2.0 repositories (YOLOX; the Google Coral iNaturalist bird classifier). A student model trained with Ultralytics is AGPL-3.0.

`data/` and `models/` are never committed: footage belongs to the people who filmed it.
