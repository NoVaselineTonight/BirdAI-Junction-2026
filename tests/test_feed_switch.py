import http.client
import importlib.util
import json
import threading
from http.server import ThreadingHTTPServer
from pathlib import Path

import pytest

SWITCH = Path(__file__).resolve().parents[1] / "tools" / "feed_switch" / "switch.py"


@pytest.fixture
def served(monkeypatch):
    spec = importlib.util.spec_from_file_location("feed_switch_under_test", SWITCH)
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    switched = []
    monkeypatch.setattr(module, "switch", lambda to: switched.append(to) or (True, ""))
    monkeypatch.setattr(module, "state", lambda: {"reachable": False})
    server = ThreadingHTTPServer(("127.0.0.1", 0), module.Handler)
    thread = threading.Thread(target=server.serve_forever, daemon=True)
    thread.start()
    yield server.server_address[1], switched
    server.shutdown()
    server.server_close()
    thread.join(5)


def ask(port, method, path, host, body=None):
    conn = http.client.HTTPConnection("127.0.0.1", port, timeout=5)
    headers = {"Host": host, "Content-Type": "application/json"}
    conn.request(method, path, body=None if body is None else json.dumps(body), headers=headers)
    reply = conn.getresponse()
    status = reply.status
    reply.read()
    conn.close()
    return status


@pytest.mark.parametrize("host", ["localhost:{port}", "127.0.0.1:{port}"])
def test_a_switch_from_this_pc_goes_through(served, host):
    port, switched = served
    assert ask(port, "POST", "/switch", host.format(port=port), {"to": "reel"}) == 200
    assert switched == ["reel"]


@pytest.mark.parametrize("host", ["evil.example:{port}", "evil.example", "localhost", "localhost:1", "",
                                  "127.0.0.1.nip.io:{port}"])
def test_a_request_under_another_host_name_is_refused_with_403(served, host):
    port, switched = served
    assert ask(port, "POST", "/switch", host.format(port=port), {"to": "reel"}) == 403
    assert ask(port, "GET", "/state", host.format(port=port)) == 403
    assert switched == []
