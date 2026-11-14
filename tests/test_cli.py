import pytest

from feeder_census import __main__ as cli
from feeder_census.config import Settings


def run_cli(monkeypatch, tmp_path, make_video, *extra):
    """Runs main() up to the Pipeline and returns the Settings it was given."""
    seen = {}

    class StubPipeline:
        error = None

        def __init__(self, camera, detector, store, settings, *args, **kwargs):
            seen["settings"] = settings

        def run(self, stop):
            pass

    monkeypatch.setattr(cli, "Pipeline", StubPipeline)
    script = tmp_path / "script.json"
    script.write_text('{"species": ["great_tit"], "frames": [[]]}')
    video = make_video()
    argv = ["--videos", str(video), "--detector", "scripted", "--script", str(script),
            "--db", str(tmp_path / "data" / "c.db"), "--no-web", *extra]
    assert cli.main(argv) == 0
    return seen["settings"]


def test_detect_every_s_defaults_to_the_settings_default(monkeypatch, tmp_path, make_video):
    settings = run_cli(monkeypatch, tmp_path, make_video)
    assert settings.detect_every_s == Settings.detect_every_s


def test_detect_every_s_flag_sets_the_detection_interval(monkeypatch, tmp_path, make_video):
    settings = run_cli(monkeypatch, tmp_path, make_video, "--detect-every-s", "4")
    assert settings.detect_every_s == 4.0


def test_detect_every_s_must_be_positive():
    with pytest.raises(SystemExit):
        cli._parser().parse_args(["--videos", "x.mp4", "--detect-every-s", "0"])
