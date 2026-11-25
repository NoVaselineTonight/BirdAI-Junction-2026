from typing import Protocol

import cv2
import numpy as np

from feeder_census.types import Detection


class Detector(Protocol):
    name: str
    species: tuple[str, ...]  # keys this detector can name, never UNIDENTIFIED
    count_threshold: float  # minimum confidence for a bird to count

    def detect(self, frame_bgr: np.ndarray) -> list[Detection]: ...


def letterbox(
    image: np.ndarray, size: int, center: bool, pad_value: int = 114
) -> tuple[np.ndarray, float, tuple[int, int]]:
    """Fit `image` into a size x size square keeping its aspect ratio.

    Returns the square image, the resize ratio and the (dx, dy) offset of the
    resized image inside the square ((0, 0) when `center` is False).
    """
    h, w = image.shape[:2]
    ratio = min(size / h, size / w)
    new_w, new_h = int(w * ratio), int(h * ratio)
    resized = cv2.resize(image, (new_w, new_h), interpolation=cv2.INTER_LINEAR)
    canvas = np.full((size, size, *image.shape[2:]), pad_value, image.dtype)
    dx, dy = ((size - new_w) // 2, (size - new_h) // 2) if center else (0, 0)
    canvas[dy : dy + new_h, dx : dx + new_w] = resized
    return canvas, ratio, (dx, dy)


def nms(boxes: np.ndarray, scores: np.ndarray, iou: float, contain: float | None = None) -> list[int]:
    """Class-agnostic non-maximum suppression. Returns kept indices, best score first.

    With `contain` set, a box is also dropped when at least that fraction of the
    smaller of the two boxes lies inside a higher-scoring kept box (a head box
    inside a body box is one bird).
    """
    order = list(np.argsort(-scores, kind="stable"))
    areas = (boxes[:, 2] - boxes[:, 0]) * (boxes[:, 3] - boxes[:, 1])
    keep: list[int] = []
    while order:
        i = int(order.pop(0))
        keep.append(i)
        if not order:
            break
        rest = np.array(order)
        w = np.minimum(boxes[i, 2], boxes[rest, 2]) - np.maximum(boxes[i, 0], boxes[rest, 0])
        h = np.minimum(boxes[i, 3], boxes[rest, 3]) - np.maximum(boxes[i, 1], boxes[rest, 1])
        inter = np.clip(w, 0, None) * np.clip(h, 0, None)
        overlap = inter / (areas[i] + areas[rest] - inter + 1e-9)
        drop = overlap > iou
        if contain is not None:
            drop |= inter / (np.minimum(areas[i], areas[rest]) + 1e-9) >= contain
        order = [int(j) for j, d in zip(rest, drop) if not d]
    return keep
