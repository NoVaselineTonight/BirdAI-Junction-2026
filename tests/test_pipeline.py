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
