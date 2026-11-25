from datetime import date

from feeder_census.periods import period_from_key, period_of


def test_half_month_boundaries():
    assert period_of(date(2026, 11, 15)).key == "2026-11-A"
    assert period_of(date(2026, 11, 16)).key == "2026-11-B"
    assert period_of(date(2026, 11, 16)).end == date(2026, 11, 30)
    assert period_of(date(2027, 2, 20)).end == date(2027, 2, 28)
    assert period_of(date(2028, 2, 20)).end == date(2028, 2, 29)


def test_labels_match_the_monitoring_form():
    assert period_of(date(2026, 11, 1)).label == "1–15 November 2026"
    assert period_of(date(2026, 12, 31)).label == "16–31 December 2026"


def test_key_round_trip():
    assert period_from_key("2026-11-B") == period_of(date(2026, 11, 20))
