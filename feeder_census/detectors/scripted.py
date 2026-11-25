import json
from pathlib import Path

import numpy as np

from feeder_census.types import Detection


class ScriptedDetector:
    """Replays canned detections, one list per `detect` call, cycling. For demos and tests."""

    name = "scripted"
    count_threshold = 0.60

    def __init__(self, script: Path | dict):
        data = script if isinstance(script, dict) else json.loads(Path(script).read_text(encoding="utf-8"))
        self.species = tuple(data["species"])
        self._frames = [
            [Detection(d["species"], float(d["confidence"]), tuple(float(v) for v in d["box"])) for d in frame]
            for frame in data["frames"]
        ]
        if not self._frames:
            raise ValueError("scripted detector needs at least one frame")
        self._next = 0

    def detect(self, frame_bgr: np.ndarray | None) -> list[Detection]:
        frame = self._frames[self._next % len(self._frames)]
        self._next += 1
        return list(frame)
