# Feeder Census

Feeder Census counts the birds at a winter feeder from video and shows the counts on a local web page: birds in frame now, the highest count per hour, per day and per half-month, and one evidence photo per day. It runs on a laptop or on an Arduino UNO Q, where the board does the detection, the counting and the page, and the laptop is only the screen.

## Run on the laptop

```
uv sync
uv run python tools/fetch_models.py
uv run python -m feeder_census --videos data/videos/demo
```

Then open http://localhost:8088. `--fast` plays the footage unpaced, `--no-web` prints a line per detection instead.

`--photo-every-s SECONDS` makes the demo behave like the board's camera: it analyses one photo every SECONDS of footage and the page shows only those photos, each drawn with its own boxes and held until the next one, instead of video. For example `uv run python -m feeder_census --videos data/videos/demo --photo-every-s 5`. It replaces `--detect-every-s`, and giving both is an error. A bird is counted when it is seen in two photos in a row, so with 10 s between photos a bird must stay at the feeder for about 10 s to be counted. `board/run.sh --photo-every-s 5` passes it on to the board.

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

One hobby servo closes a latch over the feeder while a squirrel or a rat is at it. The program closes the latch after the animal is seen in 2 detections in a row and opens it again after 5 detections in a row without one. The animals (`[[pest]]` in `species.toml`) are never census birds: they are not counted, not in the tables, the CSV, the visits or the evidence photos. They are drawn on the feed by name. Seeing them needs a model trained on them. The shipped student is trained on red squirrels, so it can close the latch for a squirrel. It has no rat class (its classes are the 12 bird species, `red_squirrel` and `unidentified`), so with this model a rat does not close the latch. `species.toml` already lists the brown rat as a pest, so a later model can add it.

The servo is a DFRobot SER0006 (9 g, 180° position servo, 4.8–6 V). It turns one axis, and both pull wires of the latch are fixed to that axis. The UNO Q's microcontroller drives it with `board/latch/latch.ino`. Wiring, in words:

- The servo's signal wire to D9.
- Recommended: servo power from a separate 5 V supply, with that supply's ground joined to a GND pin on the board.
- Fallback we use (no separate supply): servo power from the board's 5V and GND pins. Keep the flap light; a jammed servo can reset the board.
- Never put 5 V on D3 or A0–A5.

The open and closed angles are two constants at the top of the sketch (10 open, 100 closed). The sketch opens the latch by itself 30 seconds after the last close command, so the feeder does not stay shut when the program on the Linux side stops. The program repeats the close command at every detection while the latch should stay closed.

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

Milliseconds per frame on the Arduino UNO Q (4-core Kryo-V2), measured on 14 November 2026 with `python -m feeder_census.bench --frames 30`. The clip is **real feeder footage**: 120 s of the held-out day (12 November 2026), 1280x720, prepared with `tools/prepare_video.py`. The budget is 1500 ms per frame.

| Detector | median | p90 | inside the 1500 ms budget |
|---|---|---|---|
| two_stage (pretrained) | 169.8 ms | 171.8 ms | yes |
| student 640 px | 506.6 ms | 520.4 ms | yes |
| student 960 px (shipped) | 1108.5 ms | 1127.9 ms | yes |

Both student sizes stay inside the 1.5 s budget. The demo analyses one photo every 5 s (photo mode, above), which leaves time to spare even for the 960 px student.

Earlier stand-in measurement, for the pretrained two-stage detector only (`python -m feeder_census.bench --detector two_stage --frames 30`). Both rows use the same 60 s, 1280x720, 15 fps test clip. **That clip is a stand-in, not feeder footage: it is made of three still photos of a great tit, a blue tit and a bullfinch, panned and zoomed.**

| Where | median | p90 | birds per frame |
|---|---|---|---|
| Arduino UNO Q (4-core Kryo-V2) | 264 ms | 287 ms | 1.3 |
| Laptop (Intel Core Ultra 5 228V) | 28 ms | 42 ms | 1.2 |

While that stand-in clip ran, the board had about 1.2 GB of memory available.

## How the shipped model is chosen

Two kinds of detector exist: the pretrained two-stage detector and a student model trained on our footage, in two sizes (960 px and 640 px). `tools/evaluate.py` measures them on held-out footage and decides which one ships:

```
uv run python tools/evaluate.py --dataset data/dataset --candidates two_stage student:960 student:640 \
    --board-ms two_stage=<ms>,960=<ms>,640=<ms> --promote
```

- **The cut-off.** A detector gives each box a confidence. A box counts only above a cut-off. For a student, the cut-off is picked on validation footage (the last 15 % of each training video): the lowest value from 0.50 to 0.90 (in steps of 0.05) where at least 9 in 10 of the birds it named were named right. All species are judged together, and a species with fewer than 20 validation boxes is left out, so one rare species cannot hold the cut-off up. If no value reaches 9 in 10, the cut-off is 0.90, and the card says it is a fallback. The two-stage detector keeps its fixed cut-off and never sees validation footage.
- **Too little to pick by.** If no species has at least 20 validation boxes, nothing was measured to pick by, so the student keeps the cut-off written in its own card (it is not set to 0.90), and the card says so (`default: too few validation boxes to pick`).
- **The board-time bar.** A student is eligible only when its median time on the board is at most 1500 ms (`--board-ms` takes the medians from `python -m feeder_census.bench` on the board). A candidate with no board timing is treated as eligible, except that `--promote` refuses to run until every candidate has a timing.
- **Qualifying.** A student qualifies when at least three species reach precision of at least 0.90 and recall of at least 0.50 on the held-out footage. Precision means: of the birds it named, the share named right. Recall means: of the birds in the truth labels, the share it found. A rate that could not be computed does not count.
- **Who ships.** The qualifying student that counts exactly right in the most frames ships, but only if that share is at least the pretrained detector's. When no eligible student qualifies, the eligible student that counts best still ships if it beats the pretrained detector, and the card says `qualified: false`; the page then says "Below our accuracy bar; it ships because it counts better than the alternative." That mark applies to a shipped student only: when the pretrained detector ships, the page does not say it. Otherwise the pretrained detector ships, and the card says why.
- The numbers land in `models/eval.json` (every run) and in `models/model_card.json` (only with `--promote`), which the program and `board/deploy.sh` follow.

## What the accuracy numbers mean

- They are measured on one day of footage, 12 November 2026, from the same feeder camera as most of the training footage. No frame of that day was used for training, for choosing the cut-off, or for training the teacher models (see "What the student was trained on"). The numbers say how the model does on this camera on a new day. They say nothing about another feeder, another camera or another season.
- The cut-off is chosen on validation footage, the last 15 % of each training video, never on the held-out day.
- The 899 held-out frames are picked for having birds, plus some empty frames. They are harder than a random minute at a feeder, so the share of frames counted exactly right would be higher on raw footage.
- **The truth labels are machine-made.** Boxes come from a large teacher detector and two teachers trained on this camera. Names come from two bird classifiers (BioCLIP 2 and an iNaturalist classifier). Small classifiers trained on this camera's clear cases then removed non-birds (fat balls, snow) and fixed names. A person looked at sample sheets of each group (tens of crops each), not at every frame. So the numbers measure agreement with these labels. A bird the labels missed counts against the model when the model finds it. A mistake the model learned from the labels counts in its favour. In one by-eye check of 64 "false alarms" (an earlier round), about 60 were real, correctly named birds the labels had missed.
- The qualifying rule has no minimum number of boxes per species, so a species with very few held-out boxes can pass on luck. Read the box counts next to every precision and recall.
- Nothing here claims the model names species better than a skilled volunteer.

Held-out day, 12 November 2026, 899 frames. "Named birds right" is the share of the birds the model named that were named right (precision). "Birds found" is the share of the labelled birds the model found (recall). Both are pooled over all species at the cut-off; those two columns come from a separate run of the same model on the same frames. The other columns are from `models/eval.json`.

| Detector | board median | cut-off | named birds right | birds found | frames counted exactly right | held-out frames |
|---|---|---|---|---|---|---|
| two_stage (pretrained) | 169.8 ms | 0.60 (fixed) | 0.00 | 0.00 | 0.208 | 899 |
| student 640 px | 506.6 ms | 0.50 | 0.90 | 0.69 | 0.563 | 899 |
| student 960 px (shipped) | 1108.5 ms | 0.50 | 0.93 | 0.72 | 0.582 | 899 |

The pretrained two-stage detector finds no birds at all on this camera (recall 0.00). Its 0.208 can only come from frames with no bird in them. The 960 px student "qualifies" under the rule above (three species at precision 0.90 or more and recall 0.50 or more) only because the third species is house sparrow with a single held-out box; great tit and blue tit are the other two. The 640 px student does not qualify.

The shipped student, species with at least 20 held-out boxes (every other species has fewer than 20, or none):

| Species | named birds right (precision) | birds found (recall) | held-out boxes |
|---|---|---|---|
| great tit | 0.94 | 0.75 | 1466 |
| blue tit | 0.93 | 0.69 | 308 |
| magpie | 0.79 | 0.63 | 103 |
| bullfinch | 0.83 | 0.45 | 22 |

The held-out day has no squirrel, so squirrel accuracy is only known from validation footage (training days), where the 960 px student reached precision 0.95 and recall 0.85. On the 899 held-out frames the same student named a squirrel once (confidence 0.64; it is a blurred brown bird in flight). The latch closes only after two analysed photos in a row show a squirrel or rat, so that single frame would not have closed it.

## What the student was trained on

- **Feeder footage.** One public feeder camera stream, "Talvilintulive" (Haukipudas, Finland), recorded. It belongs to its uploader and is not in this repository. The shipped model was trained on 15 days of that stream, all from October and November 2026 (5 and 22 October; 29 and 31 October; 1, 2, 3, 4, 6, 7, 8, 9, 10, 11 and 13 November), plus two videos of other (forest) feeders. No earlier-winter days are in this model.
- **Squirrels.** 400 Creative Commons photos by 273 iNaturalist observers (the attribution list is kept with the photos, outside this repository), frames of one squirrel documentary video, and squirrel cut-outs pasted into feeder frames. A real red squirrel visits this feeder. The minutes of its first visit on 22 October 2026 were kept out of training and are in the demo reel.
- **Training only, never shown.** The documentary and the two forest-feeder videos are used for training only and are never shown in the demo.
- **A worse camera.** One in four training frames also has a degraded copy (smaller, blurred, noisy, re-compressed), so the model copes with a worse camera.
- **Held out.** The test day, 12 November 2026, was not used for training (see above).

## What the demo shows

The demo reel is recorded, not live. It is 12 November 2026 from one feeder camera ("Talvilintulive"), with the red squirrel's visit of 22 October 2026 in the middle. The clock in the picture is the stream's own; the clock on the page is the demo's. The demo clip may be an edited "busy parts" cut of a longer recording (made with `tools/mine_frames.py --highlights`). Say so aloud in the demo.

## Next steps

Not built yet:

- A camera closer to the feeder: most misses are birds only 20-30 pixels wide.
- Accepting a less sure name when several photos in a row agree.
- Comparing each photo with the median of the last 5-10 minutes, to catch what changed.
- A microphone as a second witness for species by their calls.

## Licences

The pretrained two-stage detector's models come from Apache-2.0 repositories (YOLOX; the Google Coral iNaturalist bird classifier). A student model trained with Ultralytics is AGPL-3.0.

`data/` and `models/` are never committed: footage belongs to the people who filmed it.
