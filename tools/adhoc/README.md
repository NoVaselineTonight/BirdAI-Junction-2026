# One-off scripts from the model night

These are the one-off scripts from the night of 14 to 15 November 2026. They were run by hand on rented GPU
machines (and on the laptop and one main machine) to mine frames, label them, check the labels, build the datasets,
train, search, score and export the shipped model (the search's role in the shipped model is not shown by the
scripts). They are kept so that the way the model was made can be read.

Please read them as a record, not as a tool:

- They were not reviewed or tested like the rest of the repo. They are not part of `uv run pytest`.
- They have hard-coded paths (`~/birdai/data/...`, `/root/birdai/...`), expect machines, accounts and files that
  are not in the repo, and will not run as they are.
- Private details were replaced by placeholders: addresses of rented machines are `MACHINE_IP` (every distinct
  machine got the same placeholder), the author's home folder is `$HOME` or `$HOME/WORKDIR`, SSH key names are `KEY`,
  the labels of the spare cloud accounts are `ACCOUNT_B`, `ACCOUNT_C`, `ACCOUNT_D`, and the ssh alias of the main
  machine is `MAIN_HOST`. Nothing else was changed in the scripts. YouTube ids and channel names are left in, because they say which public
  footage was used.
- Machine names such as `birdai-fast`, `birdai-check`, `scan3`, `g13` are the names the rented machines had that night.
- Where a script has a reviewed copy in the repo it says so. The scripts in `tools/` (`mine_frames.py`,
  `autolabel.py`, `build_dataset.py`, `train_student.py`, `evaluate.py`, `review_sheets.py`) are called by many of them.
  Where a name appeared in more than one place, the version from the main training machine was kept.

Not in the repo: the footage (it belongs to the people who streamed it), the mined frames, the labels, the datasets
and the model weights.

Layout: `footage/` (9 files), `datasets/` (13), `labelling/` (45), `training/` (27), `search/` (4), `scoring/` (35),
`machines/` (28), `board/` (1). 162 files.

## How the shipped model was made

Only what the scripts show. Steps that happened outside these scripts are marked as such.

1. Footage. Whole days of the public feeder-camera live stream (files named `talvilintulive-YYYYMMDD`) and some
   other feeders were downloaded with `yt-dlp` (`footage/dl8.sh`, `dlx.sh`, `dl-relay*.sh`, `stream-d3.sh`,
   `stream-d4.sh`, `datasets/run-more.sh`, `labelling/worker*.sh`, `labelling/proc-new.sh`). 12 Nov is the held-out
   test day and is never trained on. The first downloads are not in these scripts; `datasets/run-mine.sh` waits for them.
2. Frames. `tools/mine_frames.py` picks bird frames from the videos: `datasets/run-mine.sh` for the first days,
   `datasets/run-more.sh`, `labelling/worker*.sh` and `labelling/proc-own*.sh` for later days (long streams are cut
   into one-hour pieces first).
3. Teacher labels. `tools/autolabel.py` labels the frames (`labelling/run-label.sh`, `run-label2.sh`,
   `run-relabel-main.sh`, `worker*.sh`). Two bigger detectors trained on this camera (`training/big_train.py`,
   `big_train2.py`, started with `training/run-big.sh`) propose birds the first teachers missed
   (`labelling/big_propose.py`, `propose2.sh`, `propose-run.sh`). CLIP scores (`embed.py`, `birdness.py`) and the
   relabel passes (`relabel.py`, `relabel2.py`, `relabel3.py`, run by `run-v3-a.sh`, `run-v4-a.sh`, `run-v5-a.sh`)
   decide bird or not and the species. Squirrel training frames were cut from photos and a video and pasted into
   feeder frames (`datasets/squirrel_cut.py`, `squirrel_paste.py`); worse-quality copies of frames were added by
   `datasets/degrade.py`. The datasets of the early rounds (v1 to v5) were built by `training/run-v1.sh`,
   `run-v2a.sh`, `datasets/run-v3-build.sh`, `run-v4-build.sh`, `run-v5-build.sh` with `tools/build_dataset.py`.
4. Label check by a second AI model. `labelling/cand.py` pools candidate birds for every frame (old label, earlier
   students, the camera-tuned teacher); `labelling/judge.py` asks a served vision-language model
   (Qwen3-VL-8B-Instruct through vLLM, seen in `training/run-v9.sh` and `labelling/run-fit.sh`) about every crop;
   `labelling/truth.py` turns candidates and answers into checked labels (a species needs two agreeing votes).
   `labelling/run-v8-main.sh`, `run-v8-train-main.sh` and `run-truth-train.sh` ran it for the 25-day training set
   (dataset v8), `labelling/run-fit.sh` for the 13 selection days and 5 exam days. Reviewed copies of `cand.py`,
   `judge.py`, `truth.py` are in `tools/label_check/`.
5. Training, round 8 (25 training days). `training/run-train8.sh` runs `training/train_v8.py` on dataset v8: the 960 px
   nano model (`v8a_960`) starts from the earlier v4 960 weights, 6 epochs; a 640 px one (from the v4 640 weights, 8 epochs) and
   two runs from the stock `yolo26n.pt` weights (20 and 14 epochs) went alongside. The earlier rounds are `training/run-v1.sh`, `run-v2a.sh`, `run-v3-b.sh`, `train-v3.sh` to
   `train-v7.sh`.
6. Training, round 9 (38 training days). `training/run-v9.sh` checks (step 4) the frames of 13 more days; the
   frames were pushed by `machines/push-x2.sh`, and the scripts that mined and labelled them are not identified here.
   It then builds dataset v9 (the 25 checked days plus the 13 new ones) and runs `training/train_v9.py`: 8 more
   epochs at 960 px from the `v8a_960` weights (`v9_960_e8`), plus a 14 epoch run, a 640 px run and a control on
   dataset v8. `run-v9c.sh` is the restart from the training step after a crash (`fix-v9.sh`, `fix-v9c.sh`).
   `training/run-v10.sh` is a later round (other-feeder frames added, a second seed); the scripts do not show that it
   was shipped.
7. Search over training settings (side track). `search/evolve.py` and `search/evo_one.py` run a population-based
   search of training settings on 8 GPUs, scored on days the model never trained on; `search/score_loop.sh` scores
   size-test runs the same way. What the scripts do not show is how its result was used for the shipped model.
8. Export. `training/export_pt.py` turns the chosen `.pt` into `feeder.onnx` and `feeder.json` in the layout of
   `tools/train_student.py` (it imports `train_v8.py` for that).
9. Official scoring. `scoring/eval-v9.sh` exports the `v9_960_e8` and `v9_640_e8` weights with `export_pt.py` and runs
   `tools/evaluate.py` on dataset v8n (cut-off picked on the 13 selection days, measured on 12 Nov) with
   `--promote`. `scoring/exam-more*.sh`, `rescore.py`, `fail*.py` and the other scoring scripts are the checks around it.
   Not visible in the scripts: the manual copy of the promoted model into the repo and onto the board.

## footage/

| File | What it does |
| --- | --- |
| `cut-squirrel.sh` | Cuts a 175 s squirrel visit from the 22 Oct stream day into a 720p clip for the demo reel. |
| `cut_demo.py` | Cuts the busiest parts of the held-out day (12 Nov) into a clip of about 10 minutes, using the scan results in `mining.csv`. |
| `dl-relay.sh` | On a machine YouTube accepts: downloads a list of videos and sends each to the processing machine over rsync, then marks the set ready. |
| `dl-relay3.sh` | Same as `dl-relay.sh` without `--inplace` on the rsync. |
| `dl8.sh` | Downloads more stream days at 720p, to this machine or to another one. |
| `dlx.sh` | On the `scan3` machine: downloads ten more days and hands each to `scan4` (YouTube blocked its address). |
| `make-reel.sh` | Demo reel: two minutes of the held-out day, then the held-out squirrel visit, then the rest of the day. |
| `stream-d3.sh` | Streams each day of video straight from YouTube through to the processing machine, nothing stored locally (batch d3). |
| `stream-d4.sh` | The same for batch d4. |

## datasets/

| File | What it does |
| --- | --- |
| `clean_labels.py` | Copies a YOLO dataset with two mechanical label defects removed (oversized boxes, double boxes). Reviewed copy: `tools/label_check/clean_labels.py` (identical). |
| `degrade.py` | Makes worse-quality copies (shrink, JPEG, blur, noise) of training frames with the same labels. |
| `findsq.py` | Draws the weak detections whose BioCLIP guess was jay or squirrel-like at full size, to look at them. |
| `run-mine.sh` | Waits for the downloads, then runs `tools/mine_frames.py` on all videos. |
| `run-more.sh` | Downloads three more November days and mines them into a second frames folder (training only). |
| `run-sqcut.sh` | Runs `squirrel_cut.py` after clearing its old output. |
| `run-v3-build.sh` | Round 3: degraded copies, squirrel composites, builds dataset v3 and sends it to the training machine. |
| `run-v4-build.sh` | The same for dataset v4. |
| `run-v5-build.sh` | The same for dataset v5 (extra-days round). |
| `sqdebug.py` | Tries YOLO-World with different class lists on squirrel photos to see which one finds squirrels. Not documented further. |
| `squirrel_cut.py` | Finds the squirrel in squirrel photos and in a squirrel video (two detectors, CLIP, SAM outline) and cuts it out. |
| `squirrel_paste.py` | Pastes squirrel cut-outs into feeder frames (training footage only) to teach the squirrel class. |
| `stage_xf.py` | Stages teacher-labelled frames of other feeders as a one-split dataset for the label check. |

## labelling/

| File | What it does |
| --- | --- |
| `after-big.sh` | On the main machine: when the big teacher is trained, sends its weights to the workers; then merges frames in and lets the big teacher propose missed birds. |
| `big_propose.py` | The camera-tuned big teacher proposes birds the first teacher missed (no overlap with an existing box) on training frames only. |
| `birdness.py` | Scores every labelled box for "is this a bird at all" with a general CLIP model and writes contact sheets. |
| `cand.py` | Label check, step 1: pools candidate birds per frame from the old label, three students and the camera-tuned teacher. Reviewed copy: `tools/label_check/cand.py` (3 lines differ: a `--prefix` filter and `half=True`). |
| `chain-d4.sh` | On the processing machine: when batch d3 is through, processes batch d4. |
| `chain-xf2.sh` | On the processing machine: when wave xf1 is through, processes wave xf2 (videos arrive by relay). |
| `cleanup-label.sh` | Stops every labelling and embedding run and its follow-up script on one machine. |
| `embed.py` | CLIP embedding and two zero-shot scores (bird, squirrel) for every labelled box. |
| `get-big2.sh` | When teacher 2 is trained on the fast machine, fetches its weights and hands them to the workers. |
| `judge.py` | Label check, step 2: asks the served vision-language model about every candidate crop. Reviewed copy: `tools/label_check/judge.py` (identical). |
| `proc-new.sh` | On a processing machine: downloads other-feeder footage, picks bird frames, labels with the teachers, runs the automatic check. |
| `proc-own.sh` | On the 8-GPU machine: more days of our own camera; videos arrive by relay, then mine, label, check. |
| `proc-own2.sh` | A later version of `proc-own.sh` that mines each day's video as soon as it arrives (up to four at once) instead of waiting for the whole set. |
| `propose-run.sh` | On a worker: when its labels are embedded and the big teacher's weights have arrived, runs `big_propose.py` and embeds the proposals. |
| `propose2.sh` | Second round of proposals with the second teacher, on top of the first round. |
| `relabel.py` | First relabelling: turns BioCLIP-only predictions into labels by an agreement rule and splits the days (12 Nov held out). |
| `relabel2.py` | Second pass: uses the bird-or-not score to drop non-birds. |
| `relabel3.py` | Third pass: a classifier trained on this camera's clear cases decides bird or not, and a squirrel score finds squirrel visits. |
| `run-fit.sh` | Builds machine-checked labels (`cand.py`, `judge.py`, `truth.py`) for frames of days the v8 models never trained on: 13 selection days and 5 exam days. |
| `run-label.sh` | Waits for mining, then runs `tools/autolabel.py` and `tools/review_sheets.py`. |
| `run-label2.sh` | When the 9 to 11 Nov scan ends, labels those frames with the teachers and embeds them. |
| `run-relabel-main.sh` | Relabels the main machine's frames with the teacher at a lower bar (0.05), then embeds. |
| `run-truth-train.sh` | Runs `truth.py` on the training split of dataset v5 into dataset v8. |
| `run-v3-a.sh` | Round 3, stage A: collects frames and labels from the workers and relabels everything as tag v3. |
| `run-v4-a.sh` | The same for tag v4. |
| `run-v5-a.sh` | The same for tag v5 (extra days). |
| `run-v8-main.sh` | Runs `truth.py` for the test and validation splits of dataset v8 on the main machine. |
| `run-v8-train-main.sh` | Runs `truth.py` for the training split of dataset v8 and removes the 19 extra October days (the 25-day set). |
| `samples.py` | Draws the final training labels on a spread of frames for a person to look at. |
| `sheet2.py` | Sample sheets of the label check's decisions (added, ignored, changed, dropped). |
| `sheets.py` | Per-day counts of BioCLIP-only labels and sample contact sheets per species. |
| `sqcount.py` | Counts the squirrel boxes the label check keeps, per day. Not documented further. |
| `start-own.sh` | Waits for the automatic setup, then starts the own-camera processing. |
| `start-xf1.sh` | Starts `proc-new.sh` for wave xf1 (ten other-feeder videos, listed by YouTube id). |
| `teachertest.py` | Tests whether the teacher finds, with other settings, birds the student found and the teacher did not box. |
| `truth.py` | Label check, step 3: turns candidates and the judge's answers into checked labels. Reviewed copy: `tools/label_check/truth.py` (identical). |
| `worker.sh` | Scan worker: installs what it needs, downloads eight more days at 720p, mines training frames. |
| `worker2.sh` | After mining: labels the frames with the teachers and scores bird-or-not on the worker's GPU. |
| `worker3.sh` | After mining: labels with the teachers and computes embeddings on the worker's GPU. |
| `worker4.sh` | Second attempt with the GPU ready: scan the eight days, then label and embed. |
| `worker5.sh` | Scan worker 4: ten more days at 720p, mine frames, teacher labels, embeddings. |
| `worker6.sh` | When the videos have arrived from another machine: mine, label with the teachers, embed. |
| `worker7.sh` | Follow-up with the better teacher: waits for the scan, then labels at bar 0.05 and embeds. |
| `worker8.sh` | One worker's whole chain for the extra days: cut streams into one-hour pieces, mine, label, embed, both teachers propose. |
| `worker8b.sh` | A variant of `worker8.sh` for the fast machine, whose miner handles one piece at a time in its second pass. |

## training/

| File | What it does |
| --- | --- |
| `after-v1.sh` | When the v1 960 model is exported: stops the v1 640 run and measures v1 960. |
| `big_train.py` | Trains a large detector (YOLO26m, 1280 px) on this camera's training split: the in-domain teacher. |
| `big_train2.py` | The second, larger teacher (YOLO26l, 1280 px, two GPUs). |
| `export_pt.py` | Exports a trained `.pt` to the project's student layout (`feeder.onnx` and `feeder.json`); imports `train_v8.py`. |
| `fix-v9.sh` | Installs missing build headers on the 8-GPU machine and restarts `run-v9.sh` from the judge step as `run-v9b.sh`. |
| `fix-v9c.sh` | Installs a missing Python module and restarts from the training step as `run-v9c.sh`. |
| `run-big.sh` | Starts `big_train.py` and lists the weights. |
| `run-s640-main.sh` | Model-size test: YOLO26s at 640 px on the checked labels on the main machine's GPU, with `score_loop.sh`. |
| `run-train8.sh` | Round 8: stops the judge servers, trains four students side by side on dataset v8 with `train_v8.py` and scores them. |
| `run-v1.sh` | Version 1: relabel, build dataset v1, train a quick model and the full models with `tools/train_student.py`. |
| `run-v10.sh` | Second round on the 8-GPU machine: v9 plus other-feeder wave 1 at 960, a small 640 model, a repeat with another seed; writes `train_v10.py` itself. |
| `run-v2a.sh` | Version 2a: cleaned labels and squirrel frames; trains 960 and 640 side by side. |
| `run-v3-b.sh` | Round 3, stage B: degraded copies, squirrel composites, dataset, training at 960 and 640, measurement. |
| `run-v9.sh` | Round 9 on the 8-GPU machine: check 13 more days, build dataset v9 (38 days), run `train_v9.py` four ways, score; writes `train_v9.py` itself. |
| `run-v9c.sh` | Restart of `run-v9.sh` from the training step. |
| `train-v3.sh` | When dataset v3 has arrived, trains the 960 and 640 students side by side. |
| `train-v4.sh` | The same for dataset v4. |
| `train-v4b.sh` | The same, each starting from the 16-day model's weights. |
| `train-v5.sh` | The same for dataset v5, with a base round given as argument. |
| `train-v5b.sh` | As `train-v5.sh` with separate epoch counts for 960 and 640. |
| `train-v6.sh` | Cleans the 25-day labels with `clean_labels.py`, then fine-tunes both sizes from the v4 weights. |
| `train-v7.sh` | Small re-training of the 44-day 960 px student from its own weights, then scores it. |
| `train_big.py` | One plain training run of a student of another size (for example YOLO26s at 640) on the checked labels. |
| `train_student_nocache.py` | A copy of `tools/train_student.py` that differs in one line (`cache=False`, batch 32). |
| `train_v10.py` | The training script of `run-v10.sh`: `train_v9.py` plus a `--seed` option. |
| `train_v8.py` | A copy of `tools/train_student.py` that differs in one line (`cache=False`, batch size and workers from the environment). |
| `train_v9.py` | Plain Ultralytics training from given weights (model, data, image size, epochs, batch, devices), used for round 9. |

## search/

| File | What it does |
| --- | --- |
| `evo_one.py` | One individual of the evolution run: trains a little from the parent's weights, then scores it; also scores a checkpoint alone with `--score-only`. |
| `evolve.py` | Population-based training of the student on one machine: each generation trains every member for one epoch with its own settings, keeps the top quarter and mutates the rest. |
| `run-evo.sh` | Starts population-based training on 8 GPUs with fitness on days the lineage never trained on. |
| `score_loop.sh` | Scores every new checkpoint of a size-test run on the never-trained days. |

## scoring/

| File | What it does |
| --- | --- |
| `curve.py` | Precision and recall of a student at several confidence levels, on test and val. |
| `curve2.py` | Like `curve.py` on the test split only, building the detector from the model's own card so older models can be scored on the newest labels. |
| `errsheet.py` | Contact sheets of a student's false alarms and misses on the held-out day at one threshold. |
| `eval-s640.sh` | Exports the bigger YOLO26s 640 student and runs `tools/evaluate.py` on it. |
| `eval-s640b.sh` | A second version of `eval-s640.sh`. |
| `eval-v1.sh` | Runs `tools/evaluate.py` on dataset v1. |
| `eval-v3.sh` | Fetches the two v3 students from the fast machine and measures them on the held-out day. |
| `eval-v4.sh` | The same for v4. |
| `eval-v5.sh` | The same for v5. |
| `eval-v6.sh` | Fetches the v6 students and scores them with `rescore.py`. |
| `eval-v8.sh` | Runs `tools/evaluate.py` on dataset v8 with the v8 students (`two_stage`, 640, 960). |
| `eval-v8n.sh` | Chooses model and cut-off with the 13 never-trained days as validation footage; test stays 12 Nov. |
| `eval-v9.sh` | Official selection for the 38-day models: exports `v9_960_e8` and `v9_640_e8`, runs `tools/evaluate.py` on dataset v8n with `--promote`. |
| `exam-more.sh` | Scores more models on the 5 exam days and the 13 selection days with `evo_one.py --score-only`. |
| `exam-more2.sh` | The same for the finished size tests, on the exam days and 12 Nov. |
| `fail.py` | Where does a student still fail on the held-out frames: groups every label (hit, wrong, not seen, ...) and false alarms, writes sheets. |
| `fail2.py` | Redraws the failure tiles with every label box and model box and counts double labels. |
| `falsesq.py` | How often a student names a squirrel on the held-out day, which has none. |
| `history.sh` | Measures every model trained that day on the same held-out frames and the newest labels. |
| `history2.sh` | A later version of `history.sh`. |
| `history3.sh` | Another version, against dataset v5, at lowest priority. |
| `rescore.py` | Scores a student on the held-out frames twice: against the labels as they are and with double and oversized label boxes handled. Reviewed copy: `tools/label_check/rescore.py` (identical). |
| `rescore_t.py` | `rescore.py` with an optional two-tile mode (`TILES` environment variable). |
| `run-eval-quick.sh` | Measures the quick first model on the held-out day when its training ends. |
| `run-eval-v8b.sh` | Waits for `run-fit.sh` to finish, then runs `eval-v8.sh`. |
| `run-fail.sh` | Runs `fail.py` for the v4 students. |
| `run-k.sh` | Runs `rescore.py` for v4 and v5 on dataset v5k, three at a time. |
| `run-rescore.sh` | Runs `rescore.py` for v4 and v5 at 640 and 960 on dataset v5. |
| `run-tiles.sh` | Runs `rescore_t.py` with two tiles for the v4 students. |
| `score-snap.sh` | Snapshots each v9 run's latest weights and scores them on the exam days, 12 Nov and the selection days. |
| `unid.py` | Counts how many predictions of a new and an old 640 student are `unidentified`. Not documented further. |
| `valsq.py` | Per-species counts on the val split at one threshold (squirrel, tits, jay, ...). Not documented further. |
| `valsweep.py` | Sweeps thresholds from 0.25 to 0.60 on val and test for one student. Not documented further. |
| `whymiss.py` | For detections on the held-out day with no label box: was there a teacher box, and what became of it? |
| `whyunid.py` | Splits the student's `unidentified` detections on the held-out day by cause. |

## machines/

| File | What it does |
| --- | --- |
| `copy-to-store.sh` | Copies everything the project needs (footage, frames, labels, datasets, models) to a store machine on another account. |
| `fast-setup.sh` | On the fast machine: installs tools, syncs the Python environment, waits for the dataset, trains teacher 2. |
| `free-g13.sh` | Stops the automatically started training on one machine so it is free for footage processing. |
| `grab.sh` | On the laptop: polls the spare cloud accounts and rents every usable GPU machine offered (spot first, then on demand), with the `verda` command line tool; calls `setup-machine.sh`. |
| `guard-spare.sh` | On the laptop: deletes all rented machines of an account when its balance is at or under a limit. |
| `kill-history.sh` | Stops the accuracy-history run. |
| `kill-left.sh` | Stops decoder workers a stopped miner left behind. |
| `kill-mine.sh` | Stops the extra-days worker chain and its miner (training is not touched). |
| `kill-push-g1.sh` | Stops a running `push-to.sh` and its rsync to one machine. |
| `kill-train5.sh` | Stops the waiting last-round launcher so it can be re-armed with other epoch counts. |
| `kill-w8.sh` | Stops a waiting worker chain; downloads are left alone. |
| `nice-history.sh` | Gives the accuracy-history run the lowest priority. |
| `pull-best.sh` | Every 2 minutes copies each evolution run's log, state and best weights to the main machine. |
| `pull-once.sh` | One round of `pull-best.sh`. |
| `pull-sweep.sh` | Loop that copies the size-test scores and weights of the machines listed in a file. |
| `push-check.sh` | Main machine to the check machine: code, environment, weights and the 25-day part of dataset v5. |
| `push-evo.sh` | Sends code, seed weights, dataset v8 and the exam and fitness sets to a machine for the evolution run. |
| `push-evo2.sh` | The same for a second machine, with a few changes. |
| `push-proc.sh` | Gives a machine what it needs to label new footage (checker environment and model, teachers, vote students). |
| `push-to.sh` | Pushes code, environment, checked training set, fitness and exam sets and seed weights to a new machine. |
| `push-v2a.sh` | Sends dataset v2a to the training machine and marks it ready. |
| `push-x2.sh` | Sends the unchecked training frames of the 13 selection days and the checking assets to the 8-GPU machine. |
| `save-round2.sh` | Saves what only exists on the rented machines (datasets, verdicts, weights, logs) to the store machine and to the laptop. |
| `setup-machine.sh` | On the laptop: brings one freshly rented machine to a running job (waits for boot, adds keys, pushes data, starts a size test or an evolution run). |
| `slim-g19.sh` | Drops big training images on a machine that only processes footage to make room for videos. |
| `start-pull-sweep.sh` | Starts `pull-sweep.sh` in the background. |
| `status.sh` | On the laptop: what is rented on which account, with balances and the latest job lines. |
| `stop-ds-g19.sh` | Stops sending the big training set to one machine whose disk is needed for videos. |

## board/

| File | What it does |
| --- | --- |
| `board-watch.py` | Watches the Arduino's demo page through a tunnel and prints every change of latch state, pests and errors, with a summary. |
