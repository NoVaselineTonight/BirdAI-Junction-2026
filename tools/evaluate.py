"""Measure the detectors on held-out footage and choose which one ships.

    python tools/evaluate.py --dataset data/dataset --candidates two_stage student:640 student:416 \
        [--models-dir models] [--board-ms two_stage=<ms>,640=<ms>,416=<ms>] [--promote]

Every reported number (per-species precision and recall, count_exact, frames, footage) is measured on
the dataset's `test` split, the held-out demo footage, at the candidate's count threshold. The student's
threshold is the only thing chosen from data, and it is chosen on `val` (the tail of each training
video); `test` takes no part in it. The two-stage detector keeps its fixed threshold and never sees `val`.

Writes <models-dir>/eval.json on every run. With --promote it also copies the winning student to
<models-dir>/student/feeder.onnx and feeder.json (threshold and metrics filled in) and writes
<models-dir>/model_card.json. The last line printed is `SHIP: <candidate> (count_exact=..., threshold=...)`.
"""

import argparse
import json
import shutil
import sys
from collections.abc import Mapping, Sequence
from dataclasses import dataclass
from pathlib import Path
from typing import NoReturn

import cv2

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))  # `python tools/evaluate.py` has no repo root on the path

from feeder_census.census import frame_counts  # noqa: E402
from feeder_census.species import load_species  # noqa: E402
from feeder_census.types import UNIDENTIFIED, Detection  # noqa: E402

THRESHOLDS = tuple(round(0.50 + 0.05 * i, 2) for i in range(9))  # 0.50 .. 0.90
FALLBACK_THRESHOLD = 0.90
MAX_BOARD_MS = 1500.0
MIN_QUALIFYING_SPECIES = 3
QUALIFY_PRECISION = 0.90
QUALIFY_RECALL = 0.50
LABELS = "teacher models, checked by a person"

Frame = tuple[list[Detection], list[Detection]]  # (everything the detector saw, the truth)


@dataclass
class Tally:
    tp: int
    fp: int
    fn: int


def iou(a: Sequence[float], b: Sequence[float]) -> float:
    w = min(a[2], b[2]) - max(a[0], b[0])
    h = min(a[3], b[3]) - max(a[1], b[1])
    inter = max(w, 0.0) * max(h, 0.0)
    union = (a[2] - a[0]) * (a[3] - a[1]) + (b[2] - b[0]) * (b[3] - b[1]) - inter
    return inter / union if union > 0 else 0.0


def _off_unidentified(pred: Sequence[Detection], truth: Sequence[Detection], min_iou: float) -> list[Detection]:
    """Predictions that do not overlap an `unidentified` truth box: those are neither hits nor errors."""
    unknown = [t.box for t in truth if t.species == UNIDENTIFIED]
    return [p for p in pred if not any(iou(p.box, box) >= min_iou for box in unknown)]


def match_frame(pred: Sequence[Detection], truth: Sequence[Detection], iou: float = 0.5) -> dict[str, Tally]:
    """Per species hits, false alarms and misses for one frame. Matching is one to one, best confidence first."""
    min_iou = iou
    tallies: dict[str, Tally] = {}

    def tally(species: str) -> Tally:
        return tallies.setdefault(species, Tally(0, 0, 0))

    free = [t for t in truth if t.species != UNIDENTIFIED]
    kept = _off_unidentified([p for p in pred if p.species != UNIDENTIFIED], truth, min_iou)
    for p in sorted(kept, key=lambda d: -d.confidence):
        candidates = [t for t in free if t.species == p.species and box_iou(p, t) >= min_iou]
        if candidates:
            free.remove(max(candidates, key=lambda t: box_iou(p, t)))
            tally(p.species).tp += 1
        else:
            tally(p.species).fp += 1
    for t in free:
        tally(t.species).fn += 1
    return tallies


def box_iou(a: Detection, b: Detection) -> float:
    return iou(a.box, b.box)


def frame_is_exact(pred: Sequence[Detection], truth: Sequence[Detection], threshold: float,
                   species: Sequence[str]) -> bool:
    """True when the counted birds of every dataset species equal the truth in this frame."""
    counted = frame_counts(_off_unidentified(pred, truth, 0.5), threshold)
    wanted: dict[str, int] = {}
    for t in truth:
        wanted[t.species] = wanted.get(t.species, 0) + 1
    return all(counted.get(s, 0) == wanted.get(s, 0) for s in species)


def _rates(t: Tally) -> tuple[float, float]:
    """Precision and recall; with nothing predicted (or nothing to find) the rate is 0, never a free 1.0."""
    return (t.tp / (t.tp + t.fp) if t.tp + t.fp else 0.0, t.tp / (t.tp + t.fn) if t.tp + t.fn else 0.0)


def _known_rates(t: Tally) -> tuple[float | None, float | None]:
    """Precision and recall as reported: None when undefined (nothing predicted, or no truth to find)."""
    return (t.tp / (t.tp + t.fp) if t.tp + t.fp else None, t.tp / (t.tp + t.fn) if t.tp + t.fn else None)


def _tally_frames(frames: Sequence[Frame], threshold: float, species: Sequence[str]) -> dict[str, Tally]:
    total = {s: Tally(0, 0, 0) for s in species}
    for pred, truth in frames:
        for key, t in match_frame([d for d in pred if d.confidence >= threshold], truth).items():
            if key in total:
                total[key].tp += t.tp
                total[key].fp += t.fp
                total[key].fn += t.fn
    return total


def build_tallies(frames: Sequence[Frame], species: Sequence[str],
                  thresholds: Sequence[float] = THRESHOLDS) -> dict[float, dict[str, Tally]]:
    """Per threshold, the per-species hits, false alarms and misses over `frames`."""
    return {threshold: _tally_frames(frames, threshold, species) for threshold in thresholds}


def build_curves(frames: Sequence[Frame], species: Sequence[str],
                 thresholds: Sequence[float] = THRESHOLDS) -> dict[str, list[tuple[float, float, float]]]:
    """Per species, (threshold, precision, recall) over `frames` for every threshold."""
    curves: dict[str, list[tuple[float, float, float]]] = {s: [] for s in species}
    for threshold, tallies in build_tallies(frames, species, thresholds).items():
        for key, t in tallies.items():
            curves[key].append((threshold, *_rates(t)))
    return curves


def count_boxes(frames: Sequence[Frame], species: Sequence[str]) -> dict[str, int]:
    return {s: sum(1 for _, truth in frames for t in truth if t.species == s) for s in species}


def _lowest_pooled(tallies: Mapping[float, Mapping[str, Tally]], val_boxes: Mapping[str, int],
                   min_precision: float, min_val_boxes: int) -> float | None:
    """The lowest threshold whose pooled precision over the judged species reaches `min_precision`, else None.

    Judged species are those with at least `min_val_boxes` validation boxes. Pooled precision is the summed
    hits over the summed hits and false alarms; with nothing predicted it is undefined and does not qualify.
    """
    for threshold in sorted(tallies):
        judged = [t for s, t in tallies[threshold].items() if val_boxes.get(s, 0) >= min_val_boxes]
        hits = sum(t.tp for t in judged)
        named = hits + sum(t.fp for t in judged)
        if named and hits / named >= min_precision:
            return threshold
    return None


def pick_threshold(tallies: Mapping[float, Mapping[str, Tally]], val_boxes: Mapping[str, int],
                   min_precision: float = 0.90, min_val_boxes: int = 20) -> float:
    """The lowest threshold at which at least `min_precision` of the named birds were right, judged species pooled.

    `tallies[threshold][species]` are the validation hits and false alarms (see `build_tallies`). One small
    species cannot hold the cut-off up on its own: only the pooled precision counts. 0.90 when no threshold
    reaches it, and also when no species has enough boxes to judge by.
    """
    found = _lowest_pooled(tallies, val_boxes, min_precision, min_val_boxes)
    return FALLBACK_THRESHOLD if found is None else found


def score_frames(frames: Sequence[Frame], threshold: float, species: Sequence[str]) -> dict:
    """frames, count_exact and per-species precision, recall and truth box count at one threshold."""
    tallies = _tally_frames(frames, threshold, species)
    boxes = count_boxes(frames, species)
    exact = sum(frame_is_exact(pred, truth, threshold, species) for pred, truth in frames)
    return {
        "frames": len(frames),
        "count_exact": exact / len(frames) if frames else 0.0,
        # `val_boxes` keeps its name for the page; it is the number of truth boxes in the held-out `test` footage.
        # precision / recall are None (JSON null) when undefined; the page must show them as unknown.
        "per_species": {
            s: {"precision": _known_rates(tallies[s])[0], "recall": _known_rates(tallies[s])[1],
                "val_boxes": boxes[s]}
            for s in species
        },
    }


def read_truth(label_file: Path, image_size: tuple[int, int], classes: Sequence[str]) -> list[Detection]:
    """A YOLO label file as detections in pixels; `image_size` is (width, height)."""
    width, height = image_size
    truth = []
    for line in label_file.read_text().splitlines():
        if not line.strip():
            continue
        index, cx, cy, w, h = line.split()
        cx, w = float(cx) * width, float(w) * width
        cy, h = float(cy) * height, float(h) * height
        truth.append(Detection(classes[int(index)], 1.0, (cx - w / 2, cy - h / 2, cx + w / 2, cy + h / 2)))
    return truth


def run_split(detector, dataset: Path, split: str, classes: Sequence[str]) -> tuple[list[Frame], list[str]]:
    """Runs the detector on every image of a split. Returns the frames and the video stems they come from."""
    frames, footage = [], set()
    for image_path in sorted((dataset / "images" / split).glob("*.jpg")):
        image = cv2.imread(str(image_path))
        if image is None:
            raise RuntimeError(f"cannot read frame {image_path}")
        height, width = image.shape[:2]
        truth = read_truth(dataset / "labels" / split / f"{image_path.stem}.txt", (width, height), classes)
        frames.append((detector.detect(image), truth))
        footage.add(image_path.stem.rsplit("_", 1)[0])
    return frames, sorted(footage)


SOURCE_PICKED = ("picked on validation footage: the lowest threshold where at least 90% of named birds were right, "
                 "all judged species together")
SOURCE_FALLBACK = ("fallback 0.90: no threshold reached 0.90 precision on validation footage, "
                   "all judged species together")
SOURCE_DEFAULT = "default: too few validation boxes to pick"


def student_threshold(tallies: Mapping[float, Mapping[str, Tally]], val_boxes: Mapping[str, int],
                      default: float, min_val_boxes: int = 20) -> tuple[float, str]:
    """The student's count threshold and where it came from.

    Picked when species with at least `min_val_boxes` validation boxes exist and some grid threshold gives
    them, pooled together, precision 0.90; 0.90 as a labelled fallback when none does; `default` (the card's
    own threshold) when no species has enough validation boxes, since then nothing was measured to pick by.
    """
    if not any(val_boxes.get(s, 0) >= min_val_boxes for by_species in tallies.values() for s in by_species):
        return default, SOURCE_DEFAULT
    found = _lowest_pooled(tallies, val_boxes, QUALIFY_PRECISION, min_val_boxes)
    if found is None:
        return FALLBACK_THRESHOLD, SOURCE_FALLBACK
    return found, SOURCE_PICKED


def evaluate_candidate(detector, dataset: Path, classes: Sequence[str], pick: bool,
                       min_val_boxes: int = 20) -> dict:
    """Measure one detector on `test`.

    With `pick` the threshold is chosen on `val` first (see `student_threshold`; `threshold_source` says
    how, `val_boxes` the validation truth boxes per species it was based on); otherwise the detector's own
    count_threshold is used, source "fixed", and `val` is never opened. Only the threshold depends on
    `val`; every other number is from `test`.
    """
    species = [c for c in classes if c != UNIDENTIFIED]
    val_boxes = None
    if pick:
        val_frames, _ = run_split(detector, dataset, "val", classes)
        val_boxes = count_boxes(val_frames, species)
        threshold, source = student_threshold(build_tallies(val_frames, species), val_boxes,
                                              detector.count_threshold, min_val_boxes)
    else:
        threshold, source = detector.count_threshold, "fixed"
    test_frames, footage = run_split(detector, dataset, "test", classes)
    return {"threshold": threshold, "threshold_source": source, "val_boxes": val_boxes, "footage": footage,
            **score_frames(test_frames, threshold, species)}


def qualifies(per_species: Mapping[str, Mapping[str, float | None]]) -> bool:
    """At least three species with both rates known and at or above the bars (an unknown rate is not good)."""
    good = [s for s in per_species.values()
            if s["precision"] is not None and s["recall"] is not None
            and s["precision"] >= QUALIFY_PRECISION and s["recall"] >= QUALIFY_RECALL]
    return len(good) >= MIN_QUALIFYING_SPECIES


def choose(results: Mapping[str, Mapping]) -> tuple[str, str, bool]:
    """The candidate to ship, a one-sentence reason, and whether the shipped model qualified.

    `results` has "two_stage" and any "student:<size>". A student without a board timing counts as eligible
    (timings are optional until --promote). When no fast student qualifies, the fast student with the highest
    count_exact still ships if it counts exactly in more frames than the two-stage detector, marked as below
    the bar (qualified False); otherwise the two-stage detector ships (qualified is False for it too).
    """
    two = results["two_stage"]["count_exact"]
    students = {n: r for n, r in results.items() if r["kind"] == "student"}
    fast = {n: r for n, r in students.items() if r["board_ms"] is None or r["board_ms"] <= MAX_BOARD_MS}
    good = {n: r for n, r in fast.items() if qualifies(r["per_species"])}
    if not students:
        return "two_stage", "no student model was evaluated, so the two-stage detector ships.", False
    if not fast:
        return "two_stage", f"every student takes more than {MAX_BOARD_MS:g} ms per frame on the board, so the two-stage detector ships.", False
    if not good:
        bar = (f"at least {MIN_QUALIFYING_SPECIES} species with precision "
               f"{QUALIFY_PRECISION:.2f} and recall {QUALIFY_RECALL:.2f} on unseen footage")
        scope = "student fast enough for the board" if len(fast) < len(students) else "student"
        top = max(fast, key=lambda n: fast[n]["count_exact"])
        if fast[top]["count_exact"] > two:
            return top, (f"no {scope} reaches the bar ({bar}); {top} still counts exactly in "
                         f"{fast[top]['count_exact']:.3f} of unseen frames against the two-stage detector's "
                         f"{two:.3f}, so it ships, marked as below the bar."), False
        return "two_stage", f"no {scope} qualifies ({bar}), so the two-stage detector ships.", False
    best = max(good, key=lambda n: good[n]["count_exact"])
    if good[best]["count_exact"] < two:
        return "two_stage", (f"the best qualifying student ({best}) counts exactly in {good[best]['count_exact']:.3f} "
                             f"of frames, below the two-stage detector's {two:.3f}, so the two-stage detector ships."), False
    return best, (f"{best} qualifies and counts exactly in {good[best]['count_exact']:.3f} of unseen frames, "
                  f"at least the two-stage detector's {two:.3f}."), True


def parse_board_ms(text: str) -> dict[str, float]:
    """`two_stage=1200,640=900,416=450` to {"two_stage": 1200.0, "640": 900.0, "416": 450.0}."""
    out: dict[str, float] = {}
    for part in filter(None, (p.strip() for p in text.split(","))):
        key, sep, value = part.partition("=")
        key = key.strip()
        try:
            ms = float(value)
        except ValueError:
            ms = -1.0
        if not sep or not key or ms < 0:
            raise ValueError(f"bad --board-ms entry {part!r}; expected <candidate>=<milliseconds>")
        if key in out:
            raise ValueError(f"--board-ms names {key!r} twice")
        out[key] = ms
    return out


def _fail(message: str) -> NoReturn:
    print(f"error: {message}", file=sys.stderr)
    raise SystemExit(2)


def _timing_key(candidate: str) -> str:
    return candidate.split(":", 1)[1] if candidate.startswith("student:") else candidate


def _build(candidate: str, models_dir: Path, classes: Sequence[str]):
    """The detector and, for a student, its card. Raises FileNotFoundError when files are missing."""
    from feeder_census.detectors import build_detector

    species = load_species()
    if candidate == "two_stage":
        return build_detector("two_stage", models_dir, species), None
    student_dir = models_dir / "student" / candidate.split(":", 1)[1]
    detector = build_detector("student", models_dir, species, student_dir=student_dir)
    card = json.loads((student_dir / "feeder.json").read_text())
    if card["classes"] != list(classes):
        raise ValueError(f"{candidate} was trained on classes {card['classes']}, the dataset has {list(classes)}")
    return detector, card


def _print_table(name: str, r: Mapping) -> None:
    board = f"{r['board_ms']:g} ms" if r["board_ms"] is not None else "not measured"
    print(f"\n{name}  ({r['detector']})  threshold {r['threshold']:.2f} ({r['threshold_source']})  board: {board}")
    print(f"  frames {r['frames']}, footage: {', '.join(r['footage'])}")
    print(f"  {'species':<28}{'precision':>10}{'recall':>8}{'boxes':>7}")
    rate = lambda v: f"{v:.2f}" if v is not None else "-"  # noqa: E731
    for key, m in r["per_species"].items():
        print(f"  {key:<28}{rate(m['precision']):>10}{rate(m['recall']):>8}{m['val_boxes']:>7}")
    print(f"  count_exact {r['count_exact']:.3f}")
    if r["val_boxes"] is not None:
        print("  validation boxes the threshold was based on: "
              + ", ".join(f"{k} {n}" for k, n in r["val_boxes"].items()))


def _promote(models_dir: Path, name: str, reason: str, r: Mapping, card: Mapping | None, detector,
             *, qualified: bool) -> None:
    metrics = {"frames": r["frames"], "footage": r["footage"], "count_exact": r["count_exact"],
               "per_species": r["per_species"], "labels": LABELS, "qualified": qualified}
    if name == "two_stage":
        shipped = {"name": detector.name, "kind": "two_stage", "species": list(detector.species)}
    else:
        student_dir = models_dir / "student"
        shutil.copyfile(student_dir / name.split(":", 1)[1] / "feeder.onnx", student_dir / "feeder.onnx")
        (student_dir / "feeder.json").write_text(json.dumps(
            {**card, "count_threshold": r["threshold"], "threshold_source": r["threshold_source"],
             "metrics": metrics}, indent=2) + "\n")
        shipped = {"name": card["name"], "kind": "student", "species": list(detector.species)}
    model_card = {**shipped, "count_threshold": r["threshold"], "threshold_source": r["threshold_source"],
                  "board_ms": r["board_ms"], "metrics": metrics,
                  "note": reason}
    (models_dir / "model_card.json").write_text(json.dumps(model_card, indent=2) + "\n")


def main(argv: list[str] | None = None) -> None:
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--dataset", type=Path, required=True)
    ap.add_argument("--candidates", nargs="+", required=True, help="two_stage and student:<imgsz>")
    ap.add_argument("--models-dir", type=Path, default=Path("models"))
    ap.add_argument("--board-ms", default="", help="two_stage=<ms>,640=<ms>,416=<ms>")
    ap.add_argument("--promote", action="store_true")
    args = ap.parse_args(argv)

    if "two_stage" not in args.candidates:
        ap.error("--candidates must include two_stage, the detector that ships when no student wins")
    for c in args.candidates:
        if c != "two_stage" and not (c.startswith("student:") and c[len("student:"):].isdigit()):
            ap.error(f"unknown candidate {c!r}; use two_stage or student:<imgsz>")
    try:
        timings = parse_board_ms(args.board_ms)
    except ValueError as e:
        ap.error(str(e))
    try:
        classes = json.loads((args.dataset / "classes.json").read_text())
    except FileNotFoundError:
        _fail(f"no classes.json in {args.dataset}; build the dataset with tools/build_dataset.py")
    if not list((args.dataset / "images" / "test").glob("*.jpg")):
        _fail(f"{args.dataset}/images/test has no frames: there is no held-out footage to measure on")

    built: dict[str, tuple] = {}
    for candidate in dict.fromkeys(args.candidates):
        try:
            built[candidate] = _build(candidate, args.models_dir, classes)
        except (FileNotFoundError, ValueError) as e:
            if candidate == "two_stage":
                _fail(str(e))
            print(f"skipping {candidate}: {e}", file=sys.stderr)
    if args.promote:
        missing = [c for c in built if _timing_key(c) not in timings]
        if missing:
            _fail(f"--promote needs a board timing for every evaluated candidate; missing: {', '.join(missing)}")

    results: dict[str, dict] = {}
    for candidate, (detector, _) in built.items():
        pick = candidate != "two_stage"
        results[candidate] = {
            "kind": "student" if pick else "two_stage", "detector": detector.name,
            "board_ms": timings.get(_timing_key(candidate)),
            **evaluate_candidate(detector, args.dataset, classes, pick),
        }
        _print_table(candidate, results[candidate])

    winner, reason, qualified = choose(results)
    win = results[winner]
    args.models_dir.mkdir(parents=True, exist_ok=True)
    (args.models_dir / "eval.json").write_text(json.dumps(
        {"dataset": str(args.dataset), "candidates": results, "timings": timings,
         "decision": {"ship": winner, "reason": reason, "promoted": args.promote, "qualified": qualified}}, indent=2) + "\n")
    if args.promote:
        _promote(args.models_dir, winner, reason, win, built[winner][1], built[winner][0], qualified=qualified)
    print(f"\n{reason}")
    print(f"SHIP: {winner} (count_exact={win['count_exact']:.3f}, threshold={win['threshold']:.2f})"
          + ("" if args.promote else " [not promoted]"))


if __name__ == "__main__":
    main()
