import time
from datetime import date, datetime

import pytest

from feeder_census.camera import SimClock, SimulatedCamera


def test_clock_skips_the_night():
    c = SimClock(date(2026, 11, 1))
    assert c.at(0) == datetime(2026, 11, 1, 8, 0)
    assert c.at(8 * 3600 - 1) == datetime(2026, 11, 1, 15, 59, 59)
    assert c.at(8 * 3600) == datetime(2026, 11, 2, 8, 0)
    assert c.at(15 * 8 * 3600) == datetime(2026, 11, 16, 8, 0)


def test_camera_loops_and_footage_time_keeps_growing(make_video):
    cam = SimulatedCamera([make_video(seconds=2.0, fps=10)], realtime=False)
    times = [cam.read()[1] for _ in range(45)]
    cam.close()
    assert times == sorted(times) and len(set(times)) == 45 and times[-1] == pytest.approx(4.4, abs=0.15)


def test_camera_plays_files_in_name_order(make_video):
    make_video("b.mp4", value=200)
    a = make_video("a.mp4", value=20)
    cam = SimulatedCamera([a.parent], realtime=False)
    frame, _ = cam.read()
    cam.close()
    assert frame.mean() < 100


def test_camera_moves_on_to_the_next_file(make_video):
    a = make_video("a.mp4", seconds=1.0, value=20)
    b = make_video("b.mp4", seconds=1.0, value=200)
    cam = SimulatedCamera([a, b], realtime=False)
    frames = [cam.read()[0].mean() for _ in range(15)]
    cam.close()
    assert frames[0] < 100 and frames[10] > 100 and frames[14] > 100


def test_missing_video_names_the_path(tmp_path):
    with pytest.raises(FileNotFoundError, match="nope.mp4"):
        SimulatedCamera([tmp_path / "nope.mp4"])


def test_undecodable_video_names_the_file(tmp_path):
    bad = tmp_path / "bad.mp4"
    bad.write_text("not a video")
    with pytest.raises(ValueError, match="bad.mp4"):
        SimulatedCamera([bad]).read()


def test_realtime_camera_skips_ahead_when_the_reader_is_late(make_video):
    cam = SimulatedCamera([make_video(seconds=2.0, fps=10)], realtime=True)
    cam.read()
    time.sleep(0.5)
    assert cam.read()[1] >= 0.4
    cam.close()
