import json
import threading
import urllib.error
import urllib.request

import pytest

from feeder_census.calibrate import make_server
from feeder_census.latch import LatchError


class FakeBoard:
    def __init__(self):
        self.calls: list[tuple] = []
        self.fail: str | None = None

    def _go(self, *call):
        self.calls.append(call)
        if self.fail:
            raise LatchError(self.fail)

    def set_angle(self, degrees):
        self._go("set_angle", degrees)
        return degrees

    def set_limits(self, open_degrees, closed_degrees):
        self._go("set_limits", open_degrees, closed_degrees)

    def set(self, closed):
        self._go("set", closed)


@pytest.fixture
def served(tmp_path):
    board = FakeBoard()
    angles = tmp_path / "data" / "latch_angles.json"
    server = make_server(board, angles, "127.0.0.1", 0)
    thread = threading.Thread(target=server.serve_forever, daemon=True)
    thread.start()
    base = f"http://127.0.0.1:{server.server_address[1]}"
    yield base, board, angles
    server.shutdown()
    server.server_close()
    thread.join(5)


def request(base, path, body=None, raw=None):
    data = raw if raw is not None else (None if body is None else json.dumps(body).encode())
    req = urllib.request.Request(base + path, data=data, method="GET" if data is None else "POST",
                                 headers={"Content-Type": "application/json"})
    try:
        with urllib.request.urlopen(req, timeout=5) as r:
            return r.status, r.read()
    except urllib.error.HTTPError as e:
        return e.code, e.read()


def call(base, path, body=None, raw=None):
    status, data = request(base, path, body, raw)
    return status, json.loads(data)


def test_the_page_is_one_plain_html_document(served):
    base, _, _ = served
    status, data = request(base, "/")
    html = data.decode()
    assert status == 200 and html.lstrip().lower().startswith("<!doctype html>")
    for text in ("Save as OPEN", "Save as CLOSED", "Test: open", "Test: close", "Board not answering",
                 "color-scheme", "data/latch_angles.json"):
        assert text in html
    for outside in ("http://", "https://", "src=\"//"):
        assert outside not in html


def test_state_before_anything_is_set_shows_the_defaults(served):
    base, _, _ = served
    assert call(base, "/state") == (200, {"angle": None, "open": 10, "closed": 100, "saved": False, "error": None})


def test_state_shows_the_saved_angles(tmp_path):
    (tmp_path / "a.json").write_text('{"open": 20, "closed": 150}')
    board = FakeBoard()
    server = make_server(board, tmp_path / "a.json", "127.0.0.1", 0)
    thread = threading.Thread(target=server.serve_forever, daemon=True)
    thread.start()
    try:
        state = call(f"http://127.0.0.1:{server.server_address[1]}", "/state")[1]
    finally:
        server.shutdown()
        server.server_close()
    assert state["open"] == 20 and state["closed"] == 150 and state["saved"] is True


def test_angle_turns_the_servo(served):
    base, board, _ = served
    assert call(base, "/angle", {"degrees": 95}) == (200, {"angle": 95})
    assert board.calls == [("set_angle", 95)]
    assert call(base, "/state")[1]["angle"] == 95
    assert call(base, "/angle", {"degrees": 0})[0] == 200 and call(base, "/angle", {"degrees": 180})[0] == 200


@pytest.mark.parametrize("body", [{"degrees": -1}, {"degrees": 181}, {"degrees": 1.5}, {"degrees": "90"},
                                  {"degrees": True}, {}, {"degrees": None}, [1]])
def test_angle_rejects_bad_values(served, body):
    base, board, _ = served
    status, reply = call(base, "/angle", body)
    assert status == 400 and reply["error"]
    assert board.calls == []


def test_angle_rejects_a_body_that_is_not_json(served):
    base, board, _ = served
    status, reply = call(base, "/angle", raw=b"{nope")
    assert status == 400 and reply["error"] and board.calls == []


def test_save_before_any_angle_is_refused(served):
    base, board, angles = served
    status, reply = call(base, "/save", {"which": "open"})
    assert status == 400 and "angle" in reply["error"]
    assert board.calls == [] and not angles.exists()


def test_save_writes_the_file_and_sends_the_limits(served):
    base, board, angles = served
    call(base, "/angle", {"degrees": 25})
    status, reply = call(base, "/save", {"which": "open"})
    assert status == 200 and reply == {"open": 25, "closed": 100, "saved": True}
    assert json.loads(angles.read_text()) == {"open": 25, "closed": 100}
    call(base, "/angle", {"degrees": 140})
    assert call(base, "/save", {"which": "closed"})[1]["closed"] == 140
    assert json.loads(angles.read_text()) == {"open": 25, "closed": 140}
    assert board.calls[-1] == ("set_limits", 25, 140)
    state = call(base, "/state")[1]
    assert (state["open"], state["closed"], state["saved"]) == (25, 140, True)


@pytest.mark.parametrize("which", ["both", "OPEN", None, 1])
def test_save_rejects_a_wrong_which(served, which):
    base, board, angles = served
    call(base, "/angle", {"degrees": 25})
    status, reply = call(base, "/save", {"which": which})
    assert status == 400 and reply["error"]
    assert board.calls == [("set_angle", 25)] and not angles.exists()


def test_test_runs_set_latch(served):
    base, board, _ = served
    assert call(base, "/test", {"closed": True})[0] == 200
    assert call(base, "/test", {"closed": False})[0] == 200
    assert board.calls == [("set", True), ("set", False)]
    assert call(base, "/test", {"closed": "yes"})[0] == 400
    assert call(base, "/test", {})[0] == 400
    assert len(board.calls) == 2


def test_a_board_that_does_not_answer_gives_502_and_the_server_carries_on(served):
    base, board, _ = served
    board.fail = "no answer from the board in 0.5 s"
    for path, body in (("/angle", {"degrees": 50}), ("/test", {"closed": True})):
        assert call(base, path, body) == (502, {"error": "no answer from the board in 0.5 s"})
    state = call(base, "/state")[1]
    assert state["error"] == "no answer from the board in 0.5 s" and state["angle"] is None
    board.fail = None
    assert call(base, "/angle", {"degrees": 50})[0] == 200
    assert call(base, "/state")[1]["error"] is None


def test_a_failed_set_limits_on_save_is_a_502(served):
    base, board, _ = served
    call(base, "/angle", {"degrees": 25})
    board.fail = "the board refused set_limits: nope"
    status, reply = call(base, "/save", {"which": "open"})
    assert status == 502 and "set_limits" in reply["error"]
    assert call(base, "/state")[0] == 200


def test_unknown_paths_are_404(served):
    base, _, _ = served
    assert request(base, "/nope")[0] == 404
    assert request(base, "/nope", {})[0] == 404


def test_the_command_line_refuses_a_broken_angles_file(tmp_path, capsys):
    from feeder_census import calibrate

    bad = tmp_path / "latch_angles.json"
    bad.write_text("not json")
    assert calibrate.main(["--port", "0", "--angles-file", str(bad)]) == 1
    assert "latch_angles.json" in capsys.readouterr().err
