import threading
import time
from datetime import date, datetime

import numpy as np
import pytest

from feeder_census.camera import SimulatedCamera
from feeder_census.config import Settings
from feeder_census.detectors.scripted import ScriptedDetector
from feeder_census.pipeline import Pipeline
from feeder_census.store import Store

SPECIES = ["great_tit", "blue_tit"]
NAMES = {"great_tit": "Great Tit", "blue_tit": "Blue Tit"}
GT = {"species": "great_tit", "confidence": 0.9, "box": [10, 10, 60, 60]}


class CountingDetector(ScriptedDetector):
    calls = 0

    def detect(self, frame_bgr):
        self.calls += 1
        return super().detect(frame_bgr)


def build(tmp_path, make_video, frames, camera=None, inline=True, **settings):
    detector = CountingDetector({"species": SPECIES, "frames": frames})
    store = Store(tmp_path / "census.db", detector.species)
    camera = camera or SimulatedCamera([make_video(seconds=2.0, fps=10)], realtime=False)
    settings = Settings(evidence_dir=tmp_path / "evidence", **settings)
    return Pipeline(camera, detector, store, settings, NAMES, inline=inline), store


def run_detections(p, n):
    for _ in range(10_000):
        if p.detector.calls >= n:
            return
        p.step()
    raise AssertionError("pipeline never ran the detections")


class JumpingCamera:
    """Footage time jumps 30 s between reads, as if the detector made the reader late."""

    def __init__(self):
        self._t = -30.0

    def read(self):
        self._t += 30.0
        return np.zeros((240, 320, 3), np.uint8), self._t

    def close(self):
        pass


def test_pipeline_records_the_confirmed_maximum_and_effort(tmp_path, make_video):
    p, store = build(tmp_path, make_video, [[GT, GT], [GT, GT], [GT]])
    run_detections(p, 3)
    (hour,) = store.hours(date(2026, 11, 1))
    assert hour.counts == {"great_tit": 2, "blue_tit": 0}
    assert hour.hours_watched == pytest.approx(3 * 2.0 * 60 / 3600)


def test_pipeline_saves_one_evidence_photo_per_day_record(tmp_path, make_video):
    p, store = build(tmp_path, make_video, [[GT, GT], [GT, GT], [GT]])
    run_detections(p, 3)
    (e,) = store.evidence()
    assert (e.species, e.count, e.confidence) == ("great_tit", 2, pytest.approx(0.9))
    assert (tmp_path / "evidence" / "2026-11-01" / "great_tit.jpg").stat().st_size > 1000


def test_pipeline_resumes_clock_after_restart(tmp_path, make_video):
    frames = [[GT, GT], [GT, GT], [GT]]
    p, store = build(tmp_path, make_video, frames)
    run_detections(p, 3)
    first_total = store.total_watched_s()
    p2, store2 = build(tmp_path, make_video, frames)
    run_detections(p2, 1)
    assert store2.total_watched_s() == pytest.approx(first_total + 120)
    assert p2.live().sim_time > p.live().sim_time


def test_slow_detector_drops_frames_and_caps_effort(tmp_path, make_video):
    p, store = build(tmp_path, make_video, [[GT]], camera=JumpingCamera())
    run_detections(p, 2)
    assert store.total_watched_s() == pytest.approx(120 + 10 * 60)


def test_roi_boxes_come_back_in_full_frame_coordinates(tmp_path, make_video):
    box = {"species": "great_tit", "confidence": 0.9, "box": [0, 0, 20, 20]}
    p, _ = build(tmp_path, make_video, [[box]], roi=(0.5, 0.5, 0.5, 0.5))
    run_detections(p, 1)
    assert p.last_detections[0].box == (160, 120, 180, 140)


def test_live_state_reports_unidentified_birds_without_counting_them(tmp_path, make_video):
    unknown = {"species": "unidentified", "confidence": 0.8, "box": [100, 100, 140, 140]}
    p, _ = build(tmp_path, make_video, [[GT, unknown]])
    run_detections(p, 1)
    assert p.live().now == {"great_tit": 1, "blue_tit": 0} and p.live().unidentified == 1


def test_live_state_before_the_first_frame_is_empty(tmp_path, make_video):
    p, store = build(tmp_path, make_video, [[GT]])
    state = p.live()
    assert state.jpeg == b"" and state.unidentified == 0 and state.detector == "scripted"
    assert state.now == state.confirmed == {"great_tit": 0, "blue_tit": 0}
    assert state.visits_today == state.day_max == {"great_tit": 0, "blue_tit": 0}
    assert state.sim_time == datetime(2026, 11, 1, 8, 0)


def test_live_state_carries_a_preview_jpeg_once_a_frame_was_read(tmp_path, make_video):
    p, _ = build(tmp_path, make_video, [[GT]])
    p.step()
    assert p.live().jpeg.startswith(b"\xff\xd8")


def test_threaded_pipeline_detects_on_its_worker_and_stops_cleanly(tmp_path, make_video):
    p, store = build(tmp_path, make_video, [[GT, GT]], inline=False)
    stop = threading.Event()
    thread = threading.Thread(target=p.run, args=(stop,))
    thread.start()
    deadline = time.monotonic() + 1.0
    while p.detector.calls < 2 and time.monotonic() < deadline:
        time.sleep(0.01)
    stop.set()
    thread.join(timeout=2)
    assert not thread.is_alive() and p.detector.calls >= 2
    assert p.live().now["great_tit"] == 2


def test_visits_count_arrivals_not_birds_in_frame(tmp_path, make_video):
    p, store = build(tmp_path, make_video, [[GT], [GT], [GT, GT], [GT, GT], [], [], [GT], [GT]])
    # confirmed great_tit per detection: 0, 1, 1, 2, 0, 0, 0, 1  -> arrivals 1 + 1 + 1
    run_detections(p, 8)
    assert store.visits(date(2026, 11, 1))["great_tit"] == 3
    assert p.live().visits_today["great_tit"] == 3 and p.live().day_max["great_tit"] == 2


def test_a_bird_that_stays_is_one_visit(tmp_path, make_video):
    p, store = build(tmp_path, make_video, [[GT]])
    run_detections(p, 10)
    assert store.visits(date(2026, 11, 1))["great_tit"] == 1


def test_restart_counts_sitting_birds_once_more_and_keeps_earlier_visits(tmp_path, make_video):
    p, store = build(tmp_path, make_video, [[GT]])
    run_detections(p, 3)
    p2, store2 = build(tmp_path, make_video, [[GT]])
    before = p2.live()   # earlier numbers show before the first detection of this run
    assert before.visits_today == {"great_tit": 1, "blue_tit": 0} and before.day_max["great_tit"] == 1
    run_detections(p2, 3)
    assert store2.visits(date(2026, 11, 1))["great_tit"] == 2


def test_a_new_day_starts_with_no_visits_and_counts_a_sitting_bird_again(tmp_path, make_video):
    # 2 h of simulated time per detection: detections 1-3 fall on 1 Nov, 4-6 on 2 Nov
    p, store = build(tmp_path, make_video, [[GT]], time_scale=3600)
    run_detections(p, 4)
    assert p.live().visits_today == p.live().day_max == {"great_tit": 0, "blue_tit": 0}
    run_detections(p, 6)
    assert store.visits(date(2026, 11, 1))["great_tit"] == 1
    assert store.visits(date(2026, 11, 2))["great_tit"] == 1
    assert p.live().visits_today["great_tit"] == 1 and p.live().day_max["great_tit"] == 1


def test_a_single_missed_frame_is_not_a_new_visit(tmp_path, make_video):
    # a real detector misses a sitting bird now and then: confirmed 0, 1, 0, 0, 1
    p, store = build(tmp_path, make_video, [[GT], [GT], [], [GT], [GT]])
    run_detections(p, 5)
    assert store.visits(date(2026, 11, 1))["great_tit"] == 1


def test_a_bird_gone_for_the_gap_and_back_is_a_new_visit(tmp_path, make_video):
    # confirmed 0, 1, 0, 0, 0, 0, 0, 1: gone for three detections in a row, then back
    p, store = build(tmp_path, make_video, [[GT], [GT], [], [], [], [], [GT], [GT]])
    run_detections(p, 8)
    assert store.visits(date(2026, 11, 1))["great_tit"] == 2


def test_visit_gap_of_one_is_the_old_rule(tmp_path, make_video):
    p, store = build(tmp_path, make_video, [[GT], [GT], [], [GT], [GT]], visit_gap_frames=1)
    run_detections(p, 5)
    assert store.visits(date(2026, 11, 1))["great_tit"] == 2


# --- pests and the latch ---

SQ = {"species": "red_squirrel", "confidence": 0.9, "box": [100, 100, 200, 200]}


def test_a_squirrel_closes_the_latch_and_is_never_a_census_bird(tmp_path, make_video):
    import io

    p, store = build(tmp_path, make_video, [[GT, SQ]], latch="sim")
    run_detections(p, 3)
    live = p.live()
    assert live.latch.closed and live.latch.reason == "red_squirrel" and live.latch.mode == "sim"
    assert live.pests == {"red_squirrel": 1, "brown_rat": 0}
    assert live.unidentified == 0
    assert live.now == {"great_tit": 1, "blue_tit": 0}
    (hour,) = store.hours(date(2026, 11, 1))
    assert hour.counts == {"great_tit": 1, "blue_tit": 0}
    assert set(store.visits(date(2026, 11, 1))) <= {"great_tit", "blue_tit"}
    assert {e.species for e in store.evidence()} == {"great_tit"}
    out = io.StringIO()
    store.export_csv(out, {"great_tit": "Great tit", "blue_tit": "Blue tit"})
    assert out.getvalue().splitlines()[0] == "Period,Hours watched,Great tit,Blue tit"
    assert any(d.species == "red_squirrel" for d in p.last_detections)  # still drawn on the preview


def test_a_weak_squirrel_box_does_not_count(tmp_path, make_video):
    weak = dict(SQ, confidence=0.3)
    p, _ = build(tmp_path, make_video, [[GT, weak]], latch="sim")
    run_detections(p, 3)
    live = p.live()
    assert not live.latch.closed and live.pests == {"red_squirrel": 0, "brown_rat": 0}
    assert live.unidentified == 0  # a weak pest box is not a bird either


def test_a_detector_that_can_name_a_pest_still_keeps_it_out_of_the_census(tmp_path, make_video):
    detector = CountingDetector({"species": [*SPECIES, "red_squirrel"], "frames": [[GT, SQ, SQ]]})
    store = Store(tmp_path / "census.db", SPECIES)
    camera = SimulatedCamera([make_video(seconds=2.0, fps=10)], realtime=False)
    p = Pipeline(camera, detector, store, Settings(evidence_dir=tmp_path / "evidence", latch="sim"), NAMES, inline=True)
    run_detections(p, 3)
    live = p.live()
    assert live.now == live.confirmed == {"great_tit": 1, "blue_tit": 0}
    assert live.visits_today == {"great_tit": 1, "blue_tit": 0}
    assert live.pests == {"red_squirrel": 2, "brown_rat": 0} and live.latch.closed


def test_latch_off_by_default_still_keeps_pests_apart(tmp_path, make_video):
    p, _ = build(tmp_path, make_video, [[GT, SQ]])
    run_detections(p, 3)
    live = p.live()
    assert (live.latch.mode, live.latch.closed) == ("off", False)
    assert live.pests == {"red_squirrel": 1, "brown_rat": 0} and live.unidentified == 0


def test_a_latch_that_fails_never_stops_the_counting(tmp_path, make_video):
    from feeder_census.latch import LatchError

    class Unplugged:
        calls = 0

        def set(self, closed):
            self.calls += 1
            raise LatchError("no router socket")

    detector = CountingDetector({"species": SPECIES, "frames": [[GT, SQ]]})
    store = Store(tmp_path / "census.db", SPECIES)
    camera = SimulatedCamera([make_video(seconds=2.0, fps=10)], realtime=False)
    hardware = Unplugged()
    p = Pipeline(camera, detector, store, Settings(evidence_dir=tmp_path / "evidence", latch="router"), NAMES,
                 inline=True, latch=hardware)
    run_detections(p, 4)
    live = p.live()
    # an open at start-up, tried again at the 1st detection, then a close at the 2nd, 3rd and 4th
    assert live.latch.closed and live.latch.error == "no router socket" and hardware.calls == 5
    assert live.latch.headline == "not_answering"
    assert store.hours(date(2026, 11, 1))[0].counts["great_tit"] == 1


def test_live_state_before_the_first_frame_has_an_open_latch(tmp_path, make_video):
    p, _ = build(tmp_path, make_video, [[GT]], latch="sim")
    live = p.live()
    assert (live.latch.mode, live.latch.closed, live.latch.reason) == ("sim", False, None)
    assert live.pests == {"red_squirrel": 0, "brown_rat": 0}


def test_a_pest_box_is_drawn_by_its_own_threshold():
    from feeder_census.draw import annotate
    from feeder_census.types import Detection

    frame = np.zeros((240, 320, 3), np.uint8)
    squirrel = [Detection("red_squirrel", 0.55, (100, 100, 200, 200))]  # under the bird threshold, over the pest one
    grey = annotate(frame, squirrel, {"red_squirrel": "Red squirrel"}, 0.6)[150, 100]
    drawn = annotate(frame, squirrel, {"red_squirrel": "Red squirrel"}, 0.6, pests={"red_squirrel": 0.5})[150, 100]
    assert tuple(grey) == (150, 150, 150) and tuple(drawn) != (150, 150, 150) and drawn.any()
    weak = [Detection("red_squirrel", 0.3, (100, 100, 200, 200))]
    assert tuple(annotate(frame, weak, {}, 0.6, pests={"red_squirrel": 0.5})[150, 100]) == (150, 150, 150)


def test_a_label_near_the_right_edge_is_shifted_left_to_stay_inside_the_picture():
    from feeder_census.draw import annotate
    from feeder_census.types import Detection

    frame = np.zeros((240, 320, 3), np.uint8)
    near_edge = [Detection("great_tit", 0.9, (300, 100, 318, 140))]
    out = annotate(frame, near_edge, {"great_tit": "Great tit"}, 0.6)
    assert out[85:99, 285].any()  # the label starts left of the box, so its text is not cut off at the edge


# --- photo mode: the feed shows only the analysed photos, each held until the next ---


class VaryingCamera:
    """Every read is a different grey frame, 0.5 s of footage after the last."""

    def __init__(self):
        self.reads = 0

    def read(self):
        self.reads += 1
        return np.full((240, 320, 3), 20 + 10 * self.reads, np.uint8), (self.reads - 1) * 0.5

    def close(self):
        pass


def photo_pipeline(tmp_path, frames, inline=True):
    tmp_path.mkdir(parents=True, exist_ok=True)
    # preview_fps is high so the preview throttle (5 fps by default) cannot hide a refresh from camera frames
    return build(tmp_path, None, frames, camera=VaryingCamera(), inline=inline, photo_mode=True,
                 detect_every_s=2.0, preview_fps=1000.0)[0]


def step_past_throttle(p):
    time.sleep(0.01)  # longer than the preview interval, so a refresh from this frame would not be throttled
    p.step()


def wait_idle(p):
    deadline = time.monotonic() + 2.0
    while p._busy.is_set() and time.monotonic() < deadline:
        time.sleep(0.005)
    assert not p._busy.is_set()


def test_photo_mode_shows_the_analysed_frame_with_its_boxes_and_holds_it(tmp_path):
    p = photo_pipeline(tmp_path, [[GT]])
    p.step()  # detection due at once
    shown = p.live().jpeg
    assert shown.startswith(b"\xff\xd8") and p.detector.calls == 1
    for _ in range(3):  # footage 0.5, 1.0, 1.5 s: no detection due, the camera frames differ
        step_past_throttle(p)
    assert p.detector.calls == 1 and p.live().jpeg == shown
    step_past_throttle(p)  # footage 2.0 s: the next photo replaces it
    assert p.detector.calls == 2 and p.live().jpeg != shown


def test_photo_mode_boxes_are_the_detections_of_the_shown_frame(tmp_path):
    with_birds = photo_pipeline(tmp_path / "a", [[GT]])
    without = photo_pipeline(tmp_path / "b", [[]])
    with_birds.step()
    without.step()
    assert with_birds.live().jpeg != without.live().jpeg  # same frame, one drawn with a box


def test_photo_mode_shows_the_first_frame_once_without_boxes_before_any_detection_has_finished(tmp_path):
    no_boxes = photo_pipeline(tmp_path / "ref", [[]])
    no_boxes.step()  # the first frame, analysed, nothing found: what an unboxed first frame looks like
    release = threading.Event()
    p = photo_pipeline(tmp_path / "p", [[GT]], inline=False)
    detect = p.detector.detect
    p.detector.detect = lambda frame: (release.wait(2), detect(frame))[1]
    shown = []  # (number of boxes drawn) for every preview this pipeline published
    show = p._show
    p._show = lambda frame, detections: (shown.append(len(detections)), show(frame, detections))[1]
    try:
        p.step()
        assert p.detector.calls == 0  # the detection has not finished
        first = p.live().jpeg
        assert first == no_boxes.live().jpeg  # a JPEG of the first frame, without boxes
        step_past_throttle(p)  # more camera frames while the detection runs: nothing is published
        step_past_throttle(p)
        assert p.live().jpeg == first and shown == [0]
        release.set()
        wait_idle(p)
        photo = p.live().jpeg
        assert photo != first and shown == [0, 1]  # replaced by the analysed photo, with its box
        step_past_throttle(p)  # the first-frame path never publishes again
        step_past_throttle(p)
        assert p.live().jpeg == photo and shown == [0, 1]
    finally:
        release.set()
        p.close()


def test_photo_mode_on_the_worker_shows_the_analysed_frame_with_its_boxes(tmp_path):
    inline = photo_pipeline(tmp_path / "inline", [[GT]])
    inline.step()
    p = photo_pipeline(tmp_path / "worker", [[GT]], inline=False)
    try:
        p.step()
        wait_idle(p)
        assert p.live().jpeg == inline.live().jpeg
        shown = p.live().jpeg
        for _ in range(2):  # footage 0.5 and 1.0 s: nothing due; the camera frames must not replace the photo
            step_past_throttle(p)
        assert p.detector.calls == 1 and p.live().jpeg == shown
    finally:
        p.close()


def test_without_photo_mode_every_camera_frame_refreshes_the_preview(tmp_path):
    p = build(tmp_path, None, [[GT]], camera=VaryingCamera(), preview_fps=1000.0)[0]
    p.step()
    first = p.live().jpeg
    time.sleep(0.01)  # past the preview interval
    p.step()  # no detection due, but the preview follows the camera
    assert p.detector.calls == 1 and p.live().jpeg != first
