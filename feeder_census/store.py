import csv
import json
import sqlite3
import threading
from collections.abc import Mapping, Sequence
from dataclasses import dataclass
from datetime import date, datetime
from pathlib import Path
from typing import TextIO

from feeder_census.periods import Period, period_of

_MONTHS = ("Jan", "Feb", "Mar", "Apr", "May", "Jun",
           "Jul", "Aug", "Sep", "Oct", "Nov", "Dec")

_SCHEMA = """
CREATE TABLE IF NOT EXISTS meta (key TEXT PRIMARY KEY, value TEXT NOT NULL);
CREATE TABLE IF NOT EXISTS hour_counts (
    day TEXT NOT NULL, hour INTEGER NOT NULL, species TEXT NOT NULL,
    max_count INTEGER NOT NULL, PRIMARY KEY (day, hour, species));
CREATE TABLE IF NOT EXISTS effort (
    day TEXT NOT NULL, hour INTEGER NOT NULL, watched_s REAL NOT NULL,
    PRIMARY KEY (day, hour));
CREATE TABLE IF NOT EXISTS evidence (
    day TEXT NOT NULL, species TEXT NOT NULL, count INTEGER NOT NULL,
    confidence REAL NOT NULL, ts TEXT NOT NULL, image TEXT NOT NULL,
    PRIMARY KEY (day, species));
"""


class SpeciesMismatch(Exception):
    """The database was created for a different species list."""


@dataclass(frozen=True)
class CountRow:
    key: str
    label: str
    hours_watched: float
    counts: dict[str, int]


@dataclass(frozen=True)
class EvidenceRow:
    day: date
    species: str
    count: int
    confidence: float
    ts: datetime
    image: str


class Store:
    """Counts per hour, kept as the largest number of each species seen at once.

    One connection is shared between threads and every access holds a lock.
    An hour counts as watched exactly when it has an effort row.
    """

    def __init__(self, path: Path | str, species: Sequence[str]):
        self.species: tuple[str, ...] = tuple(species)
        self._lock = threading.Lock()
        self._db = sqlite3.connect(str(path), check_same_thread=False)
        try:
            with self._lock, self._db:
                self._db.executescript(_SCHEMA)
                self._check_species()
        except Exception:
            self._db.close()
            raise

    def _check_species(self) -> None:
        wanted = json.dumps(self.species)
        row = self._db.execute("SELECT value FROM meta WHERE key = 'species'").fetchone()
        if row is None:
            self._db.execute("INSERT INTO meta VALUES ('species', ?)", (wanted,))
        elif row[0] != wanted:
            raise SpeciesMismatch(
                f"This database holds counts for {json.loads(row[0])}, not {list(self.species)}. "
                "Pass another --db path for a different species list.")

    def record(self, ts: datetime, counts: Mapping[str, int], watched_s: float) -> set[str]:
        day, hour = ts.date().isoformat(), ts.hour
        risen: set[str] = set()
        with self._lock, self._db:
            self._db.execute(
                "INSERT INTO effort VALUES (?, ?, ?) "
                "ON CONFLICT (day, hour) DO UPDATE SET watched_s = watched_s + excluded.watched_s",
                (day, hour, watched_s))
            for sp in self.species:
                n = int(counts.get(sp, 0))
                (before,) = self._db.execute(
                    "SELECT COALESCE(MAX(max_count), 0) FROM hour_counts WHERE day = ? AND species = ?",
                    (day, sp)).fetchone()
                self._db.execute(
                    "INSERT INTO hour_counts VALUES (?, ?, ?, ?) "
                    "ON CONFLICT (day, hour, species) DO UPDATE "
                    "SET max_count = MAX(max_count, excluded.max_count)",
                    (day, hour, sp, n))
                if n > 0 and n > before:
                    risen.add(sp)
        return risen

    def set_evidence(self, ts: datetime, species: str, count: int,
                     confidence: float, image: str) -> None:
        with self._lock, self._db:
            self._db.execute(
                "INSERT OR REPLACE INTO evidence VALUES (?, ?, ?, ?, ?, ?)",
                (ts.date().isoformat(), species, count, confidence, ts.isoformat(), image))

    def total_watched_s(self) -> float:
        with self._lock:
            (total,) = self._db.execute("SELECT COALESCE(SUM(watched_s), 0) FROM effort").fetchone()
        return total

    def _zeros(self) -> dict[str, int]:
        return {sp: 0 for sp in self.species}

    def hours(self, day: date) -> list[CountRow]:
        iso = day.isoformat()
        with self._lock:
            watched = self._db.execute(
                "SELECT hour, watched_s FROM effort WHERE day = ? ORDER BY hour", (iso,)).fetchall()
            counts = self._db.execute(
                "SELECT hour, species, max_count FROM hour_counts WHERE day = ?", (iso,)).fetchall()
        per_hour = {hour: self._zeros() for hour, _ in watched}
        for hour, sp, n in counts:
            if hour in per_hour and sp in per_hour[hour]:
                per_hour[hour][sp] = n
        return [CountRow(f"{h:02d}", f"{h:02d}–{h + 1:02d}", s / 3600, per_hour[h])
                for h, s in watched]

    def _day_rows(self, start: date | None = None, end: date | None = None) -> list[tuple[date, float, dict[str, int]]]:
        """Watched days in time order: (day, seconds watched, largest count per species)."""
        lo = start.isoformat() if start else "0000-01-01"
        hi = end.isoformat() if end else "9999-12-31"
        with self._lock:
            watched = self._db.execute(
                "SELECT day, SUM(watched_s) FROM effort WHERE day BETWEEN ? AND ? "
                "GROUP BY day ORDER BY day", (lo, hi)).fetchall()
            maxima = self._db.execute(
                "SELECT day, species, MAX(max_count) FROM hour_counts WHERE day BETWEEN ? AND ? "
                "GROUP BY day, species", (lo, hi)).fetchall()
        per_day = {d: self._zeros() for d, _ in watched}
        for d, sp, n in maxima:
            if d in per_day and sp in per_day[d]:
                per_day[d][sp] = n
        return [(date.fromisoformat(d), s, per_day[d]) for d, s in watched]

    def days(self, period: Period) -> list[CountRow]:
        return [CountRow(d.isoformat(), f"{d.day} {_MONTHS[d.month - 1]}", s / 3600, counts)
                for d, s, counts in self._day_rows(period.start, period.end)]

    def periods(self) -> list[CountRow]:
        grouped: dict[Period, tuple[float, dict[str, int]]] = {}
        for d, s, counts in self._day_rows():
            p = period_of(d)
            secs, best = grouped.setdefault(p, (0.0, self._zeros()))
            for sp, n in counts.items():
                best[sp] = max(best[sp], n)
            grouped[p] = (secs + s, best)
        return [CountRow(p.key, p.label, secs / 3600, best)
                for p, (secs, best) in grouped.items()]

    def evidence(self) -> list[EvidenceRow]:
        with self._lock:
            rows = self._db.execute(
                "SELECT day, species, count, confidence, ts, image FROM evidence "
                "ORDER BY ts DESC").fetchall()
        return [EvidenceRow(date.fromisoformat(d), sp, n, c, datetime.fromisoformat(t), img)
                for d, sp, n, c, t, img in rows]

    def export_csv(self, out: TextIO, names: Mapping[str, str]) -> None:
        w = csv.writer(out)
        w.writerow(["Period", "Hours watched", *(names[sp] for sp in self.species)])
        for row in self.periods():
            w.writerow([row.label, f"{row.hours_watched:.1f}",
                        *(row.counts[sp] for sp in self.species)])
