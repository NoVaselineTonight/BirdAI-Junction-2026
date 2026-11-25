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


# --- LiveCamera: a USB webcam, tested only with a fake capture (no real device is ever opened) ---

import cv2  # noqa: E402
import numpy as np  # noqa: E402

from feeder_census import camera as camera_module  # noqa: E402
from feeder_census.camera import LiveCamera  # noqa: E402


class FakeCapture:
    def __init__(self, opened=True, frames=None):
        self.opened = opened
        self.frames = frames
        self.props = {}
        self.releases = 0

    def isOpened(self):
        return self.opened

    def set(self, prop, value):
        self.props[prop] = value
        return True

    def read(self):
        if self.frames is not None:
            if not self.frames:
                return False, None
            return True, self.frames.pop(0)
        frame = np.zeros((4, 6, 3), np.uint8)
        frame[0, 0] = (255, 255, 255)  # a white top-left pixel shows which way up the picture is
        return True, frame

    def release(self):
        self.releases += 1


def opener(capture, seen=None):
    def open_capture(source):
        if seen is not None:
            seen.append(source)
        return capture
    return open_capture


def test_live_camera_returns_frames_with_growing_seconds():
    cam = LiveCamera("/dev/video4", open_capture=opener(FakeCapture()))
    times = []
    for _ in range(3):
        frame, t = cam.read()
        assert frame.shape == (4, 6, 3)
        times.append(t)
        time.sleep(0.01)
    cam.close()
    assert times[0] == pytest.approx(0.0, abs=0.005) and times[0] < times[1] < times[2]


def test_live_camera_asks_for_mjpg_at_the_given_size():
    cap = FakeCapture()
    LiveCamera("0", size=(640, 480), open_capture=opener(cap)).close()
    assert cap.props[cv2.CAP_PROP_FOURCC] == cv2.VideoWriter_fourcc(*"MJPG")
    assert cap.props[cv2.CAP_PROP_FRAME_WIDTH] == 640 and cap.props[cv2.CAP_PROP_FRAME_HEIGHT] == 480


def test_live_camera_rotate_180_turns_the_picture_upside_down():
    upright, _ = LiveCamera("0", open_capture=opener(FakeCapture())).read()
    turned, _ = LiveCamera("0", rotate=180, open_capture=opener(FakeCapture())).read()
    assert upright[0, 0].tolist() == [255, 255, 255] and upright[-1, -1].tolist() == [0, 0, 0]
    assert turned[-1, -1].tolist() == [255, 255, 255] and turned[0, 0].tolist() == [0, 0, 0]


def test_live_camera_rotate_must_be_0_or_180():
    with pytest.raises(ValueError):
        LiveCamera("0", rotate=90, open_capture=opener(FakeCapture()))


def test_live_camera_failed_read_names_the_device():
    cam = LiveCamera("/dev/video4", open_capture=opener(FakeCapture(frames=[])))
    with pytest.raises(ValueError, match=r"^camera /dev/video4 gave no picture$"):
        cam.read()


def test_live_camera_that_cannot_open_names_the_device():
    cap = FakeCapture(opened=False)
    with pytest.raises(ValueError, match=r"^cannot open camera /dev/video9$"):
        LiveCamera("/dev/video9", open_capture=opener(cap))
    assert cap.releases == 1


def test_live_camera_close_twice_is_fine():
    cap = FakeCapture()
    cam = LiveCamera("0", open_capture=opener(cap))
    cam.close()
    cam.close()
    assert cap.releases == 1


def test_live_camera_passes_a_path_as_text_and_a_number_as_an_int():
    seen = []
    LiveCamera("/dev/video4", open_capture=opener(FakeCapture(), seen)).close()
    LiveCamera("2", open_capture=opener(FakeCapture(), seen)).close()
    assert seen == ["/dev/video4", 2]


def test_live_camera_default_opener_uses_v4l2_for_a_path_and_plain_index_for_a_number(monkeypatch):
    calls = []
    monkeypatch.setattr(camera_module.cv2, "VideoCapture", lambda *a: calls.append(a) or FakeCapture())
    LiveCamera("/dev/video4").close()
    LiveCamera("1").close()
    assert calls == [("/dev/video4", cv2.CAP_V4L2), (1,)]
