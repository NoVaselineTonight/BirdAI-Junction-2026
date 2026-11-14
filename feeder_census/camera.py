import time
from collections.abc import Sequence
from datetime import date, datetime, timedelta
from datetime import time as clock_time
from pathlib import Path

import cv2
import numpy as np

VIDEO_SUFFIXES = (".mp4", ".mkv", ".mov", ".avi")


class SimClock:
    """Maps simulated watching time to a date and time of day, skipping the night."""

    def __init__(self, start: date, day_start: clock_time = clock_time(8), day_end: clock_time = clock_time(16)):
        self._start = start
        self._day_start = day_start
        self._day_s = (
            datetime.combine(start, day_end) - datetime.combine(start, day_start)
        ).total_seconds()

    def at(self, watched_s: float) -> datetime:
        days, within = divmod(watched_s, self._day_s)
        opening = datetime.combine(self._start + timedelta(days=int(days)), self._day_start)
        return opening + timedelta(seconds=within)


def _expand(paths: Sequence[Path]) -> list[Path]:
    files: list[Path] = []
    for path in map(Path, paths):
        if not path.exists():
            raise FileNotFoundError(str(path))
        if path.is_dir():
            found = sorted(p for p in path.iterdir() if p.suffix.lower() in VIDEO_SUFFIXES)
            if not found:
                raise FileNotFoundError(f"no video files in {path}")
            files.extend(found)
        else:
            files.append(path)
    return files


class SimulatedCamera:
    """Plays video files in order, forever, as if they were a live camera.

    Footage time is frames played divided by the file's frame rate, so it keeps
    growing across files and loops. With `realtime` the call to `read` waits for
    the next frame to be due, and skips frames the caller was too late for.
    """

    def __init__(self, paths: Sequence[Path], realtime: bool = True):
        self._files = _expand(paths)
        self._realtime = realtime
        self._cap: cv2.VideoCapture | None = None
        self._file = -1
        self._fps = 1.0
        self._pass_frames = 0  # frames played from the current pass of the current file
        self._offset_s = 0.0  # footage time at which the current pass began
        self._wall_start: float | None = None

    def _open_next(self) -> None:
        self._file = (self._file + 1) % len(self._files)
        path = self._files[self._file]
        cap = cv2.VideoCapture(str(path))
        fps = cap.get(cv2.CAP_PROP_FPS) if cap.isOpened() else 0.0
        if not cap.isOpened() or not fps > 0:
            cap.release()
            raise ValueError(f"cannot decode video {path.name}")
        self._cap, self._fps = cap, fps
        self._pass_frames = 0

    def _grab(self) -> float:
        """Advance one frame and return its footage time."""
        if self._cap is None:
            self._open_next()
        if not self._cap.grab():
            if self._pass_frames == 0:
                raise ValueError(f"cannot decode video {self._files[self._file].name}")
            self._offset_s += self._pass_frames / self._fps
            self._cap.release()
            self._open_next()
            if not self._cap.grab():
                raise ValueError(f"cannot decode video {self._files[self._file].name}")
        t = self._offset_s + self._pass_frames / self._fps
        self._pass_frames += 1
        return t

    def read(self) -> tuple[np.ndarray, float]:
        """The next frame and its footage seconds since the start."""
        t = self._grab()
        if self._realtime:
            now = time.monotonic()
            if self._wall_start is None:
                self._wall_start = now - t
            due = now - self._wall_start
            while t < due - 0.5 / self._fps:  # late: jump to the frame that is due
                t = self._grab()
            if t > due:
                time.sleep(t - due)
        ok, frame = self._cap.retrieve()
        if not ok:
            raise ValueError(f"cannot decode video {self._files[self._file].name}")
        return frame, t

    def close(self) -> None:
        if self._cap is not None:
            self._cap.release()
            self._cap = None
