from feeder_census.census import ConfirmFilter, frame_counts
from feeder_census.types import Detection


def D(species, conf): return Detection(species, conf, (0, 0, 10, 10))


def test_frame_counts_only_sure_identifications():
    dets = [D("great_tit", 0.9), D("great_tit", 0.59), D("blue_tit", 0.6), D("unidentified", 0.99)]
    assert frame_counts(dets, threshold=0.6) == {"great_tit": 1, "blue_tit": 1}


def test_single_frame_spike_is_not_counted():
    f = ConfirmFilter(["great_tit", "blue_tit"], confirm_frames=2)
    assert f.update({"great_tit": 2}) == {"great_tit": 0, "blue_tit": 0}
    assert f.update({"great_tit": 5}) == {"great_tit": 2, "blue_tit": 0}
    assert f.update({"great_tit": 1}) == {"great_tit": 1, "blue_tit": 0}


def test_reset_forgets_earlier_frames():
    f = ConfirmFilter(["great_tit"], confirm_frames=2)
    f.update({"great_tit": 3}); f.reset()
    assert f.update({"great_tit": 3}) == {"great_tit": 0}


def test_confirm_frames_one_passes_counts_through():
    assert ConfirmFilter(["great_tit"], confirm_frames=1).update({"great_tit": 4}) == {"great_tit": 4}
