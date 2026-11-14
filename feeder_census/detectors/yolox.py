from pathlib import Path

import numpy as np
import onnxruntime as ort

from feeder_census.detectors.base import letterbox, nms

STRIDES = (8, 16, 32)


def decode_yolox(output: np.ndarray, size: int, class_id: int) -> tuple[np.ndarray, np.ndarray]:
    """Turn raw YOLOX output into (boxes_xyxy, scores) in letterboxed pixels, one row per anchor."""
    rows = output.reshape(-1, output.shape[-1])
    grids = []
    for stride in STRIDES:
        n = size // stride
        xs, ys = np.meshgrid(np.arange(n), np.arange(n))
        grids.append((np.stack((xs, ys), -1).reshape(-1, 2), np.full((n * n, 1), stride)))
    grid = np.concatenate([g for g, _ in grids]).astype(np.float32)
    stride = np.concatenate([s for _, s in grids]).astype(np.float32)
    xy = (rows[:, :2] + grid) * stride
    wh = np.exp(rows[:, 2:4]) * stride
    boxes = np.concatenate([xy - wh / 2, xy + wh / 2], axis=1)
    scores = rows[:, 4] * rows[:, 5 + class_id]
    return boxes, scores


class YoloxBoxes:
    """YOLOX-nano ONNX bird finder: boxes in source-frame pixels with a score."""

    def __init__(
        self,
        model: Path,
        score_threshold: float = 0.30,
        nms_iou: float = 0.45,
        class_id: int = 14,
        nms_contain: float = 0.8,
    ):
        self._session = ort.InferenceSession(str(model), providers=["CPUExecutionProvider"])
        model_input = self._session.get_inputs()[0]
        self._input_name = model_input.name
        self._size = int(model_input.shape[2])
        self._score_threshold = score_threshold
        self._nms_iou = nms_iou
        self._class_id = class_id
        self._nms_contain = nms_contain

    def boxes(self, frame_bgr: np.ndarray) -> list[tuple[tuple[float, float, float, float], float]]:
        h, w = frame_bgr.shape[:2]
        square, ratio, _ = letterbox(frame_bgr, self._size, center=False)
        blob = np.ascontiguousarray(square.transpose(2, 0, 1)[None], dtype=np.float32)
        (output,) = self._session.run(None, {self._input_name: blob})
        boxes, scores = decode_yolox(output, self._size, self._class_id)
        keep = scores >= self._score_threshold
        boxes, scores = boxes[keep] / ratio, scores[keep]
        found = []
        for i in nms(boxes, scores, self._nms_iou, self._nms_contain):
            x1, y1, x2, y2 = boxes[i]
            box = (
                float(np.clip(x1, 0, w)), float(np.clip(y1, 0, h)),
                float(np.clip(x2, 0, w)), float(np.clip(y2, 0, h)),
            )
            if box[2] > box[0] and box[3] > box[1]:
                found.append((box, float(scores[i])))
        return found
