# Feeder Census

Feeder Census counts the birds at a winter feeder from video and shows the counts on a local web page: birds in frame now, the highest count per hour, per day and per half-month, and one evidence photo per day. It runs on a laptop or on an Arduino UNO Q, where the board does the detection, the counting and the page, and the laptop is only the screen.

## Run on the laptop

```
uv sync
uv run python tools/fetch_models.py
uv run python -m feeder_census --videos data/videos/demo
```

Then open http://localhost:8088. `--fast` plays the footage unpaced, `--no-web` prints a line per detection instead.

`--detector` is `auto` by default: the program runs the detector named in `models/model_card.json` (see below), or the pretrained `two_stage` detector when there is no card. `--detector two_stage|student` forces one; the page shows the model card only when the card was measured for the detector that runs. The first output line says which detector runs, why (`model card`, `no model card`, `asked for`) and the counting threshold in force; a `count_threshold` in the card replaces the detector's own.

## Deploy and run on the Arduino UNO Q

The board must be connected over USB (`adb devices` lists exactly one).

```
board/deploy.sh --videos data/videos/demo   # prepares the videos, pushes the code and the chosen model, installs the Python packages
board/deploy.sh --detector student ...      # auto (default) | two_stage | student; auto follows models/model_card.json
board/deploy.sh --videos data/videos/demo --dry-run   # says which detector and files, checks the board's free space, pushes nothing
board/run.sh                                # starts the demo on the board (--detector auto|two_stage|student) and forwards its page to http://localhost:8088
board/run.sh --dry-run                      # says which detector would start, changes nothing
board/run.sh --fresh                        # the same, after deleting the board's counts first (see below)
board/run.sh --stop                         # stops it and removes the forward
```

`deploy.sh` copies only the files of the detector it ships. It copies `models/model_card.json` only when the card names that detector, and otherwise removes a stale card and stale student files from the board, so the board never shows a card for a model it is not running. It refuses to push when the board would be left with less than 1 GB free (`FEEDER_MARGIN_KB` changes the margin), and it stops a running demo before replacing its files. It is safe to run again; it keeps `.venv/` and `data/`. The board plays a 720p, 15 fps copy of each video (`tools/prepare_video.py`), because decoding 1080p30 in software wastes its CPU.

Where things are on the board:

- `/home/arduino/feeder-census`: the code, `models/`, `videos/`, `data/` (the census database and evidence photos), `.venv/` and `run.log`. Delete this folder to remove the demo.
- `/root/.local/bin/` (`uv`, `uvx`, `env`, `env.fish`) and `/root/.cache/uv`: the package installer `deploy.sh` fetches (adb shell is root). Delete these too to remove everything; the installer is told not to edit any shell profile.

The board remembers its counts. `data/census.db` holds the census and the demo clock, so a new `board/run.sh` continues the same days, hours and counts from where the last run stopped. For a clean start of the demo, use `board/run.sh --fresh`: it stops any run, deletes `data/census.db*` and `data/evidence` on the board (nothing else) and starts over at 08:00 on 1 November. On a board that has no `data/` yet (first run after the first deploy), `--fresh` does nothing and says so.

## Latch

Two hobby servos close a latch over the feeder while a squirrel or a rat is at it. The program closes the latch after the animal is seen in 2 detections in a row and opens it again after 5 detections in a row without one. The animals (`[[pest]]` in `species.toml`) are never census birds: they are not counted, not in the tables, the CSV, the visits or the evidence photos. They are drawn on the feed by name. Seeing them needs a model trained on them; that is a separate step.

The servos are DFRobot SER0006 (9 g, 180° position servos, 4.8–6 V). The UNO Q's microcontroller drives them with `board/latch/latch.ino`. Wiring, in words:

- Servo 1's signal wire to D9, servo 2's signal wire to D10.
- Servo power from a separate 5 V supply, not from the board's 5 V pin.
- Join that supply's ground to a GND pin on the board.
- Never put 5 V on D3 or A0–A5.

The open and closed angles are constants at the top of the sketch (10 and 100; the second servo is mounted mirrored). The sketch opens the latch by itself 30 seconds after the last close command, so the feeder does not stay shut when the program on the Linux side stops. The program repeats the close command at every detection while the latch should stay closed.

`--latch` (on `python -m feeder_census` and `board/run.sh`) picks the mode:

- `off` (default): no latch; the page shows nothing about it.
- `sim`: no hardware. The page shows what the latch would do and says `Latch not connected: showing what it would do.`
- `router`: the program calls `set_latch` on the microcontroller through the board's `arduino-router` service (`/var/run/arduino-router.sock`). When the call fails the page says `Latch not answering:` and why; the counting carries on.

Bring-up: upload the sketch from the laptop (it needs the `Servo` library, 1.3.0 or later: `arduino-cli lib install Servo`), then move the latch by hand from the board:

```
arduino-cli compile -b arduino:zephyr:unoq board/latch
arduino-cli upload -b arduino:zephyr:unoq -p /dev/ttyACM0 board/latch
adb shell "cd /home/arduino/feeder-census && .venv/bin/python -m feeder_census.latch cycle"   # close, wait 2 s, open; also: close | open
board/run.sh --latch router
```

The link between the program and the sketch follows Arduino's documentation for the router bridge; it has not yet been tried on our board.

## Measured speed

Milliseconds per frame for the pretrained two-stage detector (`python -m feeder_census.bench --detector two_stage --frames 30`), measured on 14 November 2026. Both rows use the same 60 s, 1280x720, 15 fps test clip. **That clip is a stand-in, not feeder footage: it is made of three still photos of a great tit, a blue tit and a bullfinch, panned and zoomed.** Real footage with several birds and more background will give different numbers.

| Where | median | p90 | birds per frame |
|---|---|---|---|
| Arduino UNO Q (4-core Kryo-V2) | 264 ms | 287 ms | 1.3 |
| Laptop (Intel Core Ultra 5 228V) | 28 ms | 42 ms | 1.2 |

The board keeps well inside the 1.5 s budget, so the demo detects every 2 s of footage, the default. While running, the board had about 1.2 GB of memory available.

## How the shipped model is chosen

Two detectors exist: the pretrained two-stage detector and a student model trained on our footage. `tools/evaluate.py` measures them on held-out footage and decides which one ships:

```
uv run python tools/evaluate.py --dataset data/dataset --candidates two_stage student:640 student:416 \
    --board-ms two_stage=<ms>,640=<ms>,416=<ms> --promote
```

- A candidate is eligible when its median time on the board is at most 1500 ms (`--board-ms` takes the medians from `python -m feeder_census.bench` on the board).
- A student qualifies when at least three species reach precision of at least 0.90 and recall of at least 0.50 on the held-out footage.
- The qualifying student with the highest share of exactly-right frames ships, but only if that share is at least the pretrained detector's. Otherwise the pretrained detector ships, and the card says why.
- The numbers land in `models/eval.json` (every run) and in `models/model_card.json` (only with `--promote`), which the program and `board/deploy.sh` follow.

## What the accuracy numbers mean

- They are measured on footage from a feeder the model never trained on.
- The counting threshold is chosen on a held-back part of the training footage, never on the held-out footage.
- The held-out frames are picked for having birds, plus a share of empty frames. They are harder than a random minute at a feeder, so the share of frames counted exactly right would be higher on raw footage.
- The truth labels come from teacher models plus a person's check. The pretrained two-stage detector shares one of those teachers, which favours it.
- The qualifying rule has no minimum number of boxes per species, so a species with very few held-out boxes can pass on luck. Read the box counts (`val_boxes`) next to every precision and recall.
- Nothing here claims the model names species better than a skilled volunteer.

Accuracy results (placeholder: nothing has been measured yet; after `--promote`, paste the numbers from `models/eval.json` here and do not round them up):

| Detector | board median | frames counted exactly right | species passing (precision >= 0.90, recall >= 0.50) | held-out frames |
|---|---|---|---|---|
| two_stage | _paste_ | _paste_ | _paste_ | _paste_ |
| student:640 | _paste_ | _paste_ | _paste_ | _paste_ |
| student:416 | _paste_ | _paste_ | _paste_ | _paste_ |

## What the demo shows

This is footage from a feeder, standing in for our camera. The demo clip may be an edited "busy parts" cut of a longer recording (made with `tools/mine_frames.py --highlights`). Say so aloud in the demo.

## Licences

The pretrained two-stage detector's models come from Apache-2.0 repositories (YOLOX; the Google Coral iNaturalist bird classifier). A student model trained with Ultralytics is AGPL-3.0.

`data/` and `models/` are never committed: footage belongs to the people who filmed it.
