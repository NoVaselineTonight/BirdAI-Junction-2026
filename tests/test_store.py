import io
from datetime import date, datetime

import pytest

from feeder_census.periods import period_of
from feeder_census.store import SpeciesMismatch, Store


def dt(*a): return datetime(*a)

@pytest.fixture
def s(): return Store(":memory:", ["great_tit", "blue_tit"])

def test_rollup_is_largest_at_once_not_a_sum(s):
    s.record(dt(2026, 11, 3, 9, 10), {"great_tit": 3, "blue_tit": 0}, 120)
    s.record(dt(2026, 11, 3, 9, 40), {"great_tit": 2, "blue_tit": 1}, 120)
    s.record(dt(2026, 11, 3, 13, 0), {"great_tit": 5, "blue_tit": 0}, 120)
    s.record(dt(2026, 11, 9, 10, 0), {"great_tit": 4, "blue_tit": 2}, 120)
    s.record(dt(2026, 11, 16, 10, 0), {"great_tit": 1, "blue_tit": 0}, 120)
    assert [(r.key, r.counts) for r in s.hours(date(2026, 11, 3))] == [
        ("09", {"great_tit": 3, "blue_tit": 1}), ("13", {"great_tit": 5, "blue_tit": 0})]
    assert [r.counts["great_tit"] for r in s.days(period_of(date(2026, 11, 3)))] == [5, 4]
    a, b = s.periods()
    assert (a.key, a.label, a.counts) == ("2026-11-A", "1–15 November 2026", {"great_tit": 5, "blue_tit": 2})
    assert a.hours_watched == pytest.approx(480 / 3600)
    assert b.counts == {"great_tit": 1, "blue_tit": 0}

def test_zero_is_recorded_only_for_watched_hours(s):
    s.record(dt(2026, 11, 3, 9, 0), {}, 120)
    (row,) = s.hours(date(2026, 11, 3))
    assert row.counts == {"great_tit": 0, "blue_tit": 0} and row.hours_watched > 0
    assert s.hours(date(2026, 11, 4)) == []

def test_record_returns_species_with_a_new_day_maximum(s):
    assert s.record(dt(2026, 11, 3, 9, 0), {"great_tit": 2}, 2) == {"great_tit"}
    assert s.record(dt(2026, 11, 3, 9, 1), {"great_tit": 2}, 2) == set()
    assert s.record(dt(2026, 11, 3, 14, 0), {"great_tit": 3, "blue_tit": 1}, 2) == {"great_tit", "blue_tit"}
    assert s.record(dt(2026, 11, 4, 9, 0), {"great_tit": 1}, 2) == {"great_tit"}

def test_evidence_keeps_one_photo_per_day_and_species(s):
    s.set_evidence(dt(2026, 11, 3, 9, 0), "great_tit", 2, 0.81, "2026-11-03/great_tit.jpg")
    s.set_evidence(dt(2026, 11, 3, 14, 0), "great_tit", 3, 0.90, "2026-11-03/great_tit.jpg")
    (e,) = s.evidence()
    assert (e.count, e.confidence, e.ts) == (3, 0.90, dt(2026, 11, 3, 14, 0))

def test_reopen_keeps_counts_and_effort(tmp_path):
    p = tmp_path / "c.db"
    Store(p, ["great_tit"]).record(dt(2026, 11, 3, 9, 0), {"great_tit": 2}, 120)
    again = Store(p, ["great_tit"])
    assert again.total_watched_s() == 120 and again.periods()[0].counts == {"great_tit": 2}

def test_reopen_with_another_species_list_is_refused(tmp_path):
    p = tmp_path / "c.db"; Store(p, ["great_tit"])
    with pytest.raises(SpeciesMismatch, match="great_tit"):
        Store(p, ["great_tit", "blue_tit"])

def test_csv_has_the_form_shape(s):
    s.record(dt(2026, 11, 3, 9, 0), {"great_tit": 5, "blue_tit": 2}, 360)
    out = io.StringIO(); s.export_csv(out, {"great_tit": "Great tit", "blue_tit": "Blue tit"})
    assert out.getvalue().splitlines() == [
        "Period,Hours watched,Great tit,Blue tit", "1–15 November 2026,0.1,5,2"]
