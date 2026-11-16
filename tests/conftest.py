from pathlib import Path

import cv2
import numpy as np
import pytest


@pytest.fixture
def make_video(tmp_path):
    """Writes a solid grey test video under tmp_path and returns its path."""

    def make(name="a.mp4", seconds=2.0, fps=10, size=(320, 240), value=60) -> Path:
        path = tmp_path / name
        path.parent.mkdir(parents=True, exist_ok=True)
        writer = cv2.VideoWriter(str(path), cv2.VideoWriter_fourcc(*"mp4v"), fps, size)
        frame = np.full((size[1], size[0], 3), value, dtype=np.uint8)
        for _ in range(round(seconds * fps)):
            writer.write(frame)
        writer.release()
        return path

    return make
