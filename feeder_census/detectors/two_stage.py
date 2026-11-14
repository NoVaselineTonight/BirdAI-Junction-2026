from collections.abc import Sequence
from typing import Protocol

import numpy as np

from feeder_census.species import Species
from feeder_census.types import UNIDENTIFIED, Detection


class _Boxes(Protocol):
    def boxes(self, frame_bgr: np.ndarray) -> list[tuple[tuple[float, float, float, float], float]]: ...


class _Classifier(Protocol):
    def classify(self, crop_bgr: np.ndarray) -> tuple[str, float]: ...


class TwoStageDetector:
    """Finds bird boxes, then names each padded crop with the classifier.

    `species` is the list this detector may name; birds the classifier calls
    anything else (or background) come back as UNIDENTIFIED.
    """

    name = "pretrained two-stage"
    count_threshold = 0.60

    def __init__(self, boxes: _Boxes, classifier: _Classifier, species: Sequence[Species], pad: float = 0.10):
        self._boxes = boxes
        self._classifier = classifier
        self._pad = pad
        self.species = tuple(s.key for s in species)
        self._key_of = {name: s.key for s in species for name in (s.scientific, *s.aliases)}

    def detect(self, frame_bgr: np.ndarray) -> list[Detection]:
        h, w = frame_bgr.shape[:2]
        found = []
        for box, _score in self._boxes.boxes(frame_bgr):
            x1, y1, x2, y2 = box
            px, py = (x2 - x1) * self._pad, (y2 - y1) * self._pad
            cx1, cy1 = max(0, int(x1 - px)), max(0, int(y1 - py))
            cx2, cy2 = min(w, int(np.ceil(x2 + px))), min(h, int(np.ceil(y2 + py)))
            if cx2 <= cx1 or cy2 <= cy1:
                continue
            name, probability = self._classifier.classify(frame_bgr[cy1:cy2, cx1:cx2])
            key = self._key_of.get(name, UNIDENTIFIED)
            found.append(Detection(key, probability, (float(x1), float(y1), float(x2), float(y2))))
        return found
