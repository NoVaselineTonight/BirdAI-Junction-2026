---
title: "Compute plan: Verda and Modal"
subtitle: "Where we train and label the Feeder Census model, and what it costs"
date: "14 November 2026"
---

# In one sentence

We use Verda as our hands-on GPU workstation for labelling and day-to-day training, and Modal for runs we start and leave alone: parameter sweeps, the final training run and evaluation.

# Budget

| Service | Credit | Billing | Expected use |
|---|---|---|---|
| Verda (formerly DataCrunch, Helsinki) | 200 € | Per 10 minutes while the machine is running | Most of the work |
| Modal | 100 $ | Per second, only while a job runs | Sweeps, final run, evaluation, backup |

Either budget alone is far more than we need. The whole project should use roughly 5–15 GPU-hours, about 10–30 € in total.

# Where we use Verda

One rented GPU machine (an L40S or A100-class card is enough), used like a workstation.

1. **Pre-labelling.** Run a large open-vocabulary detector (for example Grounding DINO or YOLO-World) over the feeder frames to draw rough "bird" boxes. People then fix boxes and set the species, instead of drawing every box by hand.
2. **Hands-on training.** Keep the dataset on the machine, train the nano detector, look at its mistakes (especially tree sparrow vs house sparrow), fix labels and retrain.
3. **Looking at results.** Jupyter on the machine, for browsing images, predictions and confusion matrices.

**Why Verda here:** this work is interactive, and the data needs to stay in one place between sessions. A machine we log into suits that better than one-off jobs. It is also a Finnish provider with datacentres in Finland and Iceland, which fits a Finnish open-data project.

**Rule:** stop the instance whenever nobody is using it. It bills for as long as it runs.

# Where we use Modal

Python scripts started from a laptop. Modal starts a GPU, runs the job and stops.

1. **Parameter sweeps.** Try several input sizes, model sizes and training lengths at the same time, then pick the most accurate model that is still fast enough on the UNO Q.
2. **The final training run.** One script that rebuilds the model we put on the board from the labelled dataset, so the result can be reproduced.
3. **Export.** Convert the chosen model to int8 (TFLite or ONNX) for the UNO Q.
4. **Evaluation.** Run the model on held-out footage it was never trained on, so the demo numbers are honest.
5. **Backup.** If Verda has no capacity for the GPU we want, the same training script runs on Modal.

**Why Modal here:** these jobs are scripted and can run in parallel. Per-second billing means no paying for idle time.

**Rule:** Modal can interrupt and restart a GPU job, so training saves a checkpoint every epoch to a Modal Volume and resumes from it.

# How long things take

Ballpark figures, not measurements.

| Job | Assumptions | Time on one L40S/A100-class GPU |
|---|---|---|
| Pre-labelling | ~10,000 frames | 20–40 min |
| One training run | Nano detector, ~3,000 images, 640 px, ~100 epochs | 15–45 min |
| Sweep of 8–10 variants | Run in parallel on Modal | About the same as one run |
| Export and check | int8, held-out footage | A few minutes |

One full loop (train, check errors, fix labels, retrain) is about an hour of GPU time. If a run is much slower than this, cache the images in RAM (`cache=True` in Ultralytics) before renting a bigger GPU. The small model size, or more images, takes about 2–3× longer.

# The real bottleneck

Labelling, not compute. Correcting 3,000 images is likely to take one or two people a day or more, even with pre-labels. So:

- Start labelling early.
- Train a first model after a few hundred images to test the whole pipeline end to end, as planned in the sketch's next steps.

# Workflow at a glance

| Step | Where |
|---|---|
| Collect feeder footage, extract frames | Laptop or Verda |
| Pre-label frames | Verda |
| Fix boxes and species | Labelling tool, by people |
| First training runs and error checks | Verda |
| Sweeps | Modal |
| Final training run and int8 export | Modal |
| Evaluation on held-out footage | Modal |
| Run the model live | UNO Q, no cloud |

# What has been checked

- **From provider pages and price trackers (November 2026):** Verda is the former DataCrunch, based in Helsinki, bills pay-as-you-go in 10-minute steps and offers spot instances at 50% of the dynamic price. Modal bills per second, has a free tier with monthly credits, and can interrupt GPU jobs.
- **Our own estimates, unchecked:** all training times, GPU-hours and total cost. Replace them with real numbers after the first run.
