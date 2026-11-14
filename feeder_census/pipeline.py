import sys
import threading
import time
from collections import deque
from collections.abc import Callable, Mapping
from concurrent.futures import ThreadPoolExecutor
from dataclasses import dataclass
from datetime import date, datetime

import cv2
import numpy as np

from feeder_census.camera import SimClock, SimulatedCamera
from feeder_census.census import ConfirmFilter, frame_counts
from feeder_census.config import Settings
from feeder_census.detectors.base import Detector
from feeder_census.draw import annotate
from feeder_census.store import Store
from feeder_census.types import Detection

_EPS = 1e-9  # footage times are float sums; a gap of 1.9999999999999996 s is 2 s


@dataclass(frozen=True)
class LiveState:
    jpeg: bytes
    sim_time: datetime
    now: dict[str, int]
    confirmed: dict[str, int]
    unidentified: int
    detect_ms: float
    detector: str
    visits_today: dict[str, int]  # arrivals at the feeder, not birds
    day_max: dict[str, int]  # largest number seen at once today


class Pipeline:
    """Camera, detector, counting rule and store, tied together.

    `step` runs on one thread (the caller of `run`). The detector only ever runs
    on one thread at a time: inline, or on a single worker. Everything `live`
    reads is guarded by `_lock`.
    """

    def __init__(
        self,
        camera: SimulatedCamera,
        detector: Detector,
        store: Store,
        settings: Settings,
        names: Mapping[str, str],
        inline: bool = False,
        on_result: Callable[[LiveState], None] | None = None,
    ):
        self.camera, self.detector, self.store = camera, detector, store
        self.settings, self.names, self.inline = settings, names, inline
        self.clock = SimClock(settings.sim_start)
        self.last_detections: list[Detection] = []
        self.error: Exception | None = None  # raised by `step` when the worker failed
        self._on_result = on_result
        self._threshold = (
            settings.count_threshold if settings.count_threshold is not None else detector.count_threshold
        )
        self._filter = ConfirmFilter(detector.species, settings.confirm_frames)
        self._zeros = {s: 0 for s in detector.species}
        self._lock = threading.Lock()
        self._total_s = store.total_watched_s()  # simulated seconds watched, ever
        self._now = dict(self._zeros)
        self._confirmed = dict(self._zeros)
        self._unidentified = 0
        self._detect_ms = 0.0
        self._jpeg = b""
        self._last_preview: float | None = None
        self._last_start_t: float | None = None  # footage time the last detection started
        self._day: date | None = None  # worker side only
        # worker side only: confirmed counts of the last `visit_gap_frames` detections; arrivals are rises over
        # their maximum, so a bird the detector missed for a frame or two is not a new visit
        self._recent: deque[dict[str, int]] = deque(maxlen=max(1, settings.visit_gap_frames))
        self._visits, self._day_max = self._today(self.clock.at(self._total_s).date())
        self._busy = threading.Event()
        self._executor: ThreadPoolExecutor | None = None

    def live(self) -> LiveState:
        with self._lock:
            return LiveState(
                self._jpeg, self.clock.at(self._total_s), dict(self._now), dict(self._confirmed),
                self._unidentified, self._detect_ms, self.detector.name,
                dict(self._visits), dict(self._day_max),
            )

    def _today(self, day: date) -> tuple[dict[str, int], dict[str, int]]:
        """Visits and the largest number seen at once on `day`, as the store holds them."""
        hours = self.store.hours(day)
        day_max = {sp: max((r.counts.get(sp, 0) for r in hours), default=0) for sp in self.detector.species}
        visits = self.store.visits(day)
        return {sp: visits.get(sp, 0) for sp in self.detector.species}, day_max

    def step(self) -> None:
        if self.error is not None:
            raise self.error
        frame, t = self.camera.read()
        every = self.settings.detect_every_s
        due = self._last_start_t is None or t - self._last_start_t >= every - _EPS
        if due and not self._busy.is_set():
            gap = None if self._last_start_t is None else t - self._last_start_t
            self._last_start_t = t
            if self.inline:
                self._detect(frame, gap)
            else:
                if self._executor is None:
                    self._executor = ThreadPoolExecutor(max_workers=1, thread_name_prefix="detector")
                self._busy.set()
                self._executor.submit(self._job, frame, gap)
        self._update_preview(frame)

    def run(self, stop: threading.Event) -> None:
        try:
            while not stop.is_set():
                self.step()
        finally:
            self.close()

    def close(self) -> None:
        if self._executor is not None:
            self._executor.shutdown(wait=True)
            self._executor = None
        self.camera.close()

    def _update_preview(self, frame: np.ndarray) -> None:
        now = time.monotonic()
        if self._last_preview is not None and now - self._last_preview < 1.0 / self.settings.preview_fps:
            return
        self._last_preview = now
        with self._lock:
            detections = list(self.last_detections)
        img = annotate(frame, detections, self.names, self._threshold)
        width = self.settings.preview_width
        if img.shape[1] > width:
            img = cv2.resize(img, (width, round(img.shape[0] * width / img.shape[1])), interpolation=cv2.INTER_AREA)
        ok, buf = cv2.imencode(".jpg", img, [cv2.IMWRITE_JPEG_QUALITY, 70])
        if ok:
            with self._lock:
                self._jpeg = buf.tobytes()

    def _job(self, frame: np.ndarray, gap: float | None) -> None:
        try:
            self._detect(frame, gap)
        except Exception as exc:  # reported to the caller of `step`
            print(f"detection failed: {exc!r}", file=sys.stderr)
            self.error = exc
        finally:
            self._busy.clear()

    def _crop(self, frame: np.ndarray) -> tuple[np.ndarray, int, int]:
        if self.settings.roi is None:
            return frame, 0, 0
        h, w = frame.shape[:2]
        rx, ry, rw, rh = self.settings.roi
        x0, y0 = int(round(rx * w)), int(round(ry * h))
        x1, y1 = max(int(round((rx + rw) * w)), x0 + 1), max(int(round((ry + rh) * h)), y0 + 1)
        return frame[y0:y1, x0:x1], x0, y0

    def _detect(self, frame: np.ndarray, gap: float | None) -> None:
        crop, dx, dy = self._crop(frame)
        started = time.perf_counter()
        found = self.detector.detect(crop)
        detect_ms = (time.perf_counter() - started) * 1000
        detections = [
            Detection(d.species, d.confidence, (d.box[0] + dx, d.box[1] + dy, d.box[2] + dx, d.box[3] + dy))
            for d in found
        ]
        self._record(frame, detections, gap, detect_ms)

    def _record(self, frame: np.ndarray, detections: list[Detection], gap: float | None, detect_ms: float) -> None:
        s = self.settings
        counts = frame_counts(detections, self._threshold)
        footage_s = s.detect_every_s if gap is None else min(gap, s.max_gap_s)
        credit = footage_s * s.time_scale
        with self._lock:
            self._total_s += credit
            ts = self.clock.at(self._total_s)
        if self._day is not None and ts.date() != self._day:
            self._filter.reset()
            self._recent.clear()
        self._day = ts.date()
        confirmed = self._filter.update(counts)
        arrivals = {sp: max(0, n - max((c[sp] for c in self._recent), default=0)) for sp, n in confirmed.items()}
        self._recent.append(confirmed)
        risen = self.store.record(ts, confirmed, credit, arrivals=arrivals)
        if risen:
            self._save_evidence(frame, detections, confirmed, risen, ts)
        visits, day_max = self._today(ts.date())
        with self._lock:
            self.last_detections = detections
            self._now = {sp: counts.get(sp, 0) for sp in self.detector.species}
            self._confirmed = confirmed
            self._unidentified = len(detections) - sum(counts.values())
            self._detect_ms = detect_ms
            self._visits, self._day_max = visits, day_max
        if self._on_result is not None:
            self._on_result(self.live())

    def _save_evidence(
        self, frame: np.ndarray, detections: list[Detection], confirmed: Mapping[str, int],
        risen: set[str], ts: datetime,
    ) -> None:
        img = annotate(frame, detections, self.names, self._threshold)
        for species in sorted(risen):
            seen = [d.confidence for d in detections if d.species == species and d.confidence >= self._threshold]
            if not seen:
                continue
            rel = f"{ts.date().isoformat()}/{species}.jpg"
            path = self.settings.evidence_dir / rel
            path.parent.mkdir(parents=True, exist_ok=True)
            cv2.imwrite(str(path), img, [cv2.IMWRITE_JPEG_QUALITY, 85])
            self.store.set_evidence(ts, species, confirmed[species], sum(seen) / len(seen), rel)
