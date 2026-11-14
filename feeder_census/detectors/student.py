import json
from collections.abc import Sequence
from pathlib import Path

import numpy as np
import onnxruntime as ort

from feeder_census.detectors.base import letterbox, nms
from feeder_census.types import UNIDENTIFIED, Detection

NMS_CONTAIN = 0.8  # a head box inside a body box is one bird, as in the two-stage detector


def decode_student(
    output: np.ndarray,
    ratio: float,
    pad: tuple[int, int],
    classes: Sequence[str],
    min_score: float = 0.25,
    nms_iou: float = 0.5,
) -> list[Detection]:
    """Turn the student's `[1, N, 6]` output (x1, y1, x2, y2, score, class_index in letterboxed
    input pixels) into detections in source-frame pixels, best score first.

    Boxes are not clipped here; the caller knows the frame size.
    """
    if output.shape[-1] != 6:
        raise ValueError(f"student output has rows of {output.shape[-1]} values, expected 6 "
                         "(x1, y1, x2, y2, score, class); was the model exported with nms?")
    rows = output.reshape(-1, 6)
    rows = rows[rows[:, 4] >= min_score]
    if len(rows) == 0:
        return []
    class_ids = rows[:, 5].astype(int)
    if class_ids.min() < 0 or class_ids.max() >= len(classes):
        raise ValueError(f"student named class {class_ids.max()}, but the card lists {len(classes)} classes")
    boxes = rows[:, :4].astype(np.float32).copy()
    boxes[:, [0, 2]] -= pad[0]
    boxes[:, [1, 3]] -= pad[1]
    boxes /= ratio
    scores = rows[:, 4]
    return [
        Detection(
            species=classes[class_ids[i]],  # the "unidentified" class is the UNIDENTIFIED key itself
            confidence=float(scores[i]),
            box=tuple(float(v) for v in boxes[i]),
        )
        for i in nms(boxes, scores, nms_iou, NMS_CONTAIN)
    ]


class StudentDetector:
    """The small on-device detector trained on corrected feeder footage: one model, species named directly."""

    def __init__(self, model: Path, card: Path):
        info = json.loads(Path(card).read_text())
        self.name: str = info["name"]
        self.count_threshold: float = info["count_threshold"]
        self._classes: list[str] = info["classes"]
        self.species: tuple[str, ...] = tuple(c for c in self._classes if c != UNIDENTIFIED)
        self._size = int(info["imgsz"])
        self._session = ort.InferenceSession(str(model), providers=["CPUExecutionProvider"])
        self._input_name = self._session.get_inputs()[0].name

    def detect(self, frame_bgr: np.ndarray) -> list[Detection]:
        h, w = frame_bgr.shape[:2]
        square, ratio, pad = letterbox(frame_bgr, self._size, center=True)
        rgb = square[:, :, ::-1].transpose(2, 0, 1)[None]
        blob = np.ascontiguousarray(rgb, dtype=np.float32) / 255.0
        output = self._session.run(None, {self._input_name: blob})[0]
        found = []
        for d in decode_student(output, ratio, pad, self._classes):
            x1, y1, x2, y2 = d.box
            box = (
                float(np.clip(x1, 0, w)), float(np.clip(y1, 0, h)),
                float(np.clip(x2, 0, w)), float(np.clip(y2, 0, h)),
            )
            if box[2] > box[0] and box[3] > box[1]:
                found.append(Detection(d.species, d.confidence, box))
        return found
