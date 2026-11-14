import cv2
import numpy as np
import pytest

from evaluate import (
    Tally,
    build_curves,
    choose,
    evaluate_candidate,
    frame_is_exact,
    match_frame,
    parse_board_ms,
    pick_threshold,
    qualifies,
    read_truth,
    score_frames,
)
from feeder_census.types import UNIDENTIFIED, Detection

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


def test_pick_threshold_without_any_species_with_enough_boxes_is_0_90():
    assert pick_threshold({"jay": [(0.50, 1.0, 1.0)]}, {"jay": 3}) == 0.90


def test_match_frame_is_one_to_one_and_ignores_unidentified_predictions():
    truth = [det("great_tit", A)]
    pred = [det("great_tit", A, 0.9), det("great_tit", A, 0.8), det(UNIDENTIFIED, B)]
    r = match_frame(pred, truth)
    assert r == {"great_tit": Tally(tp=1, fp=1, fn=0)}


def test_match_frame_leaves_unidentified_truth_out_of_the_misses():
    assert match_frame([], [det(UNIDENTIFIED, A)]) == {}


def test_read_truth_gives_pixel_boxes_and_names(tmp_path):
    label = tmp_path / "x.txt"
    label.write_text("0 0.5 0.5 0.5 0.5\n\n1 0.25 0.5 0.1 0.2\n")
    truth = read_truth(label, (400, 200), ["great_tit", UNIDENTIFIED])
    assert truth == [det("great_tit", (100, 50, 300, 150), 1.0), det(UNIDENTIFIED, (80, 80, 120, 120), 1.0)]


def test_read_truth_of_an_empty_label_file_is_an_empty_frame(tmp_path):
    label = tmp_path / "x.txt"
    label.write_text("")
    assert read_truth(label, (400, 200), ["great_tit", UNIDENTIFIED]) == []


SPECIES = ["great_tit", "blue_tit"]


def test_frame_is_exact_when_every_species_count_matches():
    truth = [det("great_tit", A), det("great_tit", B)]
    assert frame_is_exact([det("great_tit", A), det("great_tit", B)], truth, 0.6, SPECIES)
    assert not frame_is_exact([det("great_tit", A)], truth, 0.6, SPECIES)
    assert not frame_is_exact([det("great_tit", A), det("great_tit", B), det("blue_tit", (400, 400, 450, 450))],
                              truth, 0.6, SPECIES)


def test_frame_is_exact_only_counts_detections_at_or_above_the_threshold():
    truth = [det("great_tit", A)]
    assert frame_is_exact([det("great_tit", A, 0.6), det("blue_tit", B, 0.59)], truth, 0.6, SPECIES)
    assert not frame_is_exact([det("great_tit", A, 0.59)], truth, 0.6, SPECIES)


def test_frame_is_exact_drops_detections_on_unidentified_truth():
    truth = [det("great_tit", A), det(UNIDENTIFIED, B)]
    assert frame_is_exact([det("great_tit", A), det("blue_tit", B)], truth, 0.6, SPECIES)


def test_frame_is_exact_ignores_species_that_are_not_dataset_classes():
    assert frame_is_exact([det("jay", A)], [], 0.6, SPECIES)
    assert frame_is_exact([], [], 0.6, SPECIES)


def test_frame_is_exact_with_no_bird_and_a_false_alarm_is_not_exact():
    assert not frame_is_exact([det("blue_tit", A)], [], 0.6, SPECIES)


def frames_for_curves():
    """Two frames, one bird each. The wrong-name detection has confidence 0.72, the right one 0.9 and 0.55."""
    return [
        ([det("great_tit", A, 0.9), det("great_tit", B, 0.72)], [det("great_tit", A, 1.0)]),
        ([det("great_tit", A, 0.55)], [det("great_tit", A, 1.0)]),
    ]


def test_build_curves_gives_precision_and_recall_per_threshold():
    curves = build_curves(frames_for_curves(), ["great_tit"])["great_tit"]
    assert [t for t, _, _ in curves] == [0.50, 0.55, 0.60, 0.65, 0.70, 0.75, 0.80, 0.85, 0.90]
    at = {t: (p, r) for t, p, r in curves}
    assert at[0.50] == (pytest.approx(2 / 3), 1.0)   # tp 2, fp 1
    assert at[0.60] == (pytest.approx(1 / 2), 0.5)   # tp 1, fp 1, fn 1
    assert at[0.75] == (1.0, 0.5)                    # the false alarm is gone
    assert at[0.90] == (1.0, 0.5)


def test_build_curves_with_no_detections_has_zero_precision_and_recall():
    curves = build_curves([([], [det("great_tit", A)])], ["great_tit"])
    assert all(p == 0.0 and r == 0.0 for _, p, r in curves["great_tit"])


def test_pick_threshold_on_curves_built_from_detections():
    frames = frames_for_curves()
    curves = build_curves(frames, ["great_tit"])
    assert pick_threshold(curves, {"great_tit": 20}) == 0.75


def test_score_frames_reports_per_species_numbers_at_one_threshold():
    frames = frames_for_curves() + [([], [])]
    m = score_frames(frames, 0.60, ["great_tit", "blue_tit"])
    assert m["frames"] == 3
    # frame 1: one hit and one false alarm (not exact); frame 2: miss (not exact); frame 3: empty (exact)
    assert m["count_exact"] == pytest.approx(1 / 3)
    assert m["per_species"]["great_tit"] == {"precision": 0.5, "recall": 0.5, "val_boxes": 2}
    assert m["per_species"]["blue_tit"] == {"precision": 0.0, "recall": 0.0, "val_boxes": 0}


def entry(precision, recall):
    return {"precision": precision, "recall": recall, "val_boxes": 50}


def result(kind, count_exact, board_ms=800.0, qualifying=True, threshold=0.6):
    good, bad = entry(0.95, 0.8), entry(0.5, 0.2)
    species = {"a": good, "b": good, "c": good, "d": bad} if qualifying else {"a": good, "b": good, "c": bad}
    return {"kind": kind, "count_exact": count_exact, "board_ms": board_ms, "threshold": threshold,
            "per_species": species}


def test_qualifies_needs_three_species_with_both_precision_and_recall():
    assert qualifies(result("student", 0.9)["per_species"])
    assert not qualifies(result("student", 0.9, qualifying=False)["per_species"])
    # precision is fine but recall is not: does not count
    assert not qualifies({k: entry(0.95, 0.49) for k in "abc"})
    assert qualifies({k: entry(0.90, 0.50) for k in "abc"})


def test_choose_picks_the_qualifying_student_with_the_highest_count_exact():
    results = {"two_stage": result("two_stage", 0.70), "student:640": result("student", 0.80),
               "student:416": result("student", 0.85)}
    name, reason = choose(results)
    assert name == "student:416" and "416" in reason and isinstance(reason, str)


def test_choose_ships_two_stage_when_no_student_qualifies():
    results = {"two_stage": result("two_stage", 0.50),
               "student:640": result("student", 0.99, qualifying=False)}
    name, reason = choose(results)
    assert name == "two_stage" and "qualif" in reason


def test_choose_skips_a_student_slower_than_1500_ms():
    results = {"two_stage": result("two_stage", 0.50, board_ms=2000.0),
               "student:640": result("student", 0.99, board_ms=1501.0),
               "student:416": result("student", 0.80, board_ms=1500.0)}
    name, _ = choose(results)
    assert name == "student:416"
    results["student:416"]["board_ms"] = 1600.0
    name, reason = choose(results)
    assert name == "two_stage" and "1500" in reason


def test_choose_ships_two_stage_when_the_student_is_below_it():
    results = {"two_stage": result("two_stage", 0.80), "student:640": result("student", 0.79)}
    assert choose(results)[0] == "two_stage"


def test_choose_lets_a_student_that_ties_two_stage_ship():
    results = {"two_stage": result("two_stage", 0.80), "student:640": result("student", 0.80)}
    assert choose(results)[0] == "student:640"


def test_choose_without_timings_treats_students_as_eligible():
    results = {"two_stage": result("two_stage", 0.5, board_ms=None),
               "student:640": result("student", 0.9, board_ms=None)}
    assert choose(results)[0] == "student:640"


def test_parse_board_ms():
    assert parse_board_ms("two_stage=1200,640=900.5,416=450") == {"two_stage": 1200.0, "640": 900.5, "416": 450.0}
    assert parse_board_ms("") == {}


@pytest.mark.parametrize("text", ["640", "640=fast", "640=-3", "=5", "640=1,640=2"])
def test_parse_board_ms_rejects_bad_input(text):
    with pytest.raises(ValueError):
        parse_board_ms(text)


class CountingDetector:
    """Always sees one great tit in the top-left quarter; records how many frames it was shown."""

    name = "fake"
    species = ("great_tit",)
    count_threshold = 0.6

    def __init__(self):
        self.calls = 0

    def detect(self, frame_bgr):
        self.calls += 1
        h, w = frame_bgr.shape[:2]
        return [Detection("great_tit", 0.8, (0.0, 0.0, w / 2, h / 2))]


def make_dataset(tmp_path):
    classes = ["great_tit", UNIDENTIFIED]
    frames = {"val": ["train1_00000000"], "test": ["demo_00000000", "demo_00001000"]}
    for split, stems in frames.items():
        (tmp_path / "images" / split).mkdir(parents=True)
        (tmp_path / "labels" / split).mkdir(parents=True)
        for stem in stems:
            cv2.imwrite(str(tmp_path / "images" / split / f"{stem}.jpg"), np.full((100, 200, 3), 90, np.uint8))
            # the first test frame has the bird the detector sees, the second is empty
            bird = "0 0.25 0.25 0.5 0.5\n" if stem != "demo_00001000" else ""
            (tmp_path / "labels" / split / f"{stem}.txt").write_text(bird)
    return tmp_path, classes


def test_evaluate_candidate_with_a_fixed_threshold_never_looks_at_val(tmp_path):
    dataset, classes = make_dataset(tmp_path)
    detector = CountingDetector()
    out = evaluate_candidate(detector, dataset, classes, pick=False)
    assert detector.calls == 2  # the two test frames only
    assert out["threshold"] == 0.6 and out["frames"] == 2
    assert out["footage"] == ["demo"]
    assert out["count_exact"] == 0.5  # exact on the first frame, a false alarm on the empty one
    assert out["per_species"]["great_tit"] == {"precision": 0.5, "recall": 1.0, "val_boxes": 1}


def test_evaluate_candidate_picks_the_threshold_on_val_and_reports_test(tmp_path):
    dataset, classes = make_dataset(tmp_path)
    detector = CountingDetector()
    out = evaluate_candidate(detector, dataset, classes, pick=True, min_val_boxes=1)
    assert detector.calls == 3  # val once, test twice
    # on val the single bird is found at every threshold, so the lowest one is picked
    assert out["threshold"] == 0.50
    assert out["frames"] == 2


class FakeStudent(CountingDetector):
    name = "Feeder student 640"


def fake_build(models_dir):
    """Stands in for _build: a two-stage and a student detector that both see the same bird, no model files."""
    import json as _json
    card = {"name": "Feeder student 640", "kind": "student", "classes": ["great_tit", UNIDENTIFIED],
            "count_threshold": 0.6, "metrics": None}
    student_dir = models_dir / "student" / "640"
    student_dir.mkdir(parents=True)
    (student_dir / "feeder.onnx").write_bytes(b"onnx")

    def build(candidate, models_dir, classes):
        if candidate == "two_stage":
            detector = CountingDetector()
            detector.name = "Two-stage"
            return detector, None
        return FakeStudent(), card

    return build


def fake_evaluate(detector, dataset, classes, pick):
    """Canned numbers: the student qualifies and beats the two-stage detector."""
    good = {k: {"precision": 0.95, "recall": 0.8, "val_boxes": 30} for k in ("a", "b", "c")}
    return {"threshold": 0.65 if pick else 0.6, "footage": ["demo"], "frames": 2,
            "count_exact": 0.9 if pick else 0.7, "per_species": good}


def run_main(tmp_path, monkeypatch, capsys, extra):
    import evaluate
    dataset, _ = make_dataset(tmp_path / "dataset")
    models = tmp_path / "models"
    monkeypatch.setattr(evaluate, "_build", fake_build(models))
    monkeypatch.setattr(evaluate, "evaluate_candidate", fake_evaluate)
    evaluate.main(["--dataset", str(dataset), "--candidates", "two_stage", "student:640",
                   "--models-dir", str(models), *extra])
    return models, capsys.readouterr().out.strip().splitlines()[-1]


def make_dataset_classes(dataset):
    (dataset / "classes.json").write_text('["great_tit", "unidentified"]')


def test_main_promotes_the_winning_student(tmp_path, monkeypatch, capsys):
    import json
    (tmp_path / "dataset").mkdir()
    make_dataset_classes(tmp_path / "dataset")
    models, last = run_main(tmp_path, monkeypatch, capsys, ["--board-ms", "two_stage=900,640=700", "--promote"])
    assert last.startswith("SHIP: student:640 (count_exact=") and "not promoted" not in last
    card = json.loads((models / "model_card.json").read_text())
    assert card["kind"] == "student" and card["board_ms"] == 700.0 and card["note"]
    assert card["metrics"]["labels"] == "teacher models, checked by a person"
    assert card["metrics"]["footage"] == ["demo"] and card["count_threshold"] == 0.65
    assert (models / "student" / "feeder.onnx").read_bytes() == b"onnx"
    assert json.loads((models / "student" / "feeder.json").read_text())["count_threshold"] == card["count_threshold"]
    assert json.loads((models / "eval.json").read_text())["decision"]["ship"] == "student:640"


def test_main_without_promote_writes_only_eval_json(tmp_path, monkeypatch, capsys):
    (tmp_path / "dataset").mkdir()
    make_dataset_classes(tmp_path / "dataset")
    models, last = run_main(tmp_path, monkeypatch, capsys, [])
    assert last.endswith("[not promoted]")
    assert (models / "eval.json").is_file()
    assert not (models / "model_card.json").exists() and not (models / "student" / "feeder.json").exists()


def test_main_promote_without_a_timing_for_every_candidate_exits_2(tmp_path, monkeypatch, capsys):
    (tmp_path / "dataset").mkdir()
    make_dataset_classes(tmp_path / "dataset")
    with pytest.raises(SystemExit) as stop:
        run_main(tmp_path, monkeypatch, capsys, ["--board-ms", "two_stage=900", "--promote"])
    assert stop.value.code == 2
    assert "student:640" in capsys.readouterr().err
