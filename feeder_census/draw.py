import zlib
from collections.abc import Mapping, Sequence

import cv2
import numpy as np

from feeder_census.types import UNIDENTIFIED, Detection

_GREY = (150, 150, 150)
_PALETTE = ((60, 180, 75), (230, 120, 40), (60, 60, 230), (200, 60, 170), (30, 190, 220), (200, 180, 40))
_FONT = cv2.FONT_HERSHEY_SIMPLEX


def _label(img: np.ndarray, text: str, x: int, y: int, color: tuple[int, int, int], scale: float) -> None:
    (w, h), base = cv2.getTextSize(text, _FONT, scale, 1)
    top = max(y - h - base, 0)
    cv2.rectangle(img, (x, top), (x + w + 2, top + h + base), color, -1)
    cv2.putText(img, text, (x + 1, top + h), _FONT, scale, (255, 255, 255), 1, cv2.LINE_AA)


def annotate(
    frame: np.ndarray, detections: Sequence[Detection], names: Mapping[str, str], threshold: float
) -> np.ndarray:
    """A copy of `frame` with counted birds boxed in colour and the rest in grey."""
    img = frame.copy()
    scale = max(0.4, min(img.shape[:2]) / 700)
    for d in detections:
        x1, y1, x2, y2 = (int(round(v)) for v in d.box)
        if d.species != UNIDENTIFIED and d.confidence >= threshold:
            color = _PALETTE[zlib.crc32(d.species.encode()) % len(_PALETTE)]
            cv2.rectangle(img, (x1, y1), (x2, y2), color, 2)
            _label(img, f"{names.get(d.species, d.species)} {d.confidence:.2f}", x1, y1, color, scale)
        else:
            cv2.rectangle(img, (x1, y1), (x2, y2), _GREY, 1)
            _label(img, UNIDENTIFIED, x1, y1, _GREY, scale)
    return img
