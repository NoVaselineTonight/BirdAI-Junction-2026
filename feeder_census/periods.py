import calendar
from dataclasses import dataclass
from datetime import date


@dataclass(frozen=True)
class Period:
    """A half-month monitoring period: days 1-15 ("A") or 16-end of month ("B")."""

    start: date
    end: date

    @property
    def key(self) -> str:
        half = "A" if self.start.day == 1 else "B"
        return f"{self.start.year}-{self.start.month:02d}-{half}"

    @property
    def label(self) -> str:
        month = calendar.month_name[self.start.month]
        return f"{self.start.day}–{self.end.day} {month} {self.start.year}"


def period_of(d: date) -> Period:
    if d.day <= 15:
        return Period(d.replace(day=1), d.replace(day=15))
    last_day = calendar.monthrange(d.year, d.month)[1]
    return Period(d.replace(day=16), d.replace(day=last_day))


def period_from_key(key: str) -> Period:
    year, month, half = key.split("-")
    return period_of(date(int(year), int(month), 1 if half == "A" else 16))
