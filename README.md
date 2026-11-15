# Feeder Census

Feeder Census counts the birds at a winter feeder from video and shows the counts on a local web page: birds in frame now, the highest count per hour, per day and per half-month, and one evidence photo per species per day. It runs on a laptop or on an Arduino UNO Q, where the board does the detection, the counting and the page, and the laptop is only the screen.

## Run on the laptop

```
uv sync
uv run python tools/fetch_models.py
uv run python -m feeder_census --videos data/videos/demo
```

A fresh clone has no footage: fill `data/videos/demo` with your own video files first (the footage is not in this repository). Then open http://localhost:8088. `--fast` plays the footage unpaced, `--no-web` prints a line per detection instead.

`--photo-every-s SECONDS` makes the demo behave like the board's camera: it analyses one photo every SECONDS of footage and the page shows only those photos, each drawn with its own boxes and held until the next one, instead of video. For example `uv run python -m feeder_census --videos data/videos/demo --photo-every-s 5`. It replaces `--detect-every-s`, and giving both is an error. A bird is counted when it is seen in two photos in a row, so with 10 s between photos a bird must stay at the feeder for about 10 s to be counted. `board/run.sh --photo-every-s 5` passes it on to the board.

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

Milliseconds per frame on the Arduino UNO Q (4-core Kryo-V2), measured on 14 November 2026 with `python -m feeder_census.bench --detector student --video CLIP.mp4 --frames 30` (`--detector two_stage` for the first row). The clip is **real feeder footage**: 120 s of the held-out day (12 November 2026), 1280x720, prepared with `tools/prepare_video.py`. The budget is 1500 ms per frame.

| Detector | median | p90 | inside the 1500 ms budget |
|---|---|---|---|
| two_stage (pretrained) | 169.8 ms | 171.8 ms | yes |
| student 640 px (shipped) | 506.6 ms | 520.4 ms | yes |
| student 960 px | 1108.5 ms | 1127.9 ms | yes |

Both student sizes stay inside the 1.5 s budget. Started with `--photo-every-s 5`, as we run it, the demo analyses one photo every 5 s (photo mode, above); without it the demo plays the video and analyses a frame every 2 s. One photo every 5 s leaves time to spare for either student; the shipped 640 px student needs about half a second (timed on the earlier weights).

These timings were not measured again for the student shipped on 15 November 2026. 506.6 ms (640 px) and 1108.5 ms (960 px) are the timings of the earlier students with the same architecture and input size.

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

- **The cut-off.** A detector gives each box a confidence. A box counts only above a cut-off. For a student, the cut-off is picked on validation footage (the last 15 % of each training video): the lowest value from 0.50 to 0.90 (in steps of 0.05) where at least 9 in 10 of the birds it named were named right. All species are judged together, and a species with fewer than 20 validation boxes is left out, so one rare species cannot hold the cut-off up. If no value reaches 9 in 10, the cut-off is 0.90, and the card says it is a fallback. The two-stage detector keeps its fixed cut-off and never sees validation footage.
- **Too little to pick by.** If no species has at least 20 validation boxes, nothing was measured to pick by, so the student keeps the cut-off written in its own card (it is not set to 0.90), and the card says so (`default: too few validation boxes to pick`).
- **The board-time bar.** A student is eligible only when its median time on the board is at most 1500 ms (`--board-ms` takes the medians from `python -m feeder_census.bench --detector KIND --video CLIP.mp4` on the board). A candidate with no board timing is treated as eligible, except that `--promote` refuses to run until every candidate has a timing.
- **Qualifying.** A student qualifies when at least three species reach precision of at least 0.90 and recall of at least 0.50 on the held-out footage. Precision means: of the birds it named, the share named right. Recall means: of the birds in the truth labels, the share it found. A rate that could not be computed does not count.
- **Who ships.** The qualifying student that counts exactly right in the most frames ships, but only if that share is at least the pretrained detector's. When no eligible student qualifies, the eligible student that counts best still ships if it beats the pretrained detector, and the card says `qualified: false`; the page then says "Below our accuracy bar; it ships because it counts better than the alternative." That mark applies to a shipped student only: when the pretrained detector ships, the page does not say it. Otherwise the pretrained detector ships, and the card says why.
- **The tie of 15 November 2026.** The 640 px and 960 px students counted exactly the same share of held-out frames right (0.831, 747 of 899 each). The rule above has no tie-break. The 640 px student was put first because it takes half the time on the board and made no false squirrel detection on the held-out day (the 960 px one made one).
- The numbers land in `models/eval.json` (every run) and in `models/model_card.json` (only with `--promote`), which the program and `board/deploy.sh` follow.

## What the accuracy numbers mean

- They are measured on one day of footage, 12 November 2026, from the same feeder camera as most of the training footage. No frame of that day was used for training, for choosing the cut-off, or for training the teacher models (see "What the student was trained on"). The numbers say how the model does on this camera on a new day. They say nothing about another feeder, another camera or another season.
- The cut-off is chosen on validation footage, the last 15 % of each training video, never on the held-out day.
- The 899 held-out frames are picked for having birds, plus some empty frames. They are harder than a random minute at a feeder, so the share of frames counted exactly right would be higher on raw footage.
- **The truth labels are machine-made and machine-checked.** They were made by the automatic check described in "What the student was trained on": candidate boxes from the old teacher labels, three earlier students and a camera-tuned teacher, judged by a second AI model, and kept as a bird only when two votes agree on the species. On the held-out day the check turned 2,256 candidates into 1,856 birds, 392 ignore zones and 8 dropped. Of the 1,856 birds, 1,489 are the same as the old label, 193 were `unidentified` before, 164 had no old label and 10 changed species. 45 old named labels became ignore zones.
- **No person checked these labels.** The AI assistant that ran the work looked at sample sheets of the judge's decisions (for example, of 40 birds the check added, 39 were real and rightly named). No person did.
- **The test rewards agreeing with the check.** The test labels and the training labels come from the same automatic check. The fair comparison is the earlier student scored on the same checked labels (the first student row below).
- **The hardest cases are not scored.** 392 of the 2,256 candidates on the held-out day (17 %) are ignore zones: cut-off birds, blurred flight, sources that disagree. A detection in an ignore zone is neither a hit nor an error. The test is easier than counting every bird.
- The qualifying rule has no minimum number of boxes per species, so a species with very few held-out boxes can pass on luck. Read the box counts next to every precision and recall.
- Nothing here claims the model names species better than a skilled volunteer.

Held-out day, 12 November 2026, 899 frames, scored against the checked labels at cut-off 0.50. "Named birds right" is the share of the birds the model named that were named right (precision). "Birds found" is the share of the labelled birds the model found (recall). Both are pooled over all species and come from an ad-hoc scorer run on the same labels, not from `tools/evaluate.py`. "Frames counted exactly right" is from `models/eval.json`, except for the earlier student, where it is from the ad-hoc scorer. The board medians of the students are those of the earlier students (see "Measured speed").

| Detector | board median | cut-off | named birds right | birds found | frames counted exactly right | held-out frames |
|---|---|---|---|---|---|---|
| two_stage (pretrained) | 169.8 ms | 0.60 (fixed) | 1.00 (1 bird) | 0.00 | 0.171 | 899 |
| earlier shipped student 640 px (trained on old labels) | 506.6 ms | 0.50 | 0.940 | 0.811 | 0.751 | 899 |
| student 640 px (shipped) | 506.6 ms | 0.50 | 0.942 | 0.891 | 0.831 | 899 |
| student 960 px | 1108.5 ms | 0.50 | 0.949 | 0.899 | 0.831 | 899 |

The earlier shipped student was trained on the old labels. Scored on the same checked labels, the new 640 px student finds more birds (0.891 against 0.811) and counts more frames exactly right (0.831 against 0.751); named birds right is about the same (0.942 against 0.940). As a cross-check against the old labels (double boxes merged, oversized boxes ignored), the new 640 px student finds more birds (0.868 against 0.841), but named birds right falls from 0.901 to 0.848 and frames exactly right from 0.746 to 0.709, because it now detects birds the old labels do not contain.

The 640 px student ships. It and the 960 px student count exactly the same share of frames right (747 of 899 each); see "How the shipped model is chosen" for how the tie was broken.

The pretrained two-stage detector finds almost no birds on this camera: in `models/eval.json` it named one bird all day (a magpie, rightly) and found 1 of the 1,856 labelled birds. Its 0.171 can only come from frames with no bird in them, apart from at most one frame. Both new students qualify under the rule above (at least three species at precision 0.90 or more and recall 0.50 or more). For the 640 px student, five species pass: great tit, blue tit, magpie, bullfinch (30 held-out boxes) and tree sparrow (one box, so it passes on luck). Great tit, blue tit and magpie have 90 or more held-out boxes each. Great spotted woodpecker misses on precision (0.89, 16 boxes). For the 960 px student, five species pass (great tit, blue tit, magpie, tree sparrow with one held-out box, and great spotted woodpecker with 16).

The shipped 640 px student, by species (every other species has one held-out box or none), from `models/eval.json`:

| Species | named birds right (precision) | birds found (recall) | held-out boxes |
|---|---|---|---|
| great tit | 0.95 | 0.90 | 1460 |
| blue tit | 0.92 | 0.87 | 258 |
| magpie | 0.97 | 0.92 | 90 |
| bullfinch | 0.91 | 0.67 | 30 |
| great spotted woodpecker | 0.89 | 1.00 | 16 |

The held-out day has no squirrel, so squirrel accuracy is only known from validation footage, where the shipped 640 px student reached precision 0.953 and recall 0.865 (517 boxes). Validation is the held-back last 15 % of each training video, the same footage that set the cut-off, and its squirrel boxes are mostly photos, documentary frames and pasted cut-outs; so the figure is optimistic for this feeder. On the 899 held-out frames the shipped student made no false squirrel detection (the 960 px student made one). In the demo reel the simulated latch closed on the squirrel clip.

## What the student was trained on

- **Feeder footage.** One public feeder camera stream, "Talvilintulive" (Haukipudas, Finland), recorded. It belongs to its uploader and is not in this repository. The shipped model was trained on 25 days of that stream: 2 December 2024 and 2 January 2025 (earlier winter), and from 2026 the 5, 8, 12, 15, 18, 20, 22, 24, 26, 28, 29 and 31 of October and the 1, 2, 3, 4, 6, 7, 8, 9, 10, 11 and 13 of November, plus two videos of other (forest) feeders. 12 November 2026 is not among them.
- **Squirrels.** 400 Creative Commons photos by 273 iNaturalist observers (the attribution list is kept with the photos, outside this repository), frames of one squirrel documentary video, and squirrel cut-outs pasted into feeder frames. A real red squirrel visits this feeder. The training footage also contains this real red squirrel: after the label check, 936 labelled boxes, nearly all from 8 October (92), 22 October (77, its second visit that day), 31 October (121), 6 November (349) and 11 November (293) 2026, plus four single boxes on other days. Only the minutes of its first visit on 22 October 2026 were kept out of training; that clip is in the demo reel. So the demo shows the model recognising the same animal at the same feeder in a visit it had not seen, not a squirrel it had never met.
- **Training only, never shown.** The documentary and the two forest-feeder videos are used for training only and are never shown in the demo.
- **A worse camera.** One in four training frames also has a degraded copy (smaller, blurred, noisy, re-compressed), so the model copes with a worse camera.
- **Held out.** The test day, 12 November 2026, was not used for training (see above).
- **Labels checked by a second AI model (15 November 2026).** For every feeder-camera frame, boxes were pooled from five sources: the old teacher label (minus boxes too big to be one small bird), three earlier students and the camera-tuned teacher. Boxes of one bird were merged into one candidate. An open vision-language model (Qwen3-VL-8B-Instruct, Apache-2.0, served with vLLM on rented GPUs) looked at a crop of every candidate and answered a closed question: one bird, part of a bird, two or more birds, squirrel or no animal; which species from our list; is it sure. On 1,240 candidates where all five sources already agreed on one species, it named the same species in 1,196 (96.5 %). That is too weak to be the only judge. So a candidate became a labelled bird only when two votes agreed on the species among the old label, the camera-tuned teacher (confidence 0.4 or more) and the judge (only when it said it was sure); the earlier students' majority (confidence 0.25 or more) counted as one supporting vote. "Part of a bird", "two or more birds" and candidates without two agreeing votes became ignore zones. "No animal" was dropped, except when the old label, the teacher and at least two earlier students all saw a bird there; then it became an ignore zone. In a training frame an ignore zone is blurred out of the picture, and a frame is left out when the zone overlaps a kept bird. In the 25 training days the check turned 75,989 candidates into 55,881 birds (45,415 same as the old label, 5,035 `unidentified` before, 5,168 with no old label, 263 changed species), 18,765 ignore zones and 1,343 dropped; 15,208 frames have a blurred zone and 490 frames were left out. Photos, documentary frames, forest-feeder videos and pasted squirrels kept their labels. The model has no training examples of `unidentified` any more (the class slot still exists). On the held-out day the new shipped student gave the answer `unidentified` 0 times in 2,309 detections; the earlier shipped student gave it 427 times in 2,475. Nobody hand-checked these labels. The scripts are in `tools/label_check/`.
- **Training.** The shipped student is the earlier 25-day 640 px student, trained 8 more epochs on the checked labels. Its card lists 63,466 training boxes. A 960 px student was trained the same way (6 epochs). Two students trained from scratch on the checked labels (20 and 14 epochs) scored lower and are not shipped.
- **What did not help.** 19 more days of the same camera (44 days instead of 25) changed nothing measurable. Removing double boxes and oversized boxes from the old training labels by rule and re-training did not help either.

## What the demo shows

The demo reel is recorded, not live. It is 12 November 2026 from one feeder camera ("Talvilintulive"), with the red squirrel's visit of 22 October 2026 in the middle. The clock in the picture is the stream's own; the clock on the page is the demo's. The demo clip may be an edited "busy parts" cut of a longer recording (made with `tools/mine_frames.py --highlights`). Say so aloud in the demo.

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
