import subprocess
import sys

import cv2
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
