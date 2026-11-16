# Feeder Census

Feeder Census counts the birds at a winter feeder from video and shows the counts on a local web page: birds in frame now, the highest count per hour, per day and per half-month, and one evidence photo per species per day. It runs on a laptop or on an Arduino UNO Q, where the board does the detection, the counting and the page, and the laptop is only the screen.

## Run on the laptop

```
uv sync
uv run python tools/fetch_models.py
uv run python -m feeder_census --videos data/videos/demo
```

A fresh clone has no footage: fill `data/videos/demo` with your own video files first (the footage is not in this repository). Then open http://localhost:8088. The page only answers on the machine it runs on. `--host 0.0.0.0` opens it to the local network, and with a live camera that shows the camera picture to everyone on that network. `--fast` plays the footage unpaced, `--no-web` prints a line per detection instead.

`--photo-every-s SECONDS` makes the demo behave like the board's camera: it analyses one photo every SECONDS of footage. The page then shows two pictures: "Live", the picture as it comes in, and "What the model analysed", the last analysed photo with its own boxes, held until the next one. For example `uv run python -m feeder_census --videos data/videos/demo --photo-every-s 5`. It replaces `--detect-every-s`, and giving both is an error. A bird is counted when it is seen in two photos in a row, so with 10 s between photos a bird must stay at the feeder for about 10 s to be counted. `board/run.sh --photo-every-s 5` passes it on to the board.

A USB webcam can stand in for the video files:

```
uv run python -m feeder_census --camera /dev/video4 --camera-rotate 180 --photo-every-s 5
```

`--camera` and `--videos` are alternatives: give exactly one. `--camera` takes a device path or a camera number such as `0`. `--camera-rotate 180` turns the picture upside down, for a camera mounted that way. `--fast` only works with video files. If the camera cannot be opened, the program stops and names the device. With `--photo-every-s` the page shows the two pictures, live and analysed. The demo clock stays the same: 1 second of watching is 1 minute on the clock.

With a live camera the page shows whoever is in front of it. The program does not record the live picture, but it keeps evidence photos under `data/evidence`: one photo per species per day (`data/evidence/<date>/<species>.jpg`), replaced when that day's count rises. The page shows them to whoever opens it, and they can show people too.

`--footage-note TEXT` sets the sentence the page shows about the footage (the default says "Recorded feeder footage"), for example to say the reel is an edited cut: `board/run.sh --footage-note "Edited reel: 12 November 2026, with a squirrel visit from 22 October 2026 in the middle."`. On the board only letters, digits, spaces and `. , : -` are allowed, and it combines with `--latch`, `--fast`, `--photo-every-s` and `--fresh`.

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

### Running the board on its own

At the stand the board runs without a laptop: it starts the demo at boot, uses the USB webcam (or the recorded reel when no webcam answers) and shows the page full screen on an HDMI screen. `board/standalone/` holds the files and `board/standalone/README.md` says how they were set up by hand on the board, what it lowers in the board's security and what is not tested. The TV page is the same page opened with `?kiosk`: `http://localhost:8088/?kiosk`.

On the laptop, `python3 tools/feed_switch/switch.py` serves a page on `http://localhost:8091` with two buttons, Webcam and Feeder footage. A switch restarts the demo on the board: it took 16 s to the footage and 36 s to the webcam when tried on 15 November 2026. Set `BIRDAI_BOARD` to the board's address (for example `root@192.168.1.50`) first; `tools/feed_switch/keep-tunnel.sh` keeps `http://localhost:8088` pointing at the board's page over Wi-Fi or USB.

## Latch

One hobby servo closes a latch over the feeder while a squirrel or a rat is at it. The program closes the latch after the animal is seen in 2 detections in a row and opens it again after 5 detections in a row without one. Three options set this rule: `--pest-threshold` (how sure the model must be, from 0 to 1; default 0.5), `--latch-close-frames` (detections in a row with an animal before the latch closes; default 2) and `--latch-open-frames` (detections in a row without one before it opens; default 5). When the latch reacts to things that are not squirrels, such as a person or a box, raise `--pest-threshold` and `--latch-close-frames`. The animals (`[[pest]]` in `species.toml`) are never census birds: they are not counted, not in the tables, the CSV, the visits or the evidence photos. They are drawn on the feed by name. Seeing them needs a model trained on them. The shipped student is trained on red squirrels, so it can close the latch for a squirrel. It has no rat class (its classes are the 12 bird species, `red_squirrel` and `unidentified`), so with this model a rat does not close the latch. `species.toml` already lists the brown rat as a pest, so a later model can add it.

The servo is a DFRobot SER0006 (9 g, 180° position servo, 4.8–6 V). It turns one axis, and both pull wires of the latch are fixed to that axis. The UNO Q's microcontroller drives it with `board/latch/latch.ino`. Wiring, in words:

- The servo's signal wire to D9.
- Recommended: servo power from a separate 5 V supply, with that supply's ground joined to a GND pin on the board.
- Fallback we use (no separate supply): servo power from the board's 5V and GND pins. Keep the flap light; a jammed servo can reset the board.
- Never put 5 V on D3 or A0–A5.

The hatch is a small board hinged along its top edge. Lifted, with the slot under it exposed, is open. Hanging down over the slot is closed. So the open angle is the high one: open is 180 and closed is 0. The team set these two angles on the calibration page on 15 November 2026. An earlier camera check the same day showed that the wires are slack up to about 25 degrees, the board starts to lift at about 28 to 30 degrees and is still rising at 180. Closed is by gravity only: nothing holds the board shut. The two angles are the start values at the top of the sketch.

The servo is at the end of its range at "open". To get more lift, change the hardware: hook the wires closer to the hinge line, shorten the wires so they are just taut when the board hangs, or use a longer horn arm or a bigger spool. The sketch also attaches the servo with the pulse range from its data sheet, 500 to 2500 microseconds, instead of the library's default 544 to 2400, so that 180 should turn the servo its full 180 degrees. The team saved these angles while the board used the 500 to 2500 microsecond range. Nobody measured the range on its own. The earlier camera check, which gave open 180 and closed 25, was made with the default range. At the end of its range a servo may buzz or get warm. If it does, use a lower open angle or a smaller `SERVO_MAX_US`.

The servo moves in steps of 10 degrees, one step every 0.1 s, so a full swing takes about 1.8 s. This is in the sketch (`STEP_DEGREES`, `STEP_INTERVAL_MS`).

The sketch opens the latch by itself 30 seconds after the last close command, so the feeder does not stay shut when the program on the Linux side stops. The program repeats the close command at every detection while the latch should stay closed.

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

The link between the program and the sketch follows Arduino's documentation for the router bridge; the link was used on the board on 14 and 15 November 2026 and the board confirmed every command; whether the servo arm really moves is not yet confirmed.

### Calibrating the angles

To find the open and closed angles that fit the real latch, turn the servo by hand from a browser. Deploy, upload the sketch, then start the page and open it:

```
board/deploy.sh
arduino-cli upload -b arduino:zephyr:unoq -p /dev/ttyACM0 board/latch
board/calibrate.sh          # then open http://localhost:8090 ; stop it with: board/calibrate.sh --stop
```

The page shows the servo angle in big digits. Move the slider or press -10, -1, +1 or +10 and the servo follows. When the latch is where you want it open, press "Save as OPEN". Do the same for "Save as CLOSED". "Test: open" and "Test: close" run the latch with the saved angles. The angles are kept on the board in `data/latch_angles.json`. The microcontroller forgets them at a restart, so the demo sends them again at its start (`board/run.sh --latch router`). To make them the sketch's own start values, put the two numbers into the sketch. An angle turned by hand goes back to the open angle by itself 10 minutes after the last change, so the feeder never stays shut for good. The sketch is written to reopen a test close after 30 seconds. On 15 November 2026 the board confirmed the new calls and every command of the page. Nobody has yet reported watching the servo arm move to the saved angles. Stop the demo first (`board/run.sh --stop`) if it runs with `--latch router`: both would command the servo. From the board's shell, `python -m feeder_census.latch angle 90` also turns the servo to one angle.

## Measured speed

Milliseconds per frame on the Arduino UNO Q (4-core Kryo-V2), measured with `python -m feeder_census.bench --detector student --video CLIP.mp4 --frames 30` (`--detector two_stage` for the first row). The clip is **real feeder footage**: 120 s of the held-out day (12 November 2026), 1280x720, prepared with `tools/prepare_video.py`. The two-stage row was measured on 14 November 2026, the student rows on 15 November 2026. The budget is 1500 ms per frame.

| Detector | median | p90 | inside the 1500 ms budget |
|---|---|---|---|
| two_stage (pretrained) | 169.8 ms | 171.8 ms | yes |
| nano student 960 px (shipped, "BC 960") | 1111.1 ms | 1137.7 ms | yes |
| nano student 640 px | 510.6 ms | not recorded | yes |
| small (YOLO26s) student 640 px | 1479.4 ms | 1505.1 ms | median yes, p90 no |

The 960 px row was timed on the 25-day nano 960 px weights. The shipped 38-day weights have the same architecture and input size and were not timed again. An earlier 640 px student measured 506.6 ms on 14 November 2026.

Started with `--photo-every-s 5`, as we run it, the demo analyses one photo every 5 s (photo mode, above); without it the demo plays the video and analyses a frame every 2 s.

In the stand setup (the board alone: USB webcam, full-screen browser on HDMI, one photo every 5 s), the demo reported about 2.0 s per analysed photo on 15 November 2026 (median over five minutes, about 1.9 to 2.1 s). Before the browser and the camera ran on the board it was about 1.25 s. About 540 MB of memory was free.

Earlier stand-in measurement, for the pretrained two-stage detector only (`python -m feeder_census.bench --detector two_stage --video CLIP.mp4 --frames 30`). Both rows use the same 60 s, 1280x720, 15 fps test clip. **That clip is a stand-in, not feeder footage: it is made of three still photos of a great tit, a blue tit and a bullfinch, panned and zoomed.**

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

- **The cut-off.** A detector gives each box a confidence. A box counts only above a cut-off. For a student, the cut-off is picked on the dataset's validation frames: the lowest value in a grid from 0.25 to 0.90 (in steps of 0.05) where at least 9 in 10 of the birds it named were named right. 0.25 is the detector's own floor (it drops weaker boxes), so a lower cut-off would mean nothing. All species are judged together, and a species with fewer than 20 validation boxes is left out, so one rare species cannot hold the cut-off up. If no value reaches 9 in 10, the cut-off is 0.90, and the card says it is a fallback. The two-stage detector keeps its fixed cut-off and never sees validation footage.
- **Too little to pick by.** If no species has at least 20 validation boxes, nothing was measured to pick by, so the student keeps the cut-off written in its own card (it is not set to 0.90), and the card says so (`default: too few validation boxes to pick`).
- **The board-time bar.** A student is eligible only when its median time on the board is at most 1500 ms (`--board-ms` takes the medians from `python -m feeder_census.bench --detector KIND --video CLIP.mp4` on the board). A candidate with no board timing is treated as eligible, except that `--promote` refuses to run until every candidate has a timing.
- **Qualifying.** A student qualifies when at least three species reach precision of at least 0.90 and recall of at least 0.50 on the held-out footage. Precision means: of the birds it named, the share named right. Recall means: of the birds in the truth labels, the share it found. A rate that could not be computed does not count.
- **Who ships.** The qualifying student that counts exactly right in the most frames ships, but only if that share is at least the pretrained detector's. When no eligible student qualifies, the eligible student that counts best still ships if it beats the pretrained detector, and the card says `qualified: false`; the page then says "Below our accuracy bar; it ships because it counts better than the alternative." That mark applies to a shipped student only: when the pretrained detector ships, the page does not say it. Otherwise the pretrained detector ships, and the card says why.
- **What ships since 15 November 2026 (about 06:15).** The run was `tools/evaluate.py --candidates two_stage student:640 student:960 --board-ms two_stage=169.8,960=1111.1,640=510.6 --promote` on 899 frames of 12 November 2026. The nano 960 px student trained on 38 days counted 0.909 of the frames exactly right at cut-off 0.25 and qualifies, so it ships. Its 640 px sibling, trained the same way, counted 0.855; the pretrained two-stage detector 0.171. The page calls the shipped model "BC 960": the team's name for it, set by hand in `models/student/feeder.json` and `models/model_card.json`. `tools/evaluate.py` and `models/eval.json` call it "Feeder student 960". Until then a 640 px student trained on 25 days shipped (0.831 at cut-off 0.50).
- **For the model that ships, the cut-off was picked on 7,599 frames from 13 days of October 2026** (listed in "What the student was trained on"). When that frame set was made, none of those days had been used for training. The shipped model was then trained on other frames of those same 13 days. So the cut-off is picked on days the model has seen, though not on frames it has seen. The pick came out at 0.25, the lowest value of the grid.
- The numbers land in `models/eval.json` (every run) and in `models/model_card.json` (only with `--promote`), which the program and `board/deploy.sh` follow.

## What the accuracy numbers mean

- They are measured on one day of footage, 12 November 2026, from the same feeder camera as most of the training footage. No frame of that day was used for training, for choosing the cut-off, or for training the teacher models (see "What the student was trained on"). The numbers say how the model does on this camera on a new day. They say nothing about another feeder, another camera or another season.
- The cut-off was chosen on 7,599 frames from 13 days of October 2026 (listed below) that the shipped model also trained on (other frames of them), never on the held-out day. Only 12 November 2026 and the five exam days below are days the shipped model never trained on.
- The 899 held-out frames are picked for having birds, plus some empty frames. They are harder than a random minute at a feeder, so the share of frames counted exactly right would be higher on raw footage.
- **The truth labels are machine-made and machine-checked.** They were made by the automatic check described in "What the student was trained on": candidate boxes from the old teacher labels, three earlier students and a camera-tuned teacher, judged by a second AI model, and kept as a bird only when two votes agree on the species. On the held-out day the check turned 2,256 candidates into 1,856 birds, 392 ignore zones and 8 dropped. Of the 1,856 birds, 1,489 are the same as the old label, 193 were `unidentified` before, 164 had no old label and 10 changed species. 45 old named labels became ignore zones.
- **No person checked these labels.** The AI assistant that ran the work looked at sample sheets of the judge's decisions (for example, of 40 birds the check added, 39 were real and rightly named). No person did.
- **The test rewards agreeing with the check.** The test labels and the training labels come from the same automatic check, so part of any gain may be agreement with that check. An earlier 640 px student trained on the old labels counted 0.751 of the frames exactly right on the same checked labels, but that number is from an ad-hoc scorer at cut-off 0.50 and cannot be set directly against the 0.909 below.
- **The hardest cases are not scored.** 392 of the 2,256 candidates on the held-out day (17 %) are ignore zones: cut-off birds, blurred flight, sources that disagree. A detection in an ignore zone is neither a hit nor an error. The test is easier than counting every bird.
- The qualifying rule has no minimum number of boxes per species, so a species with very few held-out boxes can pass on luck. Read the box counts next to every precision and recall.
- Nothing here claims the model names species better than a skilled volunteer.

Held-out day, 12 November 2026, 899 frames, scored by `tools/evaluate.py` against the checked labels; every number is from `models/eval.json`. "Birds found" is pooled over all species: the per-species recall times the held-out boxes in `models/eval.json`, summed, out of the 1,856 labelled birds. The 817 of 899 is 0.909 times 899. A pooled "named birds right" is not given for the students, because `models/eval.json` does not say how many false squirrel boxes the 960 px student drew.

| Detector | board median | cut-off | birds found | frames counted exactly right | held-out frames |
|---|---|---|---|---|---|
| two_stage (pretrained) | 169.8 ms | 0.60 (fixed) | 0.001 (1 of 1,856) | 0.171 | 899 |
| nano student 640 px, 38 days | 510.6 ms | 0.25 | 0.919 (1,706 of 1,856) | 0.855 | 899 |
| nano student 960 px, 38 days (shipped, "BC 960") | 1111.1 ms | 0.25 | 0.954 (1,771 of 1,856) | 0.909 (817 of 899) | 899 |

The 960 px board median was timed on the 25-day weights (see "Measured speed"). Until the early morning of 15 November 2026 a 640 px student trained on 25 days shipped; `tools/evaluate.py` measured it at 0.831 of the frames counted exactly right, at cut-off 0.50.

The pretrained two-stage detector finds almost no birds on this camera: in `models/eval.json` it named one bird all day (a magpie, rightly) and found 1 of the 1,856 labelled birds. Its 0.171 can only come from frames with no bird in them, apart from at most one frame. Both students qualify under the rule above (at least three species at precision 0.90 or more and recall 0.50 or more). For the shipped 960 px student, four species pass: great tit, blue tit and magpie (90 or more held-out boxes each) and great spotted woodpecker (16 boxes, so luck plays a part). Bullfinch misses on precision (0.879, 30 boxes). For the 640 px student, five species pass: great tit, blue tit, magpie, bullfinch (30 boxes) and tree sparrow (one box, so it passes on luck); great spotted woodpecker misses on precision (0.882, 16 boxes).

The shipped 960 px student, by species, at cut-off 0.25, from `models/eval.json` (the same numbers are in `models/model_card.json` and `models/student/feeder.json`):

| Species | named birds right (precision) | birds found (recall) | held-out boxes |
|---|---|---|---|
| great tit | 0.952 | 0.960 | 1460 |
| blue tit | 0.909 | 0.934 | 258 |
| magpie | 0.978 | 0.978 | 90 |
| bullfinch | 0.879 | 0.967 | 30 |
| great spotted woodpecker | 1.00 | 0.625 | 16 |
| tree sparrow | 0.50 | 1.00 | 1 |
| house sparrow | none named | 0.00 | 1 |

Jay, nuthatch, crested tit, coal tit and willow tit have no held-out box on that day, and the model named none of them.

The held-out day has no squirrel. Red squirrel has precision 0.0 with 0 held-out boxes: the shipped model drew at least one squirrel box on a day with no squirrel. `models/eval.json` does not give the exact number. The real squirrel in the held-out clip of 22 October 2026 scores 0.86 on average (0.34 to 0.96) when it is in clear view. With the earlier 640 px student, the simulated latch closed on that clip in the demo reel.

**Exam days.** Five more days of the same camera that no model trained on: 3, 9, 14, 19 and 25 October 2026, 2,808 frames, labelled by the same automatic check. They were scored with an ad-hoc scorer, not `tools/evaluate.py`. That scorer picks its cut-off on the scored frames themselves (grid 0.30 to 0.90), so its numbers run a little high and are only good for comparing models with each other. The exam days were used to compare models and to choose what to train next, so they are not an untouched test either. On 12 November 2026 the same scorer gives lower numbers than `tools/evaluate.py` (0.887 against 0.909 for the shipped model); its grid starts at 0.30, while the official cut-off is 0.25. Frames counted exactly right:

| Model | exam days (2,808 frames) | 12 November 2026, ad-hoc scorer |
|---|---|---|
| nano 960 px, 25 days | 0.915 | 0.854 |
| **nano 960 px, 38 days, 8 epochs (ships)** | 0.922 | 0.887 |
| same, second training run with another random seed | 0.923 | 0.875 |
| same, 14 epochs | 0.920 | 0.881 |
| control: nano 960 px, 25 days, 8 more epochs (more training, no more days) | 0.916 | 0.853 |
| nano 640 px, 38 days | 0.914 | 0.839 |
| small (YOLO26s) 640 px, 25 days, 30 epochs | 0.922 | 0.879 (official: 0.887 at cut-off 0.30) |
| small 640 px weights, then 8 epochs on 38 days | 0.921 | 0.861 |
| nano 960 px, 38 days + 2,948 frames of other feeders | 0.917 | 0.855 |

## What the student was trained on

- **Feeder footage.** One public feeder camera stream, "Talvilintulive" (Haukipudas, Finland), recorded. It belongs to its uploader and is not in this repository. The shipped model was trained on 38 days of that stream. First 25 days: 2 December 2024 and 2 January 2025 (earlier winter), and from 2026 the 5, 8, 12, 15, 18, 20, 22, 24, 26, 28, 29 and 31 of October and the 1, 2, 3, 4, 6, 7, 8, 9, 10, 11 and 13 of November. Then 13 more days of October 2026: the 1, 2, 4, 6, 7, 10, 11, 13, 16, 17, 21, 23 and 27. Plus two videos of other (forest) feeders. 12 November 2026 and the five exam days (3, 9, 14, 19 and 25 October 2026) are not among them. Only two 2026 stream days of this camera remain unused: 5 and 14 November.
- **Squirrels.** 400 Creative Commons photos by 273 iNaturalist observers (the attribution list is kept with the photos, outside this repository), frames of one squirrel documentary video, and squirrel cut-outs pasted into feeder frames. A real red squirrel visits this feeder. The training footage also contains this real red squirrel: in the first 25 days, after the label check, 936 labelled boxes, nearly all from 8 October (92), 22 October (77, its second visit that day), 31 October (121), 6 November (349) and 11 November (293) 2026, plus four single boxes on other days. Only the minutes of its first visit on 22 October 2026 were kept out of training; that clip is in the demo reel. So the demo shows the model recognising the same animal at the same feeder in a visit it had not seen, not a squirrel it had never met.
- **Training only, never shown.** The documentary and the two forest-feeder videos are used for training only and are never shown in the demo.
- **A worse camera.** One in four training frames also has a degraded copy (smaller, blurred, noisy, re-compressed), so the model copes with a worse camera.
- **Held out.** The test day, 12 November 2026, was not used for training (see above).
- **Labels checked by a second AI model (15 November 2026).** For every feeder-camera frame, boxes were pooled from five sources: the old teacher label (minus boxes too big to be one small bird), three earlier students and the camera-tuned teacher. Boxes of one bird were merged into one candidate. An open vision-language model (Qwen3-VL-8B-Instruct, Apache-2.0, served with vLLM on rented GPUs) looked at a crop of every candidate and answered a closed question: one bird, part of a bird, two or more birds, squirrel or no animal; which species from our list; is it sure. On 1,240 candidates where all five sources already agreed on one species, it named the same species in 1,196 (96.5 %). That is too weak to be the only judge. So a candidate became a labelled bird only when two votes agreed on the species among the old label, the camera-tuned teacher (confidence 0.4 or more) and the judge (only when it said it was sure); the earlier students' majority (confidence 0.25 or more) counted as one supporting vote. "Part of a bird", "two or more birds" and candidates without two agreeing votes became ignore zones. "No animal" was dropped, except when the old label, the teacher and at least two earlier students all saw a bird there; then it became an ignore zone. In a training frame an ignore zone is blurred out of the picture, and a frame is left out when the zone overlaps a kept bird. In the 25 training days the check turned 75,989 candidates into 55,881 birds (45,415 same as the old label, 5,035 `unidentified` before, 5,168 with no old label, 263 changed species), 18,765 ignore zones and 1,343 dropped; 15,208 frames have a blurred zone and 490 frames were left out. Photos, documentary frames, forest-feeder videos and pasted squirrels kept their labels. The frames of the 13 added October days went through the same check: 53,803 candidates judged, 42,105 checked frames added. The model has no training examples of `unidentified` any more (the class slot still exists). On the held-out day the first student trained on the checked labels (640 px, 25 days) gave the answer `unidentified` 0 times in 2,309 detections; the student before it gave it 427 times in 2,475. Nobody hand-checked these labels. The scripts are in `tools/label_check/`.
- **Training.** The shipped student is a YOLO26n ("nano") that reads 960 x 960 px pictures, with 2,540,204 parameters (counted with Ultralytics on the trained weights). It is the 960 px student that had been trained on the 25 checked days, trained 8 more epochs on the 38 days. The training set has 103,798 frames. Training boxes per species, from `models/student/feeder.json` (`train_boxes`): great tit 45,223, blue tit 16,090, bullfinch 12,299, tree sparrow 8,309, magpie 6,517, jay 5,270, red squirrel 4,320, house sparrow 1,810, nuthatch 1,174, great spotted woodpecker 840, crested tit 143, coal tit 108, willow tit 39.
- **What helped.** Reading 960 px instead of 640 px. And 13 more checked days of the same camera: about +3 points on 12 November 2026, seen again in a second training run, and under one point on the exam days (see the exam-day table above).
- **What did not help.** An automatic search over training settings ("evolution": 16 variants per generation, 18 generations) reached 0.926 on the days it was tuned on but 0.906 on the exam days, below the plain model. A bigger model (small, 640 px) gave the same accuracy and takes 1,479 ms on the board against 1,111 ms. Longer training did not help. Frames from other feeders did not help: Creative Commons streams from Finland, Russia, the UK, Germany and Poland, 2,948 checked frames trained on with no gain, and 5,630 more checked frames not trained on. Removing double boxes and oversized boxes from the old training labels by rule and re-training did not help either. An earlier test found that 19 more days of the same camera changed nothing measurable, but those days had uncleaned labels; with checked labels, more days did help.

## What the demo shows

The demo reel is recorded, not live. It is 12 November 2026 from one feeder camera ("Talvilintulive"), with the red squirrel's visit of 22 October 2026 in the middle. The clock in the picture is the stream's own; the clock on the page is the demo's. The demo clip may be an edited "busy parts" cut of a longer recording (made with `tools/mine_frames.py --highlights`). Say so aloud in the demo.

The demo can also take a live USB webcam (`--camera`) instead of the reel. At the hackathon stand the webcam looks at a wooden model feeder in a room. **The model only knows the one feeder camera it was trained on.** In the room it drew "Red squirrel" boxes on a person and on the wooden box at 0.55 to 0.60 confidence, and the hatch went up and down. Since then the board runs with `--pest-threshold 0.8 --latch-close-frames 3` (see "Latch"). After that change the hatch closed once in the first five minutes and not at all in the next four. What set off that one closing is not known. This is a limitation, not a solved problem.

The page is one screen: two pictures on the left, bird stats and tech specs on the right. On the TV it is opened with `?kiosk`.

## Next steps

Not built yet:

- A camera closer to the feeder: most misses are birds only 20-30 pixels wide (earlier model).
- Accepting a less sure name when several photos in a row agree.
- Comparing each photo with the median of the last 5-10 minutes, to catch what changed.
- A microphone as a second witness for species by their calls.
- A small hand-checked test set. Every accuracy number above is measured against machine-checked labels; this is still the missing piece.

## Licences

The pretrained two-stage detector's models come from Apache-2.0 repositories (YOLOX; the Google Coral iNaturalist bird classifier). A student model trained with Ultralytics is AGPL-3.0.

`data/` and `models/` are never committed: footage belongs to the people who filmed it.
