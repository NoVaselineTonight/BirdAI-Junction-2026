import socket
import threading

import pytest

from feeder_census.latch import LatchController, LatchError, RouterLatch, pack_request, unpack

SQ = {"red_squirrel": 1, "brown_rat": 0}
CLEAR = {"red_squirrel": 0, "brown_rat": 0}


class FakeLatch:
    def __init__(self, fail: list[str | None] | None = None):
        self.calls: list[bool] = []
        self._fail = list(fail or [])

    def set(self, closed: bool) -> None:
        self.calls.append(closed)
        if self._fail:
            message = self._fail.pop(0)
            if message is not None:
                raise LatchError(message)


def test_closes_after_two_detections_and_reopens_after_five_clear():
    c = LatchController(FakeLatch(), "router")
    assert c.update(SQ).closed is False
    state = c.update(SQ)
    assert state.closed is True and state.reason == "red_squirrel" and state.error is None
    for _ in range(4):
        assert c.update(CLEAR).closed is True
    state = c.update(CLEAR)
    assert state.closed is False and state.reason is None
    assert c.state == state


def test_one_clear_detection_does_not_open():
    c = LatchController(FakeLatch(), "router")
    c.update(SQ), c.update(SQ)
    assert c.update(CLEAR).closed is True
    assert c.update(SQ).closed is True
    for _ in range(4):
        assert c.update(CLEAR).closed is True  # the count of clear detections started over
    assert c.update(CLEAR).closed is False


def test_a_single_pest_detection_does_not_close():
    latch = FakeLatch()
    c = LatchController(latch, "router")
    for frame in (SQ, CLEAR, SQ, CLEAR):
        assert c.update(frame).closed is False
    assert latch.calls == []


def test_close_is_resent_at_every_detection_while_closed():
    latch = FakeLatch()
    c = LatchController(latch, "router")
    for frame in (SQ, SQ, SQ, CLEAR, CLEAR, CLEAR, CLEAR, CLEAR, CLEAR, CLEAR):
        c.update(frame)
    # closed at the 2nd detection, still closed through the 3rd to the 7th (4 clear), opened at the 8th
    assert latch.calls == [True] * 6 + [False]


def test_hardware_error_is_reported_and_the_rule_carries_on():
    latch = FakeLatch(fail=["no socket", None])
    c = LatchController(latch, "router")
    c.update(SQ)
    state = c.update(SQ)
    assert state.closed is True and state.error == "no socket" and state.mode == "router"
    state = c.update(SQ)
    assert state.closed is True and state.error is None
    assert latch.calls == [True, True]


def test_a_failed_open_is_tried_again_at_the_next_detection():
    latch = FakeLatch(fail=[None, "timed out", None])
    c = LatchController(latch, "router", close_frames=1, open_frames=1)
    c.update(SQ)
    state = c.update(CLEAR)
    assert state.closed is False and state.error == "timed out"
    state = c.update(CLEAR)
    assert state.error is None
    c.update(CLEAR)
    assert latch.calls == [True, False, False]


def test_any_exception_from_the_latch_is_caught():
    class Broken:
        def set(self, closed):
            raise RuntimeError

    c = LatchController(Broken(), "router", close_frames=1)
    state = c.update(SQ)
    assert state.closed is True and state.error == "RuntimeError"


def test_off_mode_never_closes_and_sim_mode_follows_the_rule_without_hardware():
    off = LatchController(None, "off")
    for _ in range(5):
        state = off.update(SQ)
    assert state == off.state and (state.mode, state.closed, state.reason, state.error) == ("off", False, None, None)
    sim = LatchController(None, "sim")
    sim.update(SQ)
    state = sim.update(SQ)
    assert (state.mode, state.closed, state.reason, state.error) == ("sim", True, "red_squirrel", None)


def test_reason_is_the_first_pest_in_species_order():
    c = LatchController(None, "sim", close_frames=1)
    assert c.update({"brown_rat": 1, "red_squirrel": 2}).reason == "red_squirrel"
    c = LatchController(None, "sim", close_frames=1)
    assert c.update({"brown_rat": 1, "red_squirrel": 0}).reason == "brown_rat"


def test_reason_follows_the_pest_that_is_there_and_stays_while_none_is():
    c = LatchController(None, "sim", close_frames=1)
    c.update({"red_squirrel": 1, "brown_rat": 0})
    assert c.update({"red_squirrel": 0, "brown_rat": 1}).reason == "brown_rat"
    assert c.update(CLEAR).reason == "brown_rat"


def test_pests_of_different_kinds_in_a_row_close_it():
    c = LatchController(None, "sim")
    c.update({"red_squirrel": 1, "brown_rat": 0})
    assert c.update({"red_squirrel": 0, "brown_rat": 1}).closed is True


def test_unknown_modes_are_refused():
    with pytest.raises(ValueError):
        LatchController(None, "on")
    with pytest.raises(ValueError):
        LatchController(None, "router")  # router needs hardware to talk to


def test_pack_request_bytes():
    assert pack_request(1, "set_latch", [True]) == bytes.fromhex("940001a97365745f6c6174636891c3")
    assert pack_request(5, "set_latch", [False]) == bytes.fromhex("940005a97365745f6c6174636891c2")
    assert pack_request(2, "get_latch", []) == bytes.fromhex("940002a9") + b"get_latch" + bytes.fromhex("90")
    with pytest.raises(LatchError):
        pack_request(200, "set_latch", [True])
    with pytest.raises(LatchError):
        pack_request(1, "x" * 32, [])
    with pytest.raises(LatchError):
        pack_request(1, "set_latch", [1.5])


def test_unpack_reply():
    assert unpack(bytes.fromhex("940101c0c0")) == [1, 1, None, None]
    assert unpack(bytes.fromhex("940101c0c3")) == [1, 1, None, True]
    assert unpack(bytes.fromhex("ccff")) == 255
    assert unpack(bytes.fromhex("cd0102")) == 258
    assert unpack(bytes.fromhex("ce00010000")) == 65536
    assert unpack(bytes.fromhex("d903") + b"abc") == "abc"
    assert unpack(bytes.fromhex("92ccfea3") + b"bad") == [254, "bad"]
    for garbage in ("", "94", "940101c0", "c1", "ff", "cb3ff0000000000000", "940101c0c0c0", "d905616263"):
        with pytest.raises(LatchError):
            unpack(bytes.fromhex(garbage))


def serve_once(path, reply_for, accept_timeout=5.0):
    """A Unix socket at `path` answering one request; returns (thread, list of requests received)."""
    server = socket.socket(socket.AF_UNIX, socket.SOCK_STREAM)
    server.bind(str(path))
    server.listen(1)
    server.settimeout(accept_timeout)
    seen: list[bytes] = []

    def run():
        try:
            conn, _ = server.accept()
        except OSError:
            return
        with conn:
            conn.settimeout(accept_timeout)
            data = conn.recv(256)
            seen.append(data)
            reply = reply_for(data)
            if reply is not None:
                # in two pieces, as a stream socket may deliver it
                conn.sendall(reply[:2])
                conn.sendall(reply[2:])
            else:
                conn.recv(1)  # say nothing until the client gives up
        server.close()

    thread = threading.Thread(target=run, daemon=True)
    thread.start()
    return thread, seen


def test_router_latch_talks_to_a_socket(tmp_path):
    path = tmp_path / "router.sock"
    thread, seen = serve_once(path, lambda req: bytes([0x94, 0x01, req[2], 0xC0, 0xC0]))
    RouterLatch(path).set(True)
    thread.join(5)
    (request,) = seen
    msgid = request[2]
    assert request == pack_request(msgid, "set_latch", [True])


def test_router_latch_errors(tmp_path):
    with pytest.raises(LatchError, match="no router socket"):
        RouterLatch(tmp_path / "missing.sock").set(True)

    path = tmp_path / "error.sock"
    thread, _ = serve_once(path, lambda req: bytes([0x94, 0x01, req[2], 0x92, 0xCC, 0xFE, 0xA3]) + b"nop" + b"\xc0")
    with pytest.raises(LatchError, match="nop"):
        RouterLatch(path).set(False)
    thread.join(5)

    path = tmp_path / "silent.sock"
    thread, _ = serve_once(path, lambda req: None)
    with pytest.raises(LatchError, match="no answer"):
        RouterLatch(path, timeout_s=0.2).set(True)
    thread.join(5)

    path = tmp_path / "wrong.sock"
    thread, _ = serve_once(path, lambda req: bytes([0x94, 0x01, (req[2] + 1) % 128, 0xC0, 0xC0]))
    with pytest.raises(LatchError, match="reply"):
        RouterLatch(path).set(True)
    thread.join(5)

    path = tmp_path / "closed.sock"
    thread, _ = serve_once(path, lambda req: b"\x94\x01")
    with pytest.raises(LatchError):
        RouterLatch(path, timeout_s=0.5).set(True)
    thread.join(5)


def test_latch_errors_are_os_errors():
    assert issubclass(LatchError, OSError)


def test_command_line_cycle_reports_what_the_board_said(tmp_path, monkeypatch, capsys):
    from feeder_census import latch as module

    sent = []

    class Recorder:
        def __init__(self, socket_path, timeout_s=0.5):
            sent.append(("socket", socket_path))

        def set(self, closed):
            sent.append(closed)

    monkeypatch.setattr(module, "RouterLatch", Recorder)
    monkeypatch.setattr(module.time, "sleep", lambda s: sent.append(("sleep", s)))
    assert module.main(["cycle", "--socket", str(tmp_path / "s")]) == 0
    assert sent == [("socket", tmp_path / "s"), True, ("sleep", 2.0), False]
    assert "closed" in capsys.readouterr().out


def test_command_line_exits_1_on_a_latch_error(tmp_path, capsys):
    from feeder_census import latch as module

    assert module.main(["close", "--socket", str(tmp_path / "missing.sock")]) == 1
    assert "no router socket" in capsys.readouterr().err
