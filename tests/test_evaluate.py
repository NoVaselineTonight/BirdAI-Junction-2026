import cv2
import numpy as np
import pytest

from evaluate import (
    THRESHOLDS,
    Tally,
    build_curves,
    build_tallies,
    choose,
    evaluate_candidate,
    frame_is_exact,
    match_frame,
    parse_board_ms,
    pick_threshold,
    qualifies,
    student_threshold,
    read_truth,
    score_frames,
)
from feeder_census.detectors.student import MIN_SCORE
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

def pooled(**per_threshold):
    """Tallies by threshold: `pooled(t60={"great_tit": (500, 20)})` is {0.60: {"great_tit": Tally(500, 20, 0)}}."""
    return {float(k[1:]) / 100: {s: Tally(tp, fp, 0) for s, (tp, fp) in v.items()} for k, v in per_threshold.items()}


def test_pick_threshold_can_go_below_0_50_down_to_the_detectors_floor():
    tallies = pooled(t25={"great_tit": (60, 40)}, t30={"great_tit": (92, 8)}, t50={"great_tit": (95, 5)})
    assert pick_threshold(tallies, {"great_tit": 80}) == 0.30


def test_pick_threshold_takes_the_lowest_threshold_that_reaches_the_pooled_bar():
    tallies = pooled(t50={"great_tit": (80, 20), "blue_tit": (40, 10)},   # 120 / 150 = 0.80
                     t55={"great_tit": (80, 8), "blue_tit": (40, 4)},     # 120 / 132 = 0.909
                     t60={"great_tit": (70, 1), "blue_tit": (30, 0)})     # later and better, but not the lowest
    assert pick_threshold(tallies, {"great_tit": 80, "blue_tit": 40}) == 0.55


def test_a_small_judged_class_stuck_below_the_bar_does_not_block_the_pick():
    # great_tit 500 / 520 = 0.96, jay 17 / 21 = 0.81 on its own; pooled 517 / 541 = 0.956
    tallies = pooled(t50={"great_tit": (520, 120), "jay": (20, 20)},
                     t60={"great_tit": (500, 20), "jay": (17, 4)},
                     t90={"great_tit": (200, 5), "jay": (6, 4)})
    assert pick_threshold(tallies, {"great_tit": 500, "jay": 23}) == 0.60


def test_pick_threshold_pools_hits_and_false_alarms_exactly_at_the_bar():
    tallies = pooled(t50={"a": (45, 3), "b": (45, 7)})  # 90 / 100 = 0.90 exactly
    assert pick_threshold(tallies, {"a": 50, "b": 50}) == 0.50


def test_pick_threshold_falls_back_to_0_90_when_pooled_precision_is_below_the_bar_everywhere():
    tallies = pooled(t50={"great_tit": (50, 50)}, t70={"great_tit": (89, 11)}, t90={"great_tit": (60, 7)})
    assert pick_threshold(tallies, {"great_tit": 80}) == 0.90
    # 0.90 is also what the fallback returns when the 0.90 entry itself is below the bar
    assert pick_threshold(pooled(t50={"great_tit": (1, 1)}), {"great_tit": 80}) == 0.90


def test_pick_threshold_leaves_species_with_few_boxes_out_of_the_pool():
    # jay (3 boxes) has 100 false alarms; pooled with it the precision would be 0.46, without it 0.95
    tallies = pooled(t50={"great_tit": (95, 5), "jay": (3, 100)})
    assert pick_threshold(tallies, {"great_tit": 80, "jay": 3}) == 0.50


def test_pick_threshold_with_nothing_predicted_does_not_qualify_that_threshold():
    tallies = pooled(t50={"great_tit": (0, 0)}, t55={"great_tit": (0, 0), "blue_tit": (0, 0)},
                     t60={"great_tit": (19, 1)})
    assert pick_threshold(tallies, {"great_tit": 80, "blue_tit": 40}) == 0.60
    assert pick_threshold(pooled(t50={"great_tit": (0, 0)}), {"great_tit": 80}) == 0.90


def test_pick_threshold_without_any_species_with_enough_boxes_is_0_90():
    assert pick_threshold(pooled(t50={"jay": (10, 0)}), {"jay": 3}) == 0.90


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


def test_the_grid_runs_from_the_detectors_own_floor_to_0_90_in_steps_of_0_05():
    assert THRESHOLDS[0] == MIN_SCORE == 0.25
    assert THRESHOLDS[-1] == 0.90
    assert len(THRESHOLDS) == 14
    assert THRESHOLDS == tuple(round(0.25 + 0.05 * i, 2) for i in range(14))
    assert all(round(b - a, 2) == 0.05 for a, b in zip(THRESHOLDS, THRESHOLDS[1:]))


def test_build_curves_gives_precision_and_recall_per_threshold():
    curves = build_curves(frames_for_curves(), ["great_tit"])["great_tit"]
    assert [t for t, _, _ in curves] == list(THRESHOLDS)
    at = {t: (p, r) for t, p, r in curves}
    assert at[0.25] == (pytest.approx(2 / 3), 1.0)   # no detection scores under 0.50, so 0.25 sees the same as 0.50
    assert at[0.50] == (pytest.approx(2 / 3), 1.0)   # tp 2, fp 1
    assert at[0.60] == (pytest.approx(1 / 2), 0.5)   # tp 1, fp 1, fn 1
    assert at[0.75] == (1.0, 0.5)                    # the false alarm is gone
    assert at[0.90] == (1.0, 0.5)


def test_build_curves_with_no_detections_has_zero_precision_and_recall():
    curves = build_curves([([], [det("great_tit", A)])], ["great_tit"])
    assert all(p == 0.0 and r == 0.0 for _, p, r in curves["great_tit"])


def test_pick_threshold_on_tallies_built_from_detections():
    frames = frames_for_curves()
    tallies = build_tallies(frames, ["great_tit"])
    assert list(tallies) == list(THRESHOLDS)
    assert tallies[0.50]["great_tit"] == Tally(tp=2, fp=1, fn=0) and tallies[0.60]["great_tit"] == Tally(1, 1, 1)
    assert pick_threshold(tallies, {"great_tit": 20}) == 0.75


def test_the_default_grid_picks_0_30_when_precision_first_reaches_the_bar_there():
    # 10 frames, one bird each. The right name scores 0.30, a wrong-name box scores 0.28.
    # At 0.25 both count: 10 right, 10 false alarms, precision 0.5. At 0.30 only the right one does: 1.0.
    # Nothing scores 0.50 or more, so on the old grid (0.50 and up) nothing is named and the pick falls back to 0.90.
    frames = [([det("great_tit", A, 0.30), det("great_tit", B, 0.28)], [det("great_tit", A, 1.0)])
              for _ in range(10)]
    tallies = build_tallies(frames, ["great_tit"])  # the default grid decides which thresholds exist
    assert tallies[0.25]["great_tit"] == Tally(tp=10, fp=10, fn=0)
    assert tallies[0.30]["great_tit"] == Tally(tp=10, fp=0, fn=0)
    assert student_threshold(tallies, {"great_tit": 80}, default=0.60) == (0.30, PICKED)


def test_score_frames_reports_per_species_numbers_at_one_threshold():
    frames = frames_for_curves() + [([], [])]
    m = score_frames(frames, 0.60, ["great_tit", "blue_tit"])
    assert m["frames"] == 3
    # frame 1: one hit and one false alarm (not exact); frame 2: miss (not exact); frame 3: empty (exact)
    assert m["count_exact"] == pytest.approx(1 / 3)
    assert m["per_species"]["great_tit"] == {"precision": 0.5, "recall": 0.5, "val_boxes": 2}
    # nothing predicted and nothing to find: both rates are unknown, not zero
    assert m["per_species"]["blue_tit"] == {"precision": None, "recall": None, "val_boxes": 0}


def test_an_absent_species_has_unknown_recall_and_does_not_qualify():
    frames = [([det("great_tit", A)], [det("great_tit", A)])] * 3
    per = score_frames(frames, 0.6, ["great_tit", "blue_tit"])["per_species"]
    assert per["great_tit"] == {"precision": 1.0, "recall": 1.0, "val_boxes": 3}
    assert per["blue_tit"]["recall"] is None
    # a detector that names an absent species: precision is a real 0.0, recall is still unknown
    per = score_frames([([det("blue_tit", A)], [])], 0.6, ["blue_tit"])["per_species"]
    assert per["blue_tit"] == {"precision": 0.0, "recall": None, "val_boxes": 0}


def test_a_species_never_predicted_has_unknown_precision_and_real_zero_recall():
    per = score_frames([([], [det("great_tit", A)])], 0.6, ["great_tit"])["per_species"]
    assert per["great_tit"] == {"precision": None, "recall": 0.0, "val_boxes": 1}


def test_qualifies_counts_a_species_only_when_both_rates_are_known():
    unknown = {"precision": None, "recall": 0.9, "val_boxes": 5}
    no_truth = {"precision": 0.95, "recall": None, "val_boxes": 0}
    assert not qualifies({"a": entry(0.95, 0.8), "b": entry(0.95, 0.8), "c": unknown, "d": no_truth})
    assert qualifies({"a": entry(0.95, 0.8), "b": entry(0.95, 0.8), "c": entry(0.95, 0.8), "d": no_truth})


def test_unknown_rates_reach_the_card_as_json_null(tmp_path):
    import json
    from evaluate import _promote
    per = score_frames([([], [])], 0.6, ["great_tit"])["per_species"]
    r = {"frames": 1, "footage": ["demo"], "count_exact": 1.0, "per_species": per, "threshold": 0.6,
         "threshold_source": "fixed", "board_ms": None}
    _promote(tmp_path, "two_stage", "because", r, None, CountingDetector(), qualified=False)
    card = json.loads((tmp_path / "model_card.json").read_text())
    assert card["metrics"]["per_species"]["great_tit"] == {"precision": None, "recall": None, "val_boxes": 0}
    assert card["threshold_source"] == "fixed"
    assert card["metrics"]["qualified"] is False


def ok_tallies():
    return pooled(**{f"t{round(t * 100)}": {"great_tit": (95, 5)} for t in THRESHOLDS})


PICKED = ("picked on validation footage: the lowest threshold where at least 90% of named birds were right, "
          "all judged species together")
FALLBACK = ("fallback 0.90: no threshold reached 0.90 precision on validation footage, "
            "all judged species together")


def test_student_threshold_picked_on_validation_footage():
    below = {t: {"great_tit": Tally(85, 15, 0)} for t in THRESHOLDS if t <= 0.50}
    tallies = {**ok_tallies(), **below, 0.55: {"great_tit": Tally(91, 9, 0)}}
    assert student_threshold(tallies, {"great_tit": 80}, default=0.60) == (0.55, PICKED)


def test_student_threshold_picks_0_30_when_precision_first_reaches_the_bar_there():
    tallies = {**ok_tallies(), 0.25: {"great_tit": Tally(80, 20, 0)}, 0.30: {"great_tit": Tally(91, 9, 0)}}
    assert student_threshold(tallies, {"great_tit": 80}, default=0.60) == (0.30, PICKED)


def test_student_threshold_at_exactly_0_90_is_still_a_pick_when_it_reaches_the_bar():
    tallies = {t: {"great_tit": Tally(50, 50, 0)} for t in (0.5, 0.55, 0.6, 0.65, 0.7, 0.75, 0.8, 0.85)}
    tallies[0.90] = {"great_tit": Tally(95, 5, 0)}
    assert student_threshold(tallies, {"great_tit": 80}, default=0.60) == (0.90, PICKED)


def test_student_threshold_fallback_when_no_threshold_reaches_the_bar():
    tallies = pooled(t50={"great_tit": (50, 50)}, t90={"great_tit": (60, 40)})
    assert student_threshold(tallies, {"great_tit": 80}, default=0.60) == (0.90, FALLBACK)


def test_student_threshold_is_picked_when_a_small_class_alone_would_have_failed():
    tallies = pooled(t60={"great_tit": (500, 20), "jay": (17, 4)})
    assert student_threshold(tallies, {"great_tit": 500, "jay": 23}, default=0.60) == (0.60, PICKED)


def test_student_threshold_keeps_the_default_when_val_has_too_few_boxes():
    assert student_threshold(ok_tallies(), {"great_tit": 19}, default=0.60) == (
        0.60, "default: too few validation boxes to pick")
    assert student_threshold({}, {}, default=0.60) == (0.60, "default: too few validation boxes to pick")


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
    name, reason, qualified = choose(results)
    assert name == "student:416" and "416" in reason and isinstance(reason, str)
    assert qualified is True


def test_choose_ships_two_stage_when_no_student_qualifies_and_none_counts_better():
    results = {"two_stage": result("two_stage", 0.242),
               "student:640": result("student", 0.20, qualifying=False)}
    name, reason, qualified = choose(results)
    assert name == "two_stage" and "no student qualifies" in reason and "two-stage detector ships" in reason
    assert qualified is False


def test_choose_ships_two_stage_when_a_non_qualifying_student_only_ties_it():
    results = {"two_stage": result("two_stage", 0.50),
               "student:640": result("student", 0.50, qualifying=False)}
    name, reason, qualified = choose(results)
    assert name == "two_stage" and qualified is False


def test_choose_ships_the_better_counting_student_below_the_bar_and_says_so():
    results = {"two_stage": result("two_stage", 0.242),
               "student:640": result("student", 0.40, qualifying=False),
               "student:416": result("student", 0.570, qualifying=False)}
    name, reason, qualified = choose(results)
    assert name == "student:416" and qualified is False
    assert reason == ("no student reaches the bar (at least 3 species with precision 0.90 and recall 0.50 on unseen "
                      "footage); student:416 still counts exactly in 0.570 of unseen frames against the two-stage "
                      "detector's 0.242, so it ships, marked as below the bar.")


def test_choose_below_the_bar_only_considers_students_fast_enough():
    results = {"two_stage": result("two_stage", 0.242, board_ms=2000.0),
               "student:640": result("student", 0.90, board_ms=1600.0, qualifying=False),
               "student:416": result("student", 0.30, board_ms=900.0, qualifying=False)}
    name, reason, qualified = choose(results)
    assert name == "student:416" and "below the bar" in reason and qualified is False


def test_choose_below_the_bar_says_fast_enough_when_a_qualifying_student_is_too_slow():
    results = {"two_stage": result("two_stage", 0.242, board_ms=2000.0),
               "student:640": result("student", 0.90, board_ms=1600.0),                      # qualifies, too slow
               "student:416": result("student", 0.570, board_ms=900.0, qualifying=False)}
    name, reason, qualified = choose(results)
    assert name == "student:416" and qualified is False
    assert "no student fast enough for the board reaches the bar (" in reason and "below the bar" in reason


def test_choose_two_stage_says_fast_enough_when_a_qualifying_student_is_too_slow():
    results = {"two_stage": result("two_stage", 0.242, board_ms=2000.0),
               "student:640": result("student", 0.90, board_ms=1600.0),                      # qualifies, too slow
               "student:416": result("student", 0.20, board_ms=900.0, qualifying=False)}
    name, reason, qualified = choose(results)
    assert name == "two_stage" and qualified is False
    assert "no student fast enough for the board qualifies (" in reason and "two-stage detector ships" in reason


def test_choose_skips_a_student_slower_than_1500_ms():
    results = {"two_stage": result("two_stage", 0.50, board_ms=2000.0),
               "student:640": result("student", 0.99, board_ms=1501.0),
               "student:416": result("student", 0.80, board_ms=1500.0)}
    name, _, qualified = choose(results)
    assert name == "student:416" and qualified is True
    results["student:416"]["board_ms"] = 1600.0
    name, reason, qualified = choose(results)
    assert name == "two_stage" and "1500" in reason and qualified is False


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
    assert out["threshold_source"] == "fixed" and out["val_boxes"] is None
    assert out["footage"] == ["demo"]
    assert out["count_exact"] == 0.5  # exact on the first frame, a false alarm on the empty one
    assert out["per_species"]["great_tit"] == {"precision": 0.5, "recall": 1.0, "val_boxes": 1}


def test_evaluate_candidate_picks_the_threshold_on_val_and_reports_test(tmp_path):
    dataset, classes = make_dataset(tmp_path)
    detector = CountingDetector()
    out = evaluate_candidate(detector, dataset, classes, pick=True, min_val_boxes=1)
    assert detector.calls == 3  # val once, test twice
    # on val the single bird is found at every threshold, so the lowest one, the detector's floor, is picked
    assert out["threshold"] == MIN_SCORE
    assert out["threshold_source"] == PICKED
    assert out["val_boxes"] == {"great_tit": 1}
    assert out["frames"] == 2


def test_evaluate_candidate_keeps_the_card_threshold_when_val_is_too_thin(tmp_path):
    dataset, classes = make_dataset(tmp_path)
    out = evaluate_candidate(CountingDetector(), dataset, classes, pick=True)  # 1 val box, 20 needed
    assert out["threshold"] == 0.6
    assert out["threshold_source"] == "default: too few validation boxes to pick"
    assert out["val_boxes"] == {"great_tit": 1}


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
            "threshold_source": "picked on validation footage" if pick else "fixed",
            "val_boxes": {"a": 30} if pick else None,
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
    assert card["threshold_source"] == "picked on validation footage"
    assert card["metrics"]["labels"] == "teacher models, then checked by a second AI model; samples reviewed by an AI assistant, not by a person"
    assert card["metrics"]["footage"] == ["demo"] and card["count_threshold"] == 0.65
    assert (models / "student" / "feeder.onnx").read_bytes() == b"onnx"
    student = json.loads((models / "student" / "feeder.json").read_text())
    assert student["count_threshold"] == card["count_threshold"]
    assert student["threshold_source"] == "picked on validation footage"
    decision = json.loads((models / "eval.json").read_text())["decision"]
    assert decision["ship"] == "student:640" and decision["qualified"] is True
    assert card["metrics"]["qualified"] is True and student["metrics"]["qualified"] is True


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


def test_main_promotes_a_below_the_bar_student_and_records_it(tmp_path, monkeypatch, capsys):
    import json
    import evaluate
    dataset, _ = make_dataset(tmp_path / "dataset")
    make_dataset_classes(dataset)

    def weak_evaluate(detector, dataset, classes, pick):
        out = fake_evaluate(detector, dataset, classes, pick)
        if pick:  # a student that counts better than the two-stage detector but has only one good species
            out["count_exact"] = 0.57
            out["per_species"] = {**out["per_species"], "b": {"precision": 0.5, "recall": 0.2, "val_boxes": 30},
                                  "c": {"precision": 0.5, "recall": 0.2, "val_boxes": 30}}
        else:
            out["count_exact"] = 0.242
        return out

    monkeypatch.setattr(evaluate, "evaluate_candidate", weak_evaluate)
    models = tmp_path / "models"
    monkeypatch.setattr(evaluate, "_build", fake_build(models))
    evaluate.main(["--dataset", str(dataset), "--candidates", "two_stage", "student:640",
                   "--models-dir", str(models), "--board-ms", "two_stage=900,640=700", "--promote"])
    decision = json.loads((models / "eval.json").read_text())["decision"]
    assert decision["ship"] == "student:640" and decision["qualified"] is False
    assert "below the bar" in decision["reason"]
    card = json.loads((models / "model_card.json").read_text())
    assert card["kind"] == "student" and card["metrics"]["qualified"] is False
    assert json.loads((models / "student" / "feeder.json").read_text())["metrics"]["qualified"] is False


def test_main_records_qualified_false_when_the_two_stage_detector_ships(tmp_path, monkeypatch, capsys):
    import json
    (tmp_path / "dataset").mkdir()
    make_dataset_classes(tmp_path / "dataset")
    models, _ = run_main(tmp_path, monkeypatch, capsys, ["--board-ms", "two_stage=900,640=2000", "--promote"])
    assert json.loads((models / "eval.json").read_text())["decision"] == {
        "ship": "two_stage", "reason": json.loads((models / "model_card.json").read_text())["note"],
        "promoted": True, "qualified": False}
    assert json.loads((models / "model_card.json").read_text())["metrics"]["qualified"] is False
