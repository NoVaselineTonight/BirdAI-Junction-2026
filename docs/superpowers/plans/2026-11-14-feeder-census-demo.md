# Feeder Census Demo Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** A working Feeder Census demo by midnight on 14 November 2026: recorded feeder video stands in for the camera, a small on-device detector names and counts each bird, and a local web page shows the live feed, the "largest number at once" counts per hour, day and half-month, the logged watching hours, evidence photos and a CSV in the monitoring-form shape. It runs on the laptop first, then on the Arduino UNO Q.

**Architecture:** One Python package, `feeder_census`, runs unchanged on laptop and board: simulated camera → `Detector` → counting rule → SQLite → FastAPI page. Two detectors sit behind one protocol. The *pretrained two-stage* detector (YOLOX-nano draws bird boxes, Google's iNaturalist bird classifier names each crop) needs no training and exists from Task 3. The *student* detector is a single-stage nano model trained tonight on footage that larger teacher models label automatically (Tasks 7–9). Task 9 measures both on held-out footage and ships the better one.

**Tech Stack:** Python 3.12 (laptop) and 3.13 (board), uv, numpy, opencv-python-headless, onnxruntime, ai-edge-litert, FastAPI, uvicorn, SQLite, pytest. For labelling and training only, on a rented Verda GPU machine: ultralytics, pybioclip, torch. Modal is the backup for training.

**Spec:** `feeder-census-sketch.md` (what the device does, demo plan, honesty rules), `arduino-uno-q-spec-sheet.md` (board limits) and `compute-plan-verda-modal.md` (where labelling and training run). Read all three. The repo is `NoVaselineTonight/BirdAI-Junction-2026` (formerly `challenge-3`); every path below is relative to its root.

## Global Constraints

From the spec, verbatim where it gives a value:

- **Counting rule:** "the largest number of each species seen at once. Only surely identified species." Counts are never summed across frames, hours or days.
- **Effort:** "Logs how long it was actually watching, so a zero is a real zero." An hour that was not watched has no row. It is never shown as 0.
- **Evidence:** "Saves one photo with each record." A record is one species on one day.
- **Periods:** half-month, days 1–15 and 16–end of month.
- **Object detector, not a whole-frame classifier.** Every count comes from boxes.
- **On the device, no cloud.** The runtime makes no network call. Models and video are local files.
- **Board limits:** CPU only (no NPU), about 1.3 GB RAM free, 3.0 GB disk free. Store the best frame per record, never continuous video.
- **Honesty:** the page says the footage is recorded. Demo footage is never training footage. The page shows accuracy measured on unseen footage. Nothing claims to beat a skilled volunteer.
- **Rights:** footage belongs to its uploaders. `data/` and `models/` are git-ignored, and frames are never published or committed. Copying footage to our own Verda machine or Modal volume for training is allowed; delete it there when the machine is given up.
- **Finnish focus (from the team, 14 Nov):** the species list is Finnish winter feeder birds, every species carries its Finnish name, training and demo footage should come from Finnish or other Nordic feeders, and the page shows the species mix by habitat. That grouping is "our own proposal and needs checking against how Luomus groups them" (sketch), and the page says so. One feeder is one data point; nothing on the page claims to measure an ecosystem.
- **Repo protocol:** `AGENTS.md` is enforced by git hooks. Before creating or editing a file, claim it: `python3 .agents/agentchat.py claim <paths> --task "..."`. Each task's **Files** list is its claim list. Work continues on branch `birdai-plan/feeder-census-demo` under the agent name `birdai-plan`; a different agent needs its own name from a human and its own `<name>/<task>` branch, started from a branch that contains this plan. Never push to `main`.
- **Licence:** the student is trained with Ultralytics, which is AGPL-3.0 and whose licence covers trained weights. If the repo is published it must be AGPL-compatible. The pretrained two-stage detector is Apache-2.0 throughout.
- **Compute:** labelling and training run on one Verda GPU machine (`compute-plan-verda-modal.md`). Stop the instance when nobody is using it. The laptop has no usable GPU.

Decisions this plan makes where the spec is silent:

- **Demo clock.** Footage is minutes long and the rule works in hours and half-months, so time is simulated: 1 second of footage = 1 simulated minute (`time_scale = 60`), daylight only (08:00–16:00), starting 1 November 2026. The page states this.
- **Sure identification** = detection confidence ≥ `count_threshold` (0.60 for the pretrained detector; measured in Task 9 for the student). Birds below it are drawn as "unidentified" and not counted.
- **Confirmation.** A count must hold in 2 consecutive detection frames (`confirm_frames = 2`), because a maximum is the statistic one false frame can corrupt.
- **Detection cadence:** one frame every 2.0 s of footage (`detect_every_s`). The preview runs at 5 fps.
- **Runtime imports** are limited to the standard library, numpy, cv2, onnxruntime, ai_edge_litert, fastapi and uvicorn. No torch or ultralytics in `feeder_census/`.
- **Board route:** plain Python in a uv venv under `/home/arduino/feeder-census`, reached from the laptop with `adb forward`. Not an App Lab app: the board's App Lab runtime is a 2025 build (App CLI v0.1.12).
- **Port 8088** (free in `~/.claude/Global information/local-dev-environment.md`).
- **Species** come from `species.toml`. The eight "core" species are the sketch's list. A table column appears only for a species the active detector can name.

## Review Focus

Inputs the spec implies and a person at the demo will hit. Each has a test in the task that owns the code.

1. **One false frame.** A single frame with a wrong or doubled detection must not become the hour's, day's or period's maximum. → Task 1 `test_single_frame_spike_is_not_counted`.
2. **One bird, two boxes.** Overlapping boxes on one bird (same or different species) must count as one bird. → Task 3 `test_nms_keeps_one_box_per_bird`, Task 8 `test_student_never_gives_one_bird_two_species`.
3. **Zero versus not watched.** An empty feeder for a watched hour is a row of zeros; an unwatched hour and a species the model cannot name are blank, not 0. → Task 2 `test_zero_is_recorded_only_for_watched_hours`, Task 5 `test_tables_hide_species_the_detector_cannot_name`.
4. **Restart mid-demo.** Stopping and starting must keep counts and hours, continue the clock, and not double-count effort. → Task 2 `test_reopen_keeps_counts_and_effort`, Task 4 `test_pipeline_resumes_clock_after_restart`.
5. **Slow board.** When detection takes longer than the interval, frames are dropped, not queued, and a stall is not logged as watching. → Task 4 `test_slow_detector_drops_frames_and_caps_effort`.

---

### Task 1: Scaffold and counting core

**Files:**
- Create: `pyproject.toml`, `.gitignore`, `species.toml`
- Create: `feeder_census/__init__.py`, `feeder_census/types.py`, `feeder_census/species.py`, `feeder_census/periods.py`, `feeder_census/census.py`
- Test: `tests/test_species.py`, `tests/test_periods.py`, `tests/test_census.py`

**Interfaces:**
- Produces:
  - `types.UNIDENTIFIED = "unidentified"`
  - `types.Detection(species: str, confidence: float, box: tuple[float, float, float, float])`, frozen dataclass. `box` is `x1, y1, x2, y2` in source-frame pixels.
  - `species.Species(key, scientific, english, finnish, habitat, core: bool, aliases: tuple[str, ...])`, frozen dataclass; `habitat` is one of `species.HABITATS = ("forest", "farmland", "town", "generalist")`
  - `species.load_species(path: Path | None = None) -> list[Species]` (default: `species.toml` beside the package's parent)
  - `species.habitat_mix(counts: Mapping[str, int], species: Sequence[Species]) -> dict[str, int]` — birds per habitat, every habitat present, keys of `counts` that are not in `species` ignored
  - `periods.Period(start: date, end: date)`, frozen, with `.key` (`"2026-11-A"` / `"2026-11-B"`) and `.label` (`"1–15 November 2026"`, en dash)
  - `periods.period_of(d: date) -> Period`, `periods.period_from_key(key: str) -> Period`
  - `census.frame_counts(detections: Iterable[Detection], threshold: float) -> dict[str, int]`
  - `census.ConfirmFilter(species: Sequence[str], confirm_frames: int = 2)` with `.update(counts: Mapping[str, int]) -> dict[str, int]` and `.reset() -> None`

- [ ] **Step 1: Claim the files and set up the project**

Run `python3 .agents/agentchat.py status`, then claim `pyproject.toml uv.lock .gitignore species.toml README.md feeder_census/ tests/ tools/ board/` in one claim for the whole plan. `pyproject.toml`: project `feeder-census`, `requires-python = ">=3.12"`, dependencies `numpy`, `opencv-python-headless`, `onnxruntime`, `ai-edge-litert`, `fastapi`, `uvicorn`; dependency group `dev` = `pytest`, `httpx`; dependency group `train` = `ultralytics`, `pybioclip`, `pillow`, `onnx`, `onnxslim`; pytest marker `models` ("needs downloaded model files"). `.gitignore`: `data/`, `models/`, `build/`, `.venv/`, `__pycache__/`.

`species.toml` holds one `[[species]]` table per row, in this order (`aliases` only where given; they are older names used by label files). The eight core species are the sketch's list. The habitat column is the team's own grouping, unchecked:

| key | scientific | english | finnish | habitat | core | aliases |
|---|---|---|---|---|---|---|
| great_tit | Parus major | Great tit | Talitiainen | generalist | true | |
| yellowhammer | Emberiza citrinella | Yellowhammer | Keltasirkku | farmland | true | |
| blue_tit | Cyanistes caeruleus | Blue tit | Sinitiainen | generalist | true | Parus caeruleus |
| tree_sparrow | Passer montanus | Tree sparrow | Pikkuvarpunen | farmland | true | |
| bullfinch | Pyrrhula pyrrhula | Bullfinch | Punatulkku | forest | true | |
| blackbird | Turdus merula | Blackbird | Mustarastas | generalist | true | |
| greenfinch | Chloris chloris | Greenfinch | Viherpeippo | generalist | true | Carduelis chloris |
| house_sparrow | Passer domesticus | House sparrow | Varpunen | town | true | |
| willow_tit | Poecile montanus | Willow tit | Hömötiainen | forest | false | Parus montanus |
| coal_tit | Periparus ater | Coal tit | Kuusitiainen | forest | false | Parus ater |
| crested_tit | Lophophanes cristatus | Crested tit | Töyhtötiainen | forest | false | Parus cristatus |
| nuthatch | Sitta europaea | Nuthatch | Pähkinänakkeli | forest | false | |
| great_spotted_woodpecker | Dendrocopos major | Great spotted woodpecker | Käpytikka | forest | false | |
| magpie | Pica pica | Magpie | Harakka | town | false | |
| jay | Garrulus glandarius | Jay | Närhi | forest | false | |
| siskin | Spinus spinus | Siskin | Vihervarpunen | forest | false | Carduelis spinus |
| redpoll | Acanthis flammea | Redpoll | Urpiainen | forest | false | Carduelis flammea |
| chaffinch | Fringilla coelebs | Chaffinch | Peippo | generalist | false | |
| robin | Erithacus rubecula | Robin | Punarinta | generalist | false | |
| fieldfare | Turdus pilaris | Fieldfare | Räkättirastas | generalist | false | |
| jackdaw | Coloeus monedula | Jackdaw | Naakka | town | false | Corvus monedula |
| feral_pigeon | Columba livia | Feral pigeon | Kesykyyhky | town | false | |

- [ ] **Step 2: Write the failing tests**

```python
# tests/test_species.py
def test_core_species_are_the_sketch_eight():
    sp = load_species()
    assert [s.key for s in sp if s.core] == [
        "great_tit", "yellowhammer", "blue_tit", "tree_sparrow",
        "bullfinch", "blackbird", "greenfinch", "house_sparrow"]
    assert len({s.key for s in sp}) == len(sp) == 22
    assert all(s.finnish and s.habitat in HABITATS for s in sp)

def test_habitat_mix_adds_birds_per_habitat():
    mix = habitat_mix({"willow_tit": 2, "bullfinch": 3, "house_sparrow": 4, "great_tit": 5}, load_species())
    assert mix == {"forest": 5, "farmland": 0, "town": 4, "generalist": 5}

# tests/test_periods.py
def test_half_month_boundaries():
    assert period_of(date(2026, 11, 15)).key == "2026-11-A"
    assert period_of(date(2026, 11, 16)).key == "2026-11-B"
    assert period_of(date(2026, 11, 16)).end == date(2026, 11, 30)
    assert period_of(date(2027, 2, 20)).end == date(2027, 2, 28)
    assert period_of(date(2028, 2, 20)).end == date(2028, 2, 29)

def test_labels_match_the_monitoring_form():
    assert period_of(date(2026, 11, 1)).label == "1–15 November 2026"
    assert period_of(date(2026, 12, 31)).label == "16–31 December 2026"

def test_key_round_trip():
    assert period_from_key("2026-11-B") == period_of(date(2026, 11, 20))

# tests/test_census.py
def D(species, conf): return Detection(species, conf, (0, 0, 10, 10))

def test_frame_counts_only_sure_identifications():
    dets = [D("great_tit", 0.9), D("great_tit", 0.59), D("blue_tit", 0.6), D("unidentified", 0.99)]
    assert frame_counts(dets, threshold=0.6) == {"great_tit": 1, "blue_tit": 1}

def test_single_frame_spike_is_not_counted():
    f = ConfirmFilter(["great_tit", "blue_tit"], confirm_frames=2)
    assert f.update({"great_tit": 2}) == {"great_tit": 0, "blue_tit": 0}
    assert f.update({"great_tit": 5}) == {"great_tit": 2, "blue_tit": 0}
    assert f.update({"great_tit": 1}) == {"great_tit": 1, "blue_tit": 0}

def test_reset_forgets_earlier_frames():
    f = ConfirmFilter(["great_tit"], confirm_frames=2)
    f.update({"great_tit": 3}); f.reset()
    assert f.update({"great_tit": 3}) == {"great_tit": 0}

def test_confirm_frames_one_passes_counts_through():
    assert ConfirmFilter(["great_tit"], confirm_frames=1).update({"great_tit": 4}) == {"great_tit": 4}
```

- [ ] **Step 3: Run them and see them fail**

Run: `uv run pytest tests/test_species.py tests/test_periods.py tests/test_census.py -q`
Expected: FAIL, `ModuleNotFoundError: feeder_census`.

- [ ] **Step 4: Implement the five modules**

`ConfirmFilter.update` returns, for every species it was built with, the minimum of that species' count over the last `confirm_frames` calls (a species missing from `counts` is 0), and 0 until that many calls have been made.

- [ ] **Step 5: Run the tests and see them pass**

Run: `uv run pytest -q` — Expected: all pass.

- [ ] **Step 6: Commit**

`git add -A && git commit -m "feat: project scaffold, species list, period maths and counting rule"`

---

### Task 2: Store, roll-ups and form-shaped export

**Files:**
- Create: `feeder_census/store.py`
- Test: `tests/test_store.py`

**Interfaces:**
- Consumes: `Period`, `period_of` (Task 1).
- Produces:
  - `store.SpeciesMismatch(Exception)`
  - `store.CountRow(key: str, label: str, hours_watched: float, counts: dict[str, int])`, frozen
  - `store.EvidenceRow(day: date, species: str, count: int, confidence: float, ts: datetime, image: str)`, frozen
  - `store.Store(path: Path | str, species: Sequence[str])` — `":memory:"` allowed; safe to call from several threads
    - `.species: tuple[str, ...]`
    - `.record(ts: datetime, counts: Mapping[str, int], watched_s: float) -> set[str]` — returns the species whose **day** maximum just rose
    - `.set_evidence(ts: datetime, species: str, count: int, confidence: float, image: str) -> None`
    - `.total_watched_s() -> float`
    - `.hours(day: date) -> list[CountRow]` (key `"09"`, label `"09–10"`)
    - `.days(period: Period) -> list[CountRow]` (key `"2026-11-03"`, label `"3 Nov"`)
    - `.periods() -> list[CountRow]` (key and label from `Period`)
    - `.evidence() -> list[EvidenceRow]`
    - `.export_csv(out: TextIO, names: Mapping[str, str]) -> None`

Schema: `meta(key, value)`; `hour_counts(day, hour, species, max_count)` keyed on the first three; `effort(day, hour, watched_s)`; `evidence(day, species, count, confidence, ts, image)` keyed on day and species. `ts` values are naive local datetimes (the simulated clock).

- [ ] **Step 1: Write the failing tests**

```python
def dt(*a): return datetime(*a)

@pytest.fixture
def s(): return Store(":memory:", ["great_tit", "blue_tit"])

def test_rollup_is_largest_at_once_not_a_sum(s):
    s.record(dt(2026, 11, 3, 9, 10), {"great_tit": 3, "blue_tit": 0}, 120)
    s.record(dt(2026, 11, 3, 9, 40), {"great_tit": 2, "blue_tit": 1}, 120)
    s.record(dt(2026, 11, 3, 13, 0), {"great_tit": 5, "blue_tit": 0}, 120)
    s.record(dt(2026, 11, 9, 10, 0), {"great_tit": 4, "blue_tit": 2}, 120)
    s.record(dt(2026, 11, 16, 10, 0), {"great_tit": 1, "blue_tit": 0}, 120)
    assert [(r.key, r.counts) for r in s.hours(date(2026, 11, 3))] == [
        ("09", {"great_tit": 3, "blue_tit": 1}), ("13", {"great_tit": 5, "blue_tit": 0})]
    assert [r.counts["great_tit"] for r in s.days(period_of(date(2026, 11, 3)))] == [5, 4]
    a, b = s.periods()
    assert (a.key, a.label, a.counts) == ("2026-11-A", "1–15 November 2026", {"great_tit": 5, "blue_tit": 2})
    assert a.hours_watched == pytest.approx(480 / 3600)
    assert b.counts == {"great_tit": 1, "blue_tit": 0}

def test_zero_is_recorded_only_for_watched_hours(s):
    s.record(dt(2026, 11, 3, 9, 0), {}, 120)
    (row,) = s.hours(date(2026, 11, 3))
    assert row.counts == {"great_tit": 0, "blue_tit": 0} and row.hours_watched > 0
    assert s.hours(date(2026, 11, 4)) == []

def test_record_returns_species_with_a_new_day_maximum(s):
    assert s.record(dt(2026, 11, 3, 9, 0), {"great_tit": 2}, 2) == {"great_tit"}
    assert s.record(dt(2026, 11, 3, 9, 1), {"great_tit": 2}, 2) == set()
    assert s.record(dt(2026, 11, 3, 14, 0), {"great_tit": 3, "blue_tit": 1}, 2) == {"great_tit", "blue_tit"}
    assert s.record(dt(2026, 11, 4, 9, 0), {"great_tit": 1}, 2) == {"great_tit"}

def test_evidence_keeps_one_photo_per_day_and_species(s):
    s.set_evidence(dt(2026, 11, 3, 9, 0), "great_tit", 2, 0.81, "2026-11-03/great_tit.jpg")
    s.set_evidence(dt(2026, 11, 3, 14, 0), "great_tit", 3, 0.90, "2026-11-03/great_tit.jpg")
    (e,) = s.evidence()
    assert (e.count, e.confidence, e.ts) == (3, 0.90, dt(2026, 11, 3, 14, 0))

def test_reopen_keeps_counts_and_effort(tmp_path):
    p = tmp_path / "c.db"
    Store(p, ["great_tit"]).record(dt(2026, 11, 3, 9, 0), {"great_tit": 2}, 120)
    again = Store(p, ["great_tit"])
    assert again.total_watched_s() == 120 and again.periods()[0].counts == {"great_tit": 2}

def test_reopen_with_another_species_list_is_refused(tmp_path):
    p = tmp_path / "c.db"; Store(p, ["great_tit"])
    with pytest.raises(SpeciesMismatch, match="great_tit"):
        Store(p, ["great_tit", "blue_tit"])

def test_csv_has_the_form_shape(s):
    s.record(dt(2026, 11, 3, 9, 0), {"great_tit": 5, "blue_tit": 2}, 360)
    out = io.StringIO(); s.export_csv(out, {"great_tit": "Great tit", "blue_tit": "Blue tit"})
    assert out.getvalue().splitlines() == [
        "Period,Hours watched,Great tit,Blue tit", "1–15 November 2026,0.1,5,2"]
```

- [ ] **Step 2: Run them and see them fail**

Run: `uv run pytest tests/test_store.py -q` — Expected: FAIL, `ModuleNotFoundError`.

- [ ] **Step 3: Implement `Store`**

`record` writes a row for **every** species in `self.species` (count 0 when absent from `counts`), keeps the larger of old and new, and adds `watched_s` to the hour's effort. Roll-ups are `MAX` over hours, then days. A species counts as "new day maximum" only when its count is above 0 and above the day's previous maximum. Hours watched in the CSV have one decimal. `SpeciesMismatch` names both species lists and tells the user to pass another `--db` path.

- [ ] **Step 4: Run the tests and see them pass**

Run: `uv run pytest tests/test_store.py -q` — Expected: all pass.

- [ ] **Step 5: Commit**

`git add -A && git commit -m "feat: SQLite store with largest-at-once roll-ups, effort and CSV export"`

---

### Task 3: Detection core and the pretrained two-stage detector

**Files:**
- Create: `feeder_census/detectors/__init__.py`, `base.py`, `yolox.py`, `inat.py`, `two_stage.py`, `scripted.py` (all under `feeder_census/detectors/`)
- Create: `feeder_census/bench.py`, `tools/fetch_models.py`
- Test: `tests/test_detectors.py`

**Interfaces:**
- Consumes: `Detection`, `UNIDENTIFIED`, `Species` (Task 1).
- Produces:
  - `base.Detector` (Protocol): `name: str`, `species: tuple[str, ...]` (keys it can name, never `UNIDENTIFIED`), `count_threshold: float`, `detect(frame_bgr: np.ndarray) -> list[Detection]`
  - `base.letterbox(image: np.ndarray, size: int, center: bool, pad_value: int = 114) -> tuple[np.ndarray, float, tuple[int, int]]` — returns the `size × size` image, the resize ratio and the `(dx, dy)` padding offset (`(0, 0)` when `center=False`)
  - `base.nms(boxes: np.ndarray, scores: np.ndarray, iou: float) -> list[int]` — class-agnostic, returns kept indices, highest score first
  - `yolox.decode_yolox(output: np.ndarray, size: int, class_id: int) -> tuple[np.ndarray, np.ndarray]` — `(boxes_xyxy, scores)` in letterboxed pixels
  - `yolox.YoloxBoxes(model: Path, score_threshold: float = 0.30, nms_iou: float = 0.45, class_id: int = 14)` with `.boxes(frame_bgr) -> list[tuple[tuple[float, float, float, float], float]]` in source-frame pixels
  - `inat.InatClassifier(model: Path, labels: Path)` with `.classify(crop_bgr) -> tuple[str, float]` (scientific name, probability of the top class; `("background", p)` is possible)
  - `two_stage.TwoStageDetector(boxes, classifier, species: Sequence[Species], pad: float = 0.10)` — `name = "pretrained two-stage"`, `count_threshold = 0.60`
  - `scripted.ScriptedDetector(script: Path | dict)` — JSON `{"species": [...], "frames": [[{"species", "confidence", "box"}, ...], ...]}`, one inner list per `detect` call, cycling
  - `detectors.build_detector(kind: str, models_dir: Path, species: Sequence[Species], script: Path | None = None) -> Detector` for `kind` in `"two_stage"`, `"student"` (Task 8), `"scripted"`
  - `python -m feeder_census.bench --detector KIND --video PATH [--frames 30]` prints `median_ms`, `p90_ms`, `birds_per_frame`
  - `python tools/fetch_models.py` fills `models/pretrained/`

Model files (links checked 14 Nov 2026, all Apache-2.0 repos):

| File in `models/pretrained/` | URL | Bytes |
|---|---|---|
| `yolox_nano.onnx` | `https://github.com/Megvii-BaseDetection/YOLOX/releases/download/0.1.1rc0/yolox_nano.onnx` | 3659407 |
| `inat_bird.tflite` | `https://raw.githubusercontent.com/google-coral/test_data/master/mobilenet_v2_1.0_224_inat_bird_quant.tflite` | 3579500 |
| `inat_bird_labels.txt` | `https://raw.githubusercontent.com/google-coral/test_data/master/inat_bird_labels.txt` | 37146 |

Facts the code depends on:

- **YOLOX-nano:** input `images`, `[1, 3, 416, 416]` float32, BGR, values 0–255, no mean or std, letterbox anchored top-left with pad 114. Output `[1, 3549, 85]`: rows are the 52², 26², 13² grids (strides 8, 16, 32) in that order; columns are `cx, cy, w, h, objectness, 80 class scores`. Objectness and class scores are already sigmoided. Decode: `xy = (xy + grid) * stride`, `wh = exp(wh) * stride`, `score = objectness * class[class_id]`. COCO `bird` is class 14.
- **iNat classifier:** input `[1, 224, 224, 3]` uint8, RGB, raw 0–255. Output `[1, 965]` uint8; probability = value / 256. `inat_bird_labels.txt` has one label per line, line index = class id, format `Scientific name (Common name)`; the last line is `background`. Run it with `ai_edge_litert.interpreter.Interpreter`.
- **Two-stage rule:** crop each box grown by `pad` on every side (clamped to the frame) and classify it. If the top class is a species in `species.toml` (by `scientific` or an alias) the detection is that species with the classifier's probability; otherwise it is `UNIDENTIFIED` with that probability. `species` lists only the keys found in the label file.

- [ ] **Step 1: Write the failing tests**

```python
def test_decode_yolox_maps_a_grid_cell_to_pixels():
    out = np.zeros((1, 3549, 85), np.float32)
    out[0, 0, :4] = [0.5, 0.5, np.log(4), np.log(2)]   # first cell of the stride-8 grid
    out[0, 0, 4] = 0.9; out[0, 0, 5 + 14] = 0.8
    boxes, scores = decode_yolox(out, size=416, class_id=14)
    assert boxes[0] == pytest.approx([-12, -4, 20, 12]) and scores[0] == pytest.approx(0.72)

def test_nms_keeps_one_box_per_bird():
    boxes = np.array([[0, 0, 100, 100], [5, 5, 105, 105], [200, 200, 260, 260]], np.float32)
    assert nms(boxes, np.array([0.9, 0.8, 0.7]), iou=0.45) == [0, 2]

def test_letterbox_round_trip():
    img = np.zeros((1080, 1920, 3), np.uint8)
    out, ratio, (dx, dy) = letterbox(img, 416, center=False)
    assert out.shape == (416, 416, 3) and ratio == pytest.approx(416 / 1920) and (dx, dy) == (0, 0)
    _, ratio_c, (dx, dy) = letterbox(img, 640, center=True)
    assert (dx, dy) == (0, 140) and ratio_c == pytest.approx(640 / 1920)

def test_two_stage_names_listed_species_and_flags_the_rest(species):
    boxes = Fake(boxes=[((10, 10, 60, 60), 0.9), ((100, 100, 150, 150), 0.8)])
    clf = Fake(classify=[("Parus major", 0.91), ("Poecile atricapillus", 0.80)])
    dets = TwoStageDetector(boxes, clf, species).detect(np.zeros((200, 200, 3), np.uint8))
    assert [(d.species, d.confidence) for d in dets] == [("great_tit", 0.91), ("unidentified", 0.80)]
    assert dets[0].box == (10, 10, 60, 60)

def test_two_stage_resolves_old_names_through_aliases(species):
    clf = Fake(classify=[("Carduelis spinus", 0.7)])
    (d,) = TwoStageDetector(Fake(boxes=[((0, 0, 9, 9), 0.9)]), clf, species).detect(np.zeros((20, 20, 3), np.uint8))
    assert d.species == "siskin"

def test_scripted_detector_cycles():
    d = ScriptedDetector({"species": ["great_tit"], "frames": [[], [{"species": "great_tit", "confidence": 0.9, "box": [0, 0, 5, 5]}]]})
    assert [len(d.detect(None)) for _ in range(3)] == [0, 1, 0]

@pytest.mark.models
def test_pretrained_models_load_and_know_the_core_species(species):
    det = build_detector("two_stage", Path("models"), species)
    assert {s.key for s in species if s.core} <= set(det.species)
    assert det.detect(np.full((720, 1280, 3), 114, np.uint8)) == []
```

(`species` is a fixture returning `load_species()`; `Fake` is a small test helper that returns the given values in order.)

- [ ] **Step 2: Run them and see them fail**

Run: `uv run pytest tests/test_detectors.py -q` — Expected: FAIL, `ModuleNotFoundError`.

- [ ] **Step 3: Implement the detectors, `fetch_models.py` and `bench.py`**

`fetch_models.py` downloads each file only if it is missing or its size differs from the table, and exits non-zero on a size mismatch after download. `build_detector` raises `FileNotFoundError` naming the missing model file and the command `python tools/fetch_models.py`.

- [ ] **Step 4: Fetch the models and run every test**

Run: `uv run python tools/fetch_models.py && uv run pytest -q`
Expected: all pass, including the `models` test (none skipped).

- [ ] **Step 5: Commit**

`git add -A && git commit -m "feat: detector protocol and pretrained two-stage bird detector"`

---

### Task 4: Simulated camera, clock, pipeline and command line

**Files:**
- Create: `feeder_census/config.py`, `feeder_census/camera.py`, `feeder_census/draw.py`, `feeder_census/pipeline.py`, `feeder_census/__main__.py`
- Test: `tests/conftest.py` (video fixture), `tests/test_camera.py`, `tests/test_pipeline.py`, `tests/data/demo_script.json` (a `ScriptedDetector` script: 20 frames with one to three great tits and blue tits)

**Interfaces:**
- Consumes: `Detector`, `ScriptedDetector` (Task 3); `Store` (Task 2); `frame_counts`, `ConfirmFilter` (Task 1).
- Produces:
  - `config.Settings` dataclass with defaults: `time_scale=60.0`, `detect_every_s=2.0`, `max_gap_s=10.0`, `confirm_frames=2`, `count_threshold: float | None = None` (None = use the detector's), `roi: tuple[float, float, float, float] | None = None` (x, y, w, h as fractions of the frame), `sim_start=date(2026, 11, 1)`, `evidence_dir=Path("data/evidence")`, `preview_fps=5.0`, `preview_width=960`, `port=8088`
  - `camera.SimClock(start: date, day_start: time = time(8), day_end: time = time(16))` with `.at(watched_s: float) -> datetime`
  - `camera.SimulatedCamera(paths: Sequence[Path], realtime: bool = True)` with `.read() -> tuple[np.ndarray, float]` (frame, footage seconds since start, growing across files and loops) and `.close()`
  - `draw.annotate(frame, detections, names: Mapping[str, str], threshold: float) -> np.ndarray`
  - `pipeline.LiveState(jpeg: bytes, sim_time: datetime, now: dict[str, int], confirmed: dict[str, int], unidentified: int, detect_ms: float, detector: str)`, frozen
  - `pipeline.Pipeline(camera, detector, store, settings, names: Mapping[str, str], inline: bool = False)` with `.step() -> None`, `.run(stop: threading.Event) -> None`, `.live() -> LiveState` and `.last_detections: list[Detection]` (full-frame coordinates)
  - `python -m feeder_census --videos PATH... --detector {two_stage,student,scripted} [--db data/census.db] [--port 8088] [--fast] [--no-web] [--roi x,y,w,h] [--script FILE]`

Behaviour to implement:

- **Clock.** `watched_s` is simulated watching time. Each day holds `day_end − day_start` of it; the rest rolls to the next day at `day_start`.
- **Camera.** A directory argument means its `*.mp4`, `*.mkv`, `*.mov`, `*.avi` files in name order. Files play in order and loop forever. With `realtime=True`, `read` sleeps so footage plays at its own frame rate, and when the caller is late it skips ahead to the frame that is due. A missing path raises `FileNotFoundError` with the path; a file OpenCV cannot decode raises `ValueError` with the file name.
- **Pipeline.** `step` reads one frame and updates the preview JPEG (at most `preview_fps`, scaled to `preview_width`, last detections drawn). When no detection is running and `detect_every_s` of footage has passed since the last one started, it starts one on a single worker thread (or runs it inline when `inline=True`). Frames arriving while a detection runs are not queued.
- **On each detection result:** crop to `roi` first and shift boxes back to full-frame coordinates; `counts = frame_counts(detections, threshold)`; `confirmed = ConfirmFilter.update(counts)`; credit `min(footage gap since the previous detection, max_gap_s) × time_scale` simulated seconds (the first detection credits `detect_every_s × time_scale`); `ts = clock.at(watched total)`, where the total starts from `store.total_watched_s()`; `store.record(ts, confirmed, credit)`. Reset the `ConfirmFilter` when the simulated date changes.
- **Evidence.** For each species `record` returns, save the annotated frame to `evidence_dir/<YYYY-MM-DD>/<species>.jpg` (JPEG quality 85, overwriting) and call `store.set_evidence` with the mean confidence of that species' counted detections.
- **`--fast`** sets `realtime=False`, for filling the table before a demo.

- [ ] **Step 1: Write the failing tests**

```python
# tests/conftest.py
@pytest.fixture
def make_video(tmp_path):
    def make(name="a.mp4", seconds=2.0, fps=10, size=(320, 240), value=60):
        ...  # cv2.VideoWriter, fourcc mp4v, solid frames of `value`
        return path
    return make

# tests/test_camera.py
def test_clock_skips_the_night():
    c = SimClock(date(2026, 11, 1))
    assert c.at(0) == datetime(2026, 11, 1, 8, 0)
    assert c.at(8 * 3600 - 1) == datetime(2026, 11, 1, 15, 59, 59)
    assert c.at(8 * 3600) == datetime(2026, 11, 2, 8, 0)
    assert c.at(15 * 8 * 3600) == datetime(2026, 11, 16, 8, 0)

def test_camera_loops_and_footage_time_keeps_growing(make_video):
    cam = SimulatedCamera([make_video(seconds=2.0, fps=10)], realtime=False)
    times = [cam.read()[1] for _ in range(45)]
    assert times == sorted(times) and len(set(times)) == 45 and times[-1] == pytest.approx(4.4, abs=0.15)

def test_camera_plays_files_in_name_order(make_video):
    make_video("b.mp4", value=200); a = make_video("a.mp4", value=20)
    frame, _ = SimulatedCamera([a.parent], realtime=False).read()
    assert frame.mean() < 100

def test_missing_video_names_the_path(tmp_path):
    with pytest.raises(FileNotFoundError, match="nope.mp4"):
        SimulatedCamera([tmp_path / "nope.mp4"])

def test_undecodable_video_names_the_file(tmp_path):
    bad = tmp_path / "bad.mp4"; bad.write_text("not a video")
    with pytest.raises(ValueError, match="bad.mp4"):
        SimulatedCamera([bad]).read()

def test_realtime_camera_skips_ahead_when_the_reader_is_late(make_video):
    cam = SimulatedCamera([make_video(seconds=2.0, fps=10)], realtime=True)
    cam.read(); time.sleep(0.5)
    assert cam.read()[1] >= 0.4

# tests/test_pipeline.py — helper build(tmp_path, make_video, frames, **settings) returns (pipeline, store)
# with ScriptedDetector(species=["great_tit", "blue_tit"]), realtime=False, inline=True, detect_every_s=2.0

GT = {"species": "great_tit", "confidence": 0.9, "box": [10, 10, 60, 60]}

def test_pipeline_records_the_confirmed_maximum_and_effort(...):
    p, store = build(frames=[[GT, GT], [GT, GT], [GT]])
    run_detections(p, 3)
    (hour,) = store.hours(date(2026, 11, 1))
    assert hour.counts == {"great_tit": 2, "blue_tit": 0}
    assert hour.hours_watched == pytest.approx(3 * 2.0 * 60 / 3600)

def test_pipeline_saves_one_evidence_photo_per_day_record(...):
    run_detections(p, 3)
    (e,) = store.evidence()
    assert (e.species, e.count, e.confidence) == ("great_tit", 2, pytest.approx(0.9))
    assert (settings.evidence_dir / "2026-11-01" / "great_tit.jpg").stat().st_size > 1000

def test_pipeline_resumes_clock_after_restart(...):
    run_detections(p, 3); first_total = store.total_watched_s()
    p2, store2 = build(same db path); run_detections(p2, 1)
    assert store2.total_watched_s() == pytest.approx(first_total + 120)
    assert p2.live().sim_time > p.live().sim_time

def test_slow_detector_drops_frames_and_caps_effort(...):
    # camera stub whose footage time jumps 30 s between reads
    run_detections(p, 2)
    assert store.total_watched_s() == pytest.approx(120 + 10 * 60)

def test_roi_boxes_come_back_in_full_frame_coordinates(...):
    # roi=(0.5, 0.5, 0.5, 0.5) on a 320x240 clip; scripted box [0, 0, 20, 20]
    assert p.last_detections[0].box == (160, 120, 180, 140)

def test_live_state_reports_unidentified_birds_without_counting_them(...):
    # frame with one great_tit at 0.9 and one "unidentified" at 0.8
    assert p.live().now == {"great_tit": 1, "blue_tit": 0} and p.live().unidentified == 1
```

- [ ] **Step 2: Run them and see them fail**

Run: `uv run pytest tests/test_camera.py tests/test_pipeline.py -q` — Expected: FAIL, `ModuleNotFoundError`.

- [ ] **Step 3: Implement `config.py`, `camera.py`, `draw.py`, `pipeline.py`, `__main__.py`**

`annotate` draws counted detections with a solid 2 px box and the label `"<English name> 0.87"`, and every other detection with a 1 px grey box labelled `unidentified`. `__main__` builds the store with `detector.species`, runs the pipeline on a thread, and (unless `--no-web`) serves the Task 5 app; until Task 5 exists `--no-web` is the only mode and it prints one line per detection: simulated time, counts, `detect_ms`.

- [ ] **Step 4: Run the tests and see them pass**

Run: `uv run pytest -q` — Expected: all pass.

- [ ] **Step 5: Run it headless on real footage**

Needs any feeder clip in `data/videos/demo/`. Run: `uv run python -m feeder_census --videos data/videos/demo --detector two_stage --no-web --fast`
Expected: a line every detection with a growing simulated time; `data/census.db` exists; after a named bird has appeared, `data/evidence/2026-11-01/` holds a JPEG. Then `uv run python -m feeder_census.bench --detector two_stage --video data/videos/demo/<file>` and note `median_ms`.
If no footage has arrived yet, run the same command with `--detector scripted --script tests/data/demo_script.json` on a clip made by the test fixture, and repeat this step when footage arrives.

- [ ] **Step 6: Commit**

`git add -A && git commit -m "feat: simulated camera, demo clock and counting pipeline"`

---

### Task 5: The demo page

**Files:**
- Create: `feeder_census/web.py`, `feeder_census/static/index.html`, `feeder_census/static/app.js`, `feeder_census/static/style.css`
- Modify: `feeder_census/__main__.py` (serve the app unless `--no-web`)
- Test: `tests/test_web.py`

**Interfaces:**
- Consumes: `Pipeline.live()`, `Store` reads, `Species`, `Settings`.
- Produces: `web.create_app(pipeline, store, species: Sequence[Species], settings, model_card: dict | None) -> FastAPI`, bound to `0.0.0.0:<port>`.

| Route | Returns |
|---|---|
| `GET /` | the page |
| `GET /stream.mjpg` | `multipart/x-mixed-replace` stream of the annotated preview JPEG |
| `GET /api/live` | `{"sim_time", "detector", "detect_ms", "now": {key: n}, "confirmed": {key: n}, "unidentified", "time_scale", "recorded": true}` |
| `GET /api/tables` | `{"species": [{"key", "english", "finnish", "habitat"}], "hours": [row], "days": [row], "periods": [row], "habitats": [{"key", "label", "birds", "species": [English names]}]}`; `row = {"key", "label", "hours_watched", "counts"}`; `hours` is the current simulated day, `days` the current period; `habitats` is `habitat_mix` of the current period's maxima over the species the detector can name, with labels `Forest birds`, `Farmland birds`, `Town birds`, `Generalists` |
| `GET /api/evidence` | `[{"day", "species", "count", "confidence", "ts", "url"}]`, newest first |
| `GET /evidence/{day}/{species}.jpg` | the photo, 404 if absent |
| `GET /export/census.csv` | `Store.export_csv` output as an attachment named `feeder-census.csv` |
| `GET /api/model` | `model_card`, or `{"name": <detector name>, "metrics": null}` |

`species` in `/api/tables` is the visible column list, in `species.toml` order: every core species the detector can name, plus any other nameable species with a count above 0 in the returned rows.

Copy the page must carry, word for word:

- `Recorded feeder footage, standing in for the camera.`
- `Demo clock: 1 second of footage = 1 minute.` (the numbers come from `time_scale`)
- `Largest number seen at once. Only surely identified birds are counted.`
- `This model can name: <English names>.`
- Beside the model accuracy: `Measured on footage the model had not seen.` when `metrics` is present, otherwise `Accuracy not yet measured on this footage.`
- Above the habitat mix: `Species mix by habitat. Our own grouping, not yet checked against Luomus. One feeder is one data point.`

Every species is shown with its English and its Finnish name (`Great tit · Talitiainen`).

The page shows, in this priority: the live feed with boxes; what is in frame now and this hour's maximum per species, with the simulated clock; hours watched today; the day and half-month tables (blank cell, not 0, where nothing was watched); the habitat mix for the current half-month; the evidence photos with species, count, time and confidence; the model card with ms per frame; a CSV export button. It must read from the back of a room on a projector.

- [ ] **Step 1: Write the failing tests**

```python
# client fixture: TestClient(create_app(...)) over a scripted pipeline that has run 3 detections of two great tits
def test_live_state_has_the_fields_the_page_needs(client):
    j = client.get("/api/live").json()
    assert j["recorded"] is True and j["time_scale"] == 60 and j["confirmed"]["great_tit"] == 2
    assert set(j) >= {"sim_time", "detector", "detect_ms", "now", "confirmed", "unidentified"}

def test_tables_match_the_store(client, store):
    j = client.get("/api/tables").json()
    assert j["periods"][0]["label"] == "1–15 November 2026"
    assert j["periods"][0]["counts"]["great_tit"] == store.periods()[0].counts["great_tit"] == 2

def test_tables_hide_species_the_detector_cannot_name(client):
    keys = [s["key"] for s in client.get("/api/tables").json()["species"]]
    assert keys == ["great_tit", "blue_tit"]          # the scripted detector's list; no yellowhammer column of zeros

def test_non_core_species_gets_a_column_only_when_seen(...):
    # detector species great_tit + magpie; magpie never counted -> ["great_tit"]; after one magpie -> ["great_tit", "magpie"]

def test_habitat_mix_covers_only_nameable_species(client):
    h = {x["key"]: x for x in client.get("/api/tables").json()["habitats"]}
    assert h["generalist"]["birds"] == 2 and h["generalist"]["species"] == ["Great tit", "Blue tit"]
    assert h["forest"] == {"key": "forest", "label": "Forest birds", "birds": 0, "species": []}

def test_csv_download(client):
    r = client.get("/export/census.csv")
    assert r.headers["content-disposition"].endswith('filename="feeder-census.csv"')
    assert r.text.splitlines()[0].startswith("Period,Hours watched,Great tit")

def test_evidence_photo_is_served_and_paths_cannot_escape(client):
    assert client.get("/evidence/2026-11-01/great_tit.jpg").headers["content-type"] == "image/jpeg"
    assert client.get("/evidence/2026-11-01/blue_tit.jpg").status_code == 404
    assert client.get("/evidence/..%2F..%2Fcensus.db/x.jpg").status_code == 404

def test_page_carries_the_honesty_lines(client):
    html = client.get("/").text
    assert "Recorded feeder footage, standing in for the camera." in html
    assert "Largest number seen at once. Only surely identified birds are counted." in html
    assert "Our own grouping, not yet checked against Luomus." in html
```

- [ ] **Step 2: Run them and see them fail**

Run: `uv run pytest tests/test_web.py -q` — Expected: FAIL, `ModuleNotFoundError`.

- [ ] **Step 3: Implement `web.py` and wire it into `__main__`**

- [ ] **Step 4: Run the tests and see them pass**

Run: `uv run pytest -q` — Expected: all pass.

- [ ] **Step 5: Design and build the page**

Use the `impeccable` skill for `index.html`, `app.js`, `style.css` (plain files, no build step, no CDN: the board may be offline). `app.js` polls `/api/live` every second and `/api/tables` and `/api/evidence` every 5 seconds.

- [ ] **Step 6: Look at it**

Run: `uv run python -m feeder_census --videos data/videos/demo --detector two_stage`, open `http://localhost:8088`. With the Playwright MCP take screenshots at 1920×1080 and 1366×768 and check: the feed plays with boxes, the clock advances, the hour row fills, an evidence photo appears, the CSV downloads, the honesty lines are visible without scrolling at 1920×1080.

- [ ] **Step 7: Commit**

`git add -A && git commit -m "feat: live demo page with tables, evidence and CSV export"`

**Milestone A: the demo works on the laptop with pretrained models.**

---

### Task 6: Run it on the Arduino UNO Q

**Files:**
- Create: `tools/prepare_video.py`, `board/deploy.sh`, `board/run.sh`, `README.md`
- Modify, outside the repo: `~/.claude/Global information/local-dev-environment.md` (add port 8088, Feeder Census)
- Test: `tests/test_prepare_video.py`

**Interfaces:**
- Consumes: the whole `feeder_census` package, `models/`, `species.toml`.
- Produces:
  - `python tools/prepare_video.py IN OUT [--height 720] [--fps 15]` — re-encodes with OpenCV (`mp4v`); the board plays this copy, because decoding 1080p30 in software wastes its CPU
  - `board/deploy.sh [--detector two_stage|student]` — builds `build/board/` and pushes it
  - `board/run.sh [--detector ...] [--fast]` — starts the demo on the board and forwards the port
  - Board layout: `/home/arduino/feeder-census/{feeder_census/, species.toml, models/, videos/, data/, .venv/, run.log}`

Board facts (read over adb on 14 Nov 2026): `adb shell` is root; Debian 13, glibc 2.41, Python 3.13.5; no `pip`, no `uv`, no `cv2` on the host; internet works; 2.3 GB free on `/home/arduino`. Wheels for onnxruntime, ai-edge-litert, opencv-python-headless and numpy exist for aarch64 CPython 3.13.

- [ ] **Step 1: Write the failing test**

```python
def test_prepare_video_downscales_and_keeps_the_length(make_video, tmp_path):
    src = make_video(seconds=2.0, fps=30, size=(1920, 1080))
    out = tmp_path / "small.mp4"
    subprocess.run([sys.executable, "tools/prepare_video.py", src, out, "--height", "720", "--fps", "15"], check=True)
    cap = cv2.VideoCapture(str(out))
    assert cap.get(cv2.CAP_PROP_FRAME_HEIGHT) == 720 and cap.get(cv2.CAP_PROP_FPS) == pytest.approx(15, abs=0.5)
    assert cap.get(cv2.CAP_PROP_FRAME_COUNT) / 15 == pytest.approx(2.0, abs=0.2)
```

- [ ] **Step 2: Run it and see it fail, implement `prepare_video.py`, see it pass**

Run: `uv run pytest tests/test_prepare_video.py -q` — FAIL first (file not found), then PASS.

- [ ] **Step 3: Write `board/deploy.sh`**

It prepares each demo video into `build/board/videos/`, copies `feeder_census/`, `species.toml` and the chosen detector's model files, then `adb push build/board/. /home/arduino/feeder-census/`. On the board it installs uv if missing (`curl -LsSf https://astral.sh/uv/install.sh | sh`), creates `.venv` with `uv venv --python 3.13`, and installs `numpy opencv-python-headless onnxruntime ai-edge-litert fastapi uvicorn`. It must be safe to run twice.

- [ ] **Step 4: Deploy and measure**

Run: `board/deploy.sh`, then
`adb shell 'cd /home/arduino/feeder-census && .venv/bin/python -m feeder_census.bench --detector two_stage --video videos/<file> --frames 30'`
Expected: prints `median_ms`. Gate: median ≤ 1500 ms. If it is slower, set `detect_every_s` for the board to twice the median (rounded up to a whole second) in `board/run.sh`. Write the measured numbers into `README.md`.

- [ ] **Step 5: Write `board/run.sh` and run the demo from the board**

It stops any earlier run, starts `nohup .venv/bin/python -m feeder_census --videos videos --detector <kind> --port 8088 > run.log 2>&1 &` on the board, then `adb forward tcp:8088 tcp:8088`.
Run: `board/run.sh`, then `curl -s localhost:8088/api/live` — Expected: JSON whose `detector` is `pretrained two-stage` and whose `sim_time` moves between two calls. Open `http://localhost:8088` and repeat the Task 5 Step 6 checks. Run `adb shell free -m`: `available` must stay above 500.

- [ ] **Step 6: Write `README.md`**

How to run on the laptop, how to deploy and run on the board, the measured ms per frame on both, and the one-sentence disclosure for the demo: "This is footage from a feeder, standing in for our camera."

- [ ] **Step 7: Commit**

`git add -A && git commit -m "feat: deploy and run the demo on the Arduino UNO Q"`

**Milestone B: the board does detection, counting and the page; the laptop is only its screen.**

---

### Task 7: Teacher labelling on the Verda GPU

Large models label the footage so that people only check. A strong generic detector draws the bird boxes, and two independent classifiers name each crop. A label is accepted automatically only when they agree.

**Files:**
- Create: `tools/remote.sh`, `tools/extract_frames.py`, `tools/autolabel.py`, `tools/review_sheets.py`
- Test: `tests/test_labelling.py`

**Interfaces:**
- Consumes: `Species`, `load_species` (Task 1); `InatClassifier` (Task 3).
- Footage layout (from the team): `data/videos/train/` holds footage from at least two different feeders; `data/videos/demo/` holds the held-out demo footage from a feeder that is not in `train/`.
- Produces:
  - `tools/remote.sh push | run "<command>" | pull` — reads `VERDA_HOST` (for example `root@203.0.113.7`). `push` rsyncs the repo and `data/videos/` to `~/birdai`; `run` executes a command there inside `uv run --group train`; `pull` brings back `data/labels/`, `data/review/`, `data/dataset/classes.json` and `models/student/`.
  - `python tools/extract_frames.py --videos data/videos --out data/frames [--every 1.0] [--max-per-video 1500]` → `data/frames/<train|demo>/<video stem>/<video stem>_<milliseconds:08d>.jpg`
  - `python tools/autolabel.py --frames data/frames --out data/labels/auto.jsonl [--box-model yolo26x.pt] [--imgsz 1280] [--box-conf 0.20]`
  - `autolabel.decide_label(bioclip_species: str, score: float, margin: float, inat_species: str | None, inat_known: bool) -> tuple[str, str]` — returns `(label, status)`
  - `python tools/review_sheets.py --labels data/labels/auto.jsonl --frames data/frames --out data/review` → contact sheets `data/review/<label>/<label>_<NN>.jpg` (48 crops each, 8 × 6, every crop 160 px with its row number printed on it), `data/review/index.csv` (`n,id,label,status,bioclip,inat`) and, if missing, `data/review/corrections.csv` with the header `id,label`

One JSON line per box in `auto.jsonl`:

```json
{"id": "pihla_00012000#2", "split": "train", "video": "pihla", "frame": "train/pihla/pihla_00012000.jpg",
 "box": [412.0, 220.5, 498.0, 301.0], "box_conf": 0.83,
 "bioclip": {"species": "great_tit", "score": 0.91, "margin": 0.74},
 "inat": {"species": "great_tit", "prob": 0.66},
 "label": "great_tit", "status": "auto"}
```

A frame with no bird box gets one line with `"id": "<frame stem>#-"`, `"box": null`, `"label": null`, `"status": "empty"`, so empty feeders become training negatives.

Teacher facts (checked 14 Nov 2026):

- **Boxes:** Ultralytics `YOLO("yolo26x.pt").predict(frame, classes=[14], imgsz=1280, conf=0.20)`. COCO `bird` is class 14. If `yolo26x.pt` fails to load, use `yolo11x.pt`.
- **Species, teacher 1:** BioCLIP 2 through pybioclip: `CustomLabelsClassifier(labels).predict(list_of_PIL_crops)` returns, per crop, items with `classification` and `score`. Build one label per species in `species.toml` as `"<scientific> with common name <english>"`. `score` is the top item's score; `margin` is top minus second.
- **Species, teacher 2:** `InatClassifier` from Task 3. It was trained on other data, so agreement means something. `inat_known` is whether the species has a label in its label file.
- **Decision rule** (`decide_label`):
  - `(species, "auto")` when `score ≥ 0.60`, `margin ≥ 0.20` and teacher 2 names the same species.
  - `(species, "single")` when teacher 2 has no label for that species, `score ≥ 0.85` and `margin ≥ 0.30`.
  - otherwise `("unidentified", "review")`.

- [ ] **Step 1: Write the failing tests**

```python
def test_two_teachers_agreeing_gives_an_automatic_label():
    assert decide_label("great_tit", 0.91, 0.74, "great_tit", True) == ("great_tit", "auto")

def test_disagreement_or_a_narrow_margin_goes_to_review():
    assert decide_label("tree_sparrow", 0.70, 0.40, "house_sparrow", True) == ("unidentified", "review")
    assert decide_label("tree_sparrow", 0.55, 0.10, "tree_sparrow", True) == ("unidentified", "review")
    assert decide_label("great_tit", 0.95, 0.80, None, True) == ("unidentified", "review")

def test_species_the_second_teacher_cannot_name_needs_a_high_score():
    assert decide_label("willow_tit", 0.90, 0.50, None, False) == ("willow_tit", "single")
    assert decide_label("willow_tit", 0.80, 0.50, None, False) == ("unidentified", "review")

def test_extract_frames_keeps_the_train_demo_split(make_video, tmp_path):
    # videos/train/a.mp4 and videos/demo/b.mp4, 3 s each, --every 1.0
    assert sorted(p.name for p in (out / "train" / "a").iterdir()) == ["a_00000000.jpg", "a_00001000.jpg", "a_00002000.jpg"]
    assert len(list((out / "demo" / "b").iterdir())) == 3

def test_label_frame_writes_rows_for_birds_and_for_empty_frames():
    # label_frame(frame, meta, boxes_fn, bioclip_fn, inat_fn, species) with stub teachers
    rows = label_frame(..., boxes_fn=lambda f: [])
    assert rows == [{"id": "a_00000000#-", "split": "train", "video": "a", "frame": "train/a/a_00000000.jpg",
                     "box": None, "label": None, "status": "empty"}]
    rows = label_frame(..., boxes_fn=two boxes, stubs naming great_tit twice)
    assert [r["id"] for r in rows] == ["a_00000000#0", "a_00000000#1"] and rows[0]["status"] == "auto"

def test_review_sheets_hold_48_crops_and_an_index(tmp_path):
    # 100 great_tit rows -> great_tit_01.jpg, _02.jpg, _03.jpg; index.csv has 100 data lines; corrections.csv == "id,label\n"
```

- [ ] **Step 2: Run them and see them fail**

Run: `uv run pytest tests/test_labelling.py -q` — Expected: FAIL, `ModuleNotFoundError`.

- [ ] **Step 3: Implement the four tools**

`autolabel.py` imports ultralytics and pybioclip inside `main()`, so the tests run without them. `label_frame` holds the per-frame logic and takes the three teachers as functions.

- [ ] **Step 4: Run the tests and see them pass**

Run: `uv run pytest -q` — Expected: all pass.

- [ ] **Step 5: Prepare the Verda machine**

Needs `VERDA_HOST` from the team (one L40S or A100-class instance, Ubuntu, SSH key installed). Run: `tools/remote.sh push && tools/remote.sh run "nvidia-smi --query-gpu=name --format=csv,noheader && python -c 'import ultralytics, bioclip; print(\"ok\")'"`
Expected: the GPU name, then `ok`.

- [ ] **Step 6: Label the footage**

Run: `tools/remote.sh run "python tools/extract_frames.py --videos data/videos --out data/frames && python tools/autolabel.py --frames data/frames --out data/labels/auto.jsonl && python tools/review_sheets.py --labels data/labels/auto.jsonl --frames data/frames --out data/review" && tools/remote.sh pull`
Expected: `autolabel.py` ends with a table of boxes per label, split and status. **Gate:** at least two species with 60 or more `auto` or `single` boxes in `train`. If not, stop and tell the team which species are short; they supply more footage or accept fewer species.

- [ ] **Step 7: Check the labels**

Open every sheet under `data/review/` (the Read tool shows images). For each crop that is visibly a different species than its sheet, add a line `<id>,<right species key>` to `data/review/corrections.csv`; use `drop` for a crop that is not a bird and `unidentified` when it cannot be told. In the `unidentified` sheets, promote only crops that are unmistakable. Then hand the sheets and `corrections.csv` to a team member for a 15-minute pass; tree sparrow against house sparrow and willow tit against other tits need a person who knows the birds.

- [ ] **Step 8: Commit**

`git add -A && git commit -m "feat: teacher labelling tools for the feeder footage"` (code only; `data/` is ignored)

---

### Task 8: Dataset, student training and the student detector

**Files:**
- Create: `tools/build_dataset.py`, `tools/train_student.py`, `feeder_census/detectors/student.py`
- Modify: `feeder_census/detectors/__init__.py`, `feeder_census/bench.py`, `feeder_census/__main__.py` (add `student_dir`)
- Test: `tests/test_dataset.py`, `tests/test_student.py`

**Interfaces:**
- Consumes: `auto.jsonl` rows and `corrections.csv` (Task 7); `letterbox`, `nms`, `Detector` (Task 3).
- Produces:
  - `build_dataset.choose_classes(train_counts: Mapping[str, int], min_boxes: int = 60) -> list[str]` — species with at least `min_boxes` training boxes, most frequent first, then `"unidentified"` last
  - `build_dataset.apply_corrections(rows: list[dict], corrections: Mapping[str, str]) -> list[dict]`
  - `python tools/build_dataset.py --labels data/labels/auto.jsonl --corrections data/review/corrections.csv --frames data/frames --out data/dataset [--min-boxes 60]` → `data/dataset/images/{train,val}/`, `labels/{train,val}/` (YOLO text format), `data.yaml`, `classes.json`. `val` is exactly the `demo` split.
  - `python tools/train_student.py --data data/dataset/data.yaml --imgsz 640 416 [--epochs 60] [--base yolo26n.pt] --out models/student` → for each size `models/student/<imgsz>/feeder.onnx` and `feeder.json`
  - Card `feeder.json`: `{"name": "Feeder student <imgsz>", "kind": "student", "base": "yolo26n", "imgsz": 640, "classes": [...], "count_threshold": 0.60, "trained_at": "...", "train_boxes": {key: n}, "held_out_footage": [stems], "metrics": null}`
  - `student.decode_student(output: np.ndarray, ratio: float, pad: tuple[int, int], classes: Sequence[str], min_score: float = 0.05, nms_iou: float = 0.5) -> list[Detection]`
  - `student.StudentDetector(model: Path, card: Path)` — `name` and `count_threshold` from the card; `species` = `classes` without `"unidentified"`
  - `build_detector(kind, models_dir, species, script=None, student_dir: Path | None = None)` — `student_dir` defaults to `models_dir / "student"`; `bench` and `__main__` gain `--student-dir`

Dataset rules: a box whose final label is a species outside `choose_classes` becomes `unidentified`. Rows with label `drop` are removed. `empty` frames get an empty label file. A frame is never split between train and val; the split comes from its footage folder. With no `demo` rows the tool exits with code 2 and the message `no held-out footage: put the demo video in data/videos/demo`. With fewer than two species classes it exits with code 2 and lists the box counts.

Student model facts (Ultralytics 8.4.212, read from its exporter source):

- Train: `YOLO(base).train(data=..., imgsz=S, epochs=60, batch=32, patience=15, cache=True)`.
- Export: `model.export(format="onnx", imgsz=S, nms=False, simplify=True)`. For YOLO26 this selects the end-to-end head and the output is `[1, 300, 6]`: `x1, y1, x2, y2, score, class_index` in letterboxed input pixels. `train_student.py` opens the file with onnxruntime and fails if the output shape is not `[1, N, 6]`.
- If YOLO26 training fails, use `--base yolo11n.pt`; the script then exports with `nms=True, conf=0.05`, which gives the same six-column rows.
- Input: RGB, NCHW, float32 scaled to 0–1, letterbox centred with pad 114.
- `decode_student` drops rows under `min_score`, undoes pad then ratio, runs class-agnostic `nms`, and maps the `unidentified` class to `UNIDENTIFIED`.

- [ ] **Step 1: Write the failing tests**

```python
# tests/test_dataset.py
def test_choose_classes_keeps_species_with_enough_boxes():
    counts = {"great_tit": 400, "blue_tit": 61, "bullfinch": 59, "unidentified": 900}
    assert choose_classes(counts, min_boxes=60) == ["great_tit", "blue_tit", "unidentified"]

def test_corrections_relabel_and_drop():
    rows = [row("a#0", "great_tit"), row("a#1", "great_tit"), row("a#2", "unidentified")]
    out = apply_corrections(rows, {"a#0": "blue_tit", "a#1": "drop", "a#2": "willow_tit"})
    assert [(r["id"], r["label"]) for r in out] == [("a#0", "blue_tit"), ("a#2", "willow_tit")]

def test_dataset_split_follows_the_footage_and_rare_species_become_unidentified(tmp_path):
    # 70 great_tit + 65 blue_tit + 5 bullfinch boxes in split "train", 10 great_tit in split "demo";
    # every box is the centre quarter of a 400x400 frame
    run_build(...)
    assert json.loads((out / "classes.json").read_text()) == ["great_tit", "blue_tit", "unidentified"]
    assert not any("demo" in p.name for p in (out / "images" / "train").iterdir())
    assert (out / "labels" / "val" / "d_00000000.txt").read_text().splitlines()[0] == "0 0.500000 0.500000 0.500000 0.500000"
    assert bullfinch_frame_label.startswith("2 ")

def test_build_refuses_without_held_out_footage(tmp_path):
    assert run_build(only_train_rows).returncode == 2

# tests/test_student.py
def test_decode_student_undoes_the_letterbox():
    out = np.zeros((1, 300, 6), np.float32)
    out[0, 0] = [100, 240, 200, 340, 0.9, 0]          # 1920x1080 in a 640 letterbox: ratio 1/3, pad (0, 140)
    (d,) = decode_student(out, ratio=1 / 3, pad=(0, 140), classes=["great_tit", "unidentified"])
    assert d.species == "great_tit" and d.confidence == pytest.approx(0.9)
    assert d.box == pytest.approx((300, 300, 600, 600))

def test_student_never_gives_one_bird_two_species():
    out = np.zeros((1, 300, 6), np.float32)
    out[0, 0] = [100, 240, 200, 340, 0.8, 0]; out[0, 1] = [102, 241, 201, 338, 0.6, 1]
    dets = decode_student(out, 1 / 3, (0, 140), ["great_tit", "blue_tit", "unidentified"])
    assert [d.species for d in dets] == ["great_tit"]

def test_unidentified_class_is_not_a_species():
    out = np.zeros((1, 300, 6), np.float32); out[0, 0] = [10, 150, 60, 200, 0.7, 1]
    (d,) = decode_student(out, 1 / 3, (0, 140), ["great_tit", "unidentified"])
    assert d.species == UNIDENTIFIED
```

- [ ] **Step 2: Run them and see them fail**

Run: `uv run pytest tests/test_dataset.py tests/test_student.py -q` — Expected: FAIL, `ModuleNotFoundError`.

- [ ] **Step 3: Implement the two tools and `student.py`**

- [ ] **Step 4: Run the tests and see them pass**

Run: `uv run pytest -q` — Expected: all pass.

- [ ] **Step 5: Build the dataset and train on Verda**

Run: `tools/remote.sh push && tools/remote.sh run "python tools/build_dataset.py --labels data/labels/auto.jsonl --corrections data/review/corrections.csv --frames data/frames --out data/dataset && python tools/train_student.py --data data/dataset/data.yaml --imgsz 640 416 --out models/student" && tools/remote.sh pull`
Expected: a class table from `build_dataset.py`, two training runs that each print validation mAP, and `models/student/640/feeder.onnx` and `models/student/416/feeder.onnx` on the laptop, each around 10 MB.
Backup, only if Verda has no machine: wrap the same two commands in a Modal function with the dataset in a Modal Volume and a checkpoint every epoch, as `compute-plan-verda-modal.md` describes.

- [ ] **Step 6: Try the student on the laptop**

Run: `uv run python -m feeder_census --videos data/videos/demo --detector student --student-dir models/student/640 --db data/student-try.db`
Expected: the page shows boxes with species names on the demo footage, and its species list matches `classes.json`.

- [ ] **Step 7: Commit**

`git add -A && git commit -m "feat: dataset builder, student training and student detector"`

---

### Task 9: Measure, choose and ship

**Files:**
- Create: `tools/evaluate.py`
- Modify: `feeder_census/__main__.py` (`--detector auto`, model card), `board/deploy.sh`, `README.md`
- Test: `tests/test_evaluate.py`

**Interfaces:**
- Consumes: `data/dataset` (val split = held-out demo footage), both detectors, `feeder_census.bench`.
- Produces:
  - `evaluate.Tally(tp: int, fp: int, fn: int)`
  - `evaluate.match_frame(pred: Sequence[Detection], truth: Sequence[Detection], iou: float = 0.5) -> dict[str, Tally]` — a prediction is a hit when it overlaps an unmatched truth box of the same species at IoU ≥ `iou`. Predictions that overlap an `unidentified` truth box are ignored, neither hit nor error. `UNIDENTIFIED` predictions are ignored.
  - `evaluate.pick_threshold(curves: Mapping[str, Sequence[tuple[float, float, float]]], val_boxes: Mapping[str, int], min_precision: float = 0.90, min_val_boxes: int = 20) -> float` — `curves[species]` is `(threshold, precision, recall)` for thresholds 0.50 to 0.90 in steps of 0.05; returns the lowest threshold at which every species with at least `min_val_boxes` reaches `min_precision`, or 0.90 when none does
  - `python tools/evaluate.py --dataset data/dataset --candidates two_stage student:640 student:416 --board-ms two_stage=<ms>,640=<ms>,416=<ms> [--promote]` — prints one table per candidate, writes `models/eval.json`; with `--promote` copies the winning student to `models/student/feeder.onnx` and `feeder.json` and writes `models/model_card.json`
  - `models/model_card.json`: `{"name", "kind": "student" | "two_stage", "species": [...], "count_threshold", "board_ms", "metrics": {"frames", "footage": [stems], "count_exact", "per_species": {key: {"precision", "recall", "val_boxes"}}, "labels": "teacher models, checked by a person"}}`
  - `python -m feeder_census --detector auto` (the new default): the card's `kind`, or `two_stage` when there is no card. The card is passed to `create_app` and its `count_threshold` overrides the detector's.

Rules:

- `count_exact` is the share of held-out frames where the counted number of every species equals the truth, at the chosen threshold.
- A candidate is eligible when its board median is at most 1500 ms.
- A student **qualifies** when at least three species reach precision ≥ 0.90 with recall ≥ 0.50 on the held-out footage.
- The winner is the qualifying student with the highest `count_exact`, provided that is at least the two-stage detector's. Otherwise the two-stage detector ships, and the card and README say why.
- The truth labels come from the teachers plus a person's check, and the two-stage detector shares one teacher. The README states both facts next to the numbers.

- [ ] **Step 1: Write the failing tests**

```python
A, B = (0, 0, 100, 100), (200, 200, 300, 300)
def det(species, box, conf=0.9): return Detection(species, conf, box)

def test_match_frame_counts_hits_misses_and_wrong_names():
    truth = [det("great_tit", A), det("blue_tit", B)]
    pred = [det("great_tit", (2, 2, 98, 98)), det("great_tit", (205, 205, 300, 300))]
    r = match_frame(pred, truth)
    assert r["great_tit"] == Tally(tp=1, fp=1, fn=0) and r["blue_tit"] == Tally(tp=0, fp=0, fn=1)

def test_predictions_on_unidentified_truth_are_not_errors():
    r = match_frame([det("great_tit", A)], [det("unidentified", A)])
    assert r.get("great_tit", Tally(0, 0, 0)) == Tally(0, 0, 0)

def test_pick_threshold_takes_the_lowest_sure_one():
    curves = {"great_tit": [(0.50, 0.85, 0.9), (0.55, 0.91, 0.88), (0.60, 0.95, 0.8)],
              "blue_tit": [(0.50, 0.92, 0.7), (0.55, 0.93, 0.7), (0.60, 0.97, 0.6)]}
    assert pick_threshold(curves, {"great_tit": 80, "blue_tit": 40}) == 0.55

def test_pick_threshold_ignores_species_with_few_examples():
    curves = {"great_tit": [(0.50, 0.95, 0.9)], "jay": [(0.50, 0.10, 0.5)]}
    assert pick_threshold(curves, {"great_tit": 80, "jay": 3}) == 0.50

def test_pick_threshold_falls_back_to_0_90():
    assert pick_threshold({"great_tit": [(0.50, 0.5, 0.9), (0.90, 0.6, 0.2)]}, {"great_tit": 80}) == 0.90
```

- [ ] **Step 2: Run them and see them fail**

Run: `uv run pytest tests/test_evaluate.py -q` — Expected: FAIL, `ModuleNotFoundError`.

- [ ] **Step 3: Implement `evaluate.py` and the `--detector auto` path**

- [ ] **Step 4: Run the tests and see them pass**

Run: `uv run pytest -q` — Expected: all pass.

- [ ] **Step 5: Measure speed on the board**

Run `board/deploy.sh --detector student`, then on the board `python -m feeder_census.bench --detector student --student-dir models/student/640 --video videos/<file>` and the same for `416`. Note the three medians (two-stage is from Task 6).

- [ ] **Step 6: Evaluate and choose**

Run: `uv run python tools/evaluate.py --dataset data/dataset --candidates two_stage student:640 student:416 --board-ms two_stage=<ms>,640=<ms>,416=<ms> --promote`
Expected: three tables and a last line `SHIP: <candidate> (count_exact=…, threshold=…)`. Show the tables to the team before going on.

- [ ] **Step 7: Ship to the board and run the whole demo**

Run: `board/deploy.sh && board/run.sh --fast` for ten minutes to fill several simulated days, then `board/run.sh` for the live run. Check on `http://localhost:8088`: the model card shows the measured numbers and `Measured on footage the model had not seen.`, the half-month table has at least one full period, the habitat mix is filled, evidence photos open, the CSV downloads.

- [ ] **Step 8: Finish**

Write the measured accuracy, the ms per frame and the parts cost line into `README.md`. `python3 .agents/agentchat.py say PROGRESS "demo runs on the UNO Q with <model>"`, then `git add -A && git commit -m "feat: evaluation, model choice and final board demo" && git push -u origin HEAD`. The team records a backup video of the working demo and stops the Verda instance.

**Milestone C: the model on the board is the one that measured best on unseen Finnish feeder footage.**

---

## Order and timing

Two tracks run in parallel. Track A needs nothing from outside; Track B needs footage and the Verda machine.

| Track | Tasks | Needs | Target (14 Nov) |
|---|---|---|---|
| A: runtime | 1 → 2 → 3 → 4 → 5 → 6 | board on USB; one demo clip for the visual checks | Milestone A 16:30, Milestone B 18:00 |
| B: model | 7 → 8 → 9 (after Task 3) | footage by 15:00, `VERDA_HOST`, 15 minutes of a person's label checking | labels 17:30, models 19:00, Milestone C 21:00 |

21:00–23:00 is rehearsal, the backup recording and slack. If Track B misses its 20:00 gate (no qualifying student), the demo ships the pretrained two-stage detector on the board and the pitch says the trained model is the next step.

## Not in this plan

Each is in the sketch and was cut for the midnight deadline: the squirrel and rat flag, the distance-sensor wake-up, a live camera on the board, int8 quantisation, the Modal sweep, and packaging as an App Lab app.
