import subprocess
import sys

import cv2
import numpy as np
import pytest


def test_prepare_video_downscales_and_keeps_the_length(make_video, tmp_path):
    src = make_video(seconds=2.0, fps=30, size=(1920, 1080))
    out = tmp_path / "small.mp4"
    subprocess.run([sys.executable, "tools/prepare_video.py", src, out, "--height", "720", "--fps", "15"], check=True)
    cap = cv2.VideoCapture(str(out))
    assert cap.get(cv2.CAP_PROP_FRAME_HEIGHT) == 720 and cap.get(cv2.CAP_PROP_FPS) == pytest.approx(15, abs=0.5)
    assert cap.get(cv2.CAP_PROP_FRAME_COUNT) / 15 == pytest.approx(2.0, abs=0.2)


def test_prepare_video_fails_clearly_on_an_unreadable_file(tmp_path):
    bad = tmp_path / "not-a-video.mp4"
    bad.write_bytes(b"nope")
    done = subprocess.run(
        [sys.executable, "tools/prepare_video.py", str(bad), str(tmp_path / "out.mp4")], capture_output=True, text=True
    )
    assert done.returncode != 0 and "cannot read" in done.stderr


def run_prepare(src, dst):
    return subprocess.run(
        [sys.executable, "tools/prepare_video.py", str(src), str(dst)], capture_output=True, text=True
    )


def test_prepare_video_fails_when_the_output_cannot_be_written(make_video, tmp_path):
    src = make_video()
    blocker = tmp_path / "file"
    blocker.write_text("not a folder")
    done = run_prepare(src, blocker / "out.mp4")
    assert done.returncode != 0 and "error:" in done.stderr
    assert not (blocker / "out.mp4").exists()


def test_prepare_video_fails_when_no_encoder_opens(make_video, tmp_path):
    done = run_prepare(make_video(), tmp_path / "out.nosuchformat")
    assert done.returncode != 0 and "cannot write" in done.stderr


def test_prepare_video_fails_when_decoding_stops_early(monkeypatch, tmp_path):
    import prepare_video

    class HalfCapture:
        """Says it has 100 frames at 10 fps but delivers only 30."""

        def __init__(self, path):
            self.left = 30

        def get(self, prop):
            return {cv2.CAP_PROP_FPS: 10.0, cv2.CAP_PROP_FRAME_COUNT: 100.0}.get(prop, 0.0)

        def read(self):
            self.left -= 1
            return self.left >= 0, np.zeros((240, 320, 3), np.uint8)

        def release(self):
            pass

    monkeypatch.setattr(prepare_video.cv2, "VideoCapture", HalfCapture)
    out = tmp_path / "out.mp4"
    with pytest.raises(ValueError, match="stopped decoding early"):
        prepare_video.prepare(tmp_path / "in.mp4", out, 240, 10)
    assert not out.exists()
