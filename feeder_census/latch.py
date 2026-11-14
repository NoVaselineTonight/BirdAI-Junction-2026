"""The feeder latch: closes when a squirrel or rat is at the feeder, opens again when it has gone.

`LatchController` holds the rule; `RouterLatch` sends the command to the UNO Q's microcontroller
through the arduino-router service (MessagePack-RPC on a Unix socket), where board/latch/latch.ino
moves the two servos. Bring the hardware up by hand with:

    python -m feeder_census.latch close|open|cycle [--socket PATH]
"""
import argparse
import itertools
import socket
import struct
import sys
import time
from collections.abc import Mapping, Sequence
from dataclasses import dataclass
from pathlib import Path
from typing import Protocol

MODES = ("off", "sim", "router")
ROUTER_SOCKET = Path("/var/run/arduino-router.sock")


class LatchError(OSError):
    """The latch command did not go through. The message says what to check."""


class Latch(Protocol):
    def set(self, closed: bool) -> None: ...  # may raise OSError / LatchError


@dataclass(frozen=True)
class LatchState:
    mode: str  # "off" | "sim" | "router"
    closed: bool
    reason: str | None  # pest key that closed it, None when open
    error: str | None  # last hardware error text, None when the last command went through

    @property
    def headline(self) -> str:
        """What the page may say: "off", "open", "closed", or "not_answering" when the board did not confirm
        the last command (router mode). The page never calls the latch open or closed unconfirmed."""
        if self.mode == "off":
            return "off"
        if self.mode == "router" and self.error is not None:
            return "not_answering"
        return "closed" if self.closed else "open"


class LatchController:
    """Closes after `close_frames` detections in a row with a pest in frame, opens after `open_frames` without.

    In router mode an open command goes out when the controller is made, so the page's "open" is
    confirmed from the start. While closed the close command is sent again at every detection: the
    sketch reopens by itself when it stops hearing it. A command that fails is reported in
    `state.error` and tried again at the next detection; it never stops the caller.
    """

    def __init__(
        self, latch: Latch | None, mode: str, close_frames: int = 2, open_frames: int = 5,
        *, order: Sequence[str] | None = None,
    ):
        if mode not in MODES:
            raise ValueError(f"latch mode must be one of {', '.join(MODES)}, got {mode!r}")
        if mode == "router" and latch is None:
            raise ValueError("latch mode 'router' needs a latch to send commands to")
        if order is None:
            from feeder_census.species import load_pests

            order = [p.key for p in load_pests()]
        self._latch = latch if mode == "router" else None
        self._close_frames, self._open_frames = max(1, close_frames), max(1, open_frames)
        self._order = list(order)
        self._seen = 0  # detections in a row with a pest in frame
        self._clear = 0  # detections in a row without one
        self._resend = False  # the last command failed; send the state again
        self._state = LatchState(mode, False, None, None)
        if self._latch is not None:  # confirm the open latch now, or show at once that the board is not answering
            self._state = LatchState(mode, False, None, self._send(False))

    @property
    def state(self) -> LatchState:
        return self._state

    def update(self, pests_in_frame: Mapping[str, int]) -> LatchState:
        s = self._state
        if s.mode == "off":
            return s
        rank = {key: i for i, key in enumerate(self._order)}
        present = sorted((k for k, n in pests_in_frame.items() if n > 0), key=lambda k: rank.get(k, len(rank)))
        if present:
            self._seen, self._clear = self._seen + 1, 0
        else:
            self._seen, self._clear = 0, self._clear + 1
        closed, reason = s.closed, s.reason
        if not closed and self._seen >= self._close_frames:
            closed = True
        elif closed and self._clear >= self._open_frames:
            closed = False
        if closed and present:
            reason = present[0]
        elif not closed:
            reason = None
        error = s.error
        if self._latch is not None and (closed or closed != s.closed or self._resend):
            error = self._send(closed)
        self._state = LatchState(s.mode, closed, reason, error)
        return self._state

    def _send(self, closed: bool) -> str | None:
        try:
            self._latch.set(closed)
        except Exception as exc:  # a latch fault must never stop the counting
            self._resend = True
            return str(exc) or type(exc).__name__
        self._resend = False
        return None


# --- MessagePack, just the few types the router call needs ---


def _pack(value: object) -> bytes:
    if value is None:
        return b"\xc0"
    if isinstance(value, bool):
        return b"\xc3" if value else b"\xc2"
    if isinstance(value, int) and 0 <= value <= 127:
        return bytes([value])
    if isinstance(value, str):
        raw = value.encode()
        if len(raw) < 32:
            return bytes([0xA0 | len(raw)]) + raw
    if isinstance(value, (list, tuple)) and len(value) < 16:
        return bytes([0x90 | len(value)]) + b"".join(_pack(v) for v in value)
    raise LatchError(f"cannot send {value!r} to the board (only nil, bool, 0-127, short strings and lists)")


def pack_request(msgid: int, method: str, args: list) -> bytes:
    """A MessagePack-RPC request: [0, msgid, method, args]."""
    return _pack([0, msgid, method, list(args)])


class _Incomplete(LatchError):
    """The bytes end before the value does: more may still arrive."""


def _take(data: bytes, at: int, n: int) -> bytes:
    if at + n > len(data):
        raise _Incomplete("the reply from the board ended too early")
    return data[at : at + n]


def _unpack_at(data: bytes, at: int) -> tuple[object, int]:
    b = _take(data, at, 1)[0]
    at += 1
    if b == 0xC0:
        return None, at
    if b in (0xC2, 0xC3):
        return b == 0xC3, at
    if b <= 0x7F:
        return b, at
    if b in (0xCC, 0xCD, 0xCE):
        n = {0xCC: 1, 0xCD: 2, 0xCE: 4}[b]
        return int.from_bytes(_take(data, at, n), "big"), at + n
    if 0xA0 <= b <= 0xBF or b in (0xD9, 0xDA):
        if b == 0xD9:
            n, at = _take(data, at, 1)[0], at + 1
        elif b == 0xDA:
            n, at = struct.unpack(">H", _take(data, at, 2))[0], at + 2
        else:
            n = b & 0x1F
        raw = _take(data, at, n)
        try:
            return raw.decode(), at + n
        except UnicodeDecodeError:
            raise LatchError("the board's reply holds text that is not UTF-8")
    if 0x90 <= b <= 0x9F:
        items = []
        for _ in range(b & 0x0F):
            item, at = _unpack_at(data, at)
            items.append(item)
        return items, at
    raise LatchError(f"the board's reply holds a value this program cannot read (type byte 0x{b:02x})")


def unpack(data: bytes) -> object:
    """One MessagePack value filling all of `data`: nil, bool, unsigned ints, strings and arrays."""
    value, end = _unpack_at(data, 0)
    if end != len(data):
        raise LatchError(f"the board's reply has {len(data) - end} unexpected bytes after it")
    return value


# --- the router link ---


class RouterLatch:
    """Calls `set_latch` on the microcontroller through arduino-router. One connection per call."""

    def __init__(self, socket_path: Path = ROUTER_SOCKET, timeout_s: float = 0.5):
        self.socket_path, self.timeout_s = Path(socket_path), timeout_s
        self._ids = itertools.cycle(range(128))

    def set(self, closed: bool) -> None:
        self.call("set_latch", [bool(closed)])

    def call(self, method: str, args: list) -> object:
        """Sends one request and returns the board's result; any failure raises LatchError."""
        msgid = next(self._ids)
        request = pack_request(msgid, method, args)
        with socket.socket(socket.AF_UNIX, socket.SOCK_STREAM) as sock:
            sock.settimeout(self.timeout_s)
            try:
                sock.connect(str(self.socket_path))
            except FileNotFoundError:
                raise LatchError(f"no router socket at {self.socket_path}")  # short: the page shows it
            except PermissionError:
                raise LatchError(f"no permission to open {self.socket_path}")
            except OSError as exc:
                raise LatchError(f"cannot connect to {self.socket_path}: {exc.strerror or exc}")
            reply = self._read_reply(sock, request, method)
        if not (isinstance(reply, list) and len(reply) == 4 and reply[0] == 1):
            raise LatchError(f"the router sent something that is not a reply: {reply!r}")
        if reply[1] != msgid:
            raise LatchError(f"the router's reply is for request {reply[1]!r}, not {msgid}")
        if reply[2] is not None:
            raise LatchError(f"the board refused {method}: {_error_text(reply[2])}")
        return reply[3]

    def _read_reply(self, sock: socket.socket, request: bytes, method: str) -> object:
        data = b""
        try:
            sock.sendall(request)
            while True:
                chunk = sock.recv(512)
                if not chunk:
                    raise LatchError(f"the router closed the connection before answering {method}")
                data += chunk
                try:
                    return unpack(data)
                except _Incomplete:
                    continue
        except TimeoutError:
            raise LatchError(f"no answer from the board in {self.timeout_s:g} s")
        except LatchError:
            raise
        except OSError as exc:
            raise LatchError(f"lost the connection to {self.socket_path}: {exc.strerror or exc}")


def _error_text(error: object) -> str:
    if isinstance(error, list) and len(error) == 2:  # RPClite sends [code, traceback]
        return f"{error[1]} (code {error[0]})"
    return str(error)


def main(argv: list[str] | None = None) -> int:
    p = argparse.ArgumentParser(prog="python -m feeder_census.latch", description="Move the feeder latch by hand.")
    p.add_argument("command", choices=("close", "open", "cycle"), help="cycle: close, wait 2 s, open")
    p.add_argument("--socket", type=Path, default=ROUTER_SOCKET, help="arduino-router socket (default: %(default)s)")
    args = p.parse_args(argv)
    latch = RouterLatch(args.socket)
    steps = {"close": [True], "open": [False], "cycle": [True, None, False]}[args.command]
    try:
        for closed in steps:
            if closed is None:
                time.sleep(2.0)
                continue
            latch.set(closed)
            word = "closed" if closed else "opened"
            print(f"{word}: the board answered set_latch({str(closed).lower()}) without an error", flush=True)
    except LatchError as exc:
        print(f"error: {exc}", file=sys.stderr)
        print("check that the arduino-router service runs on the board and that board/latch/latch.ino is uploaded "
              "(README.md, Latch)", file=sys.stderr)
        return 1
    return 0


if __name__ == "__main__":
    sys.exit(main())
