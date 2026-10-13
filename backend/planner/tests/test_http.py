import socket
import threading
import time

import pytest
import requests

from planner.http import SlowResponse, read_json
from planner.tests.fakes import FakeResponse


def trickling_server(body: bytes, pause: float):
    """A local HTTP server that sends its headers at once and then the body one byte every `pause` seconds."""
    listener = socket.socket()
    listener.bind(("127.0.0.1", 0))
    listener.listen(1)

    def serve():
        conn, _ = listener.accept()
        conn.recv(65536)
        conn.sendall(b"HTTP/1.1 200 OK\r\nContent-Type: application/json\r\nContent-Length: "
                     + str(len(body)).encode() + b"\r\n\r\n")
        try:
            for byte in body:
                conn.sendall(bytes([byte]))
                time.sleep(pause)
        except OSError:
            pass  # the client gave up, as it should
        finally:
            conn.close()
            listener.close()

    threading.Thread(target=serve, daemon=True).start()
    return f"http://127.0.0.1:{listener.getsockname()[1]}/"


def test_a_server_that_trickles_its_answer_is_given_up_at_the_deadline():
    # each byte arrives well inside the request timeout, so only a deadline on the whole body can stop it
    url = trickling_server(b'{"trip": "' + b"x" * 200 + b'"}', pause=0.05)
    resp = requests.get(url, timeout=1, stream=True)
    started = time.monotonic()
    with pytest.raises(SlowResponse, match="longer than"):
        read_json(resp, deadline_s=0.5)
    assert time.monotonic() - started < 1.5


def test_a_prompt_answer_is_read_in_full():
    url = trickling_server(b'{"ok": true}', pause=0)
    assert read_json(requests.get(url, timeout=1, stream=True)) == {"ok": True}


def test_an_oversized_or_non_json_answer_is_refused_and_the_response_closed():
    big = FakeResponse(200, {"x": "y" * 5000})
    with pytest.raises(SlowResponse, match="larger than"):
        read_json(big, max_bytes=1000)
    assert big.closed
    with pytest.raises(ValueError):
        read_json(FakeResponse(502, None))


def test_the_test_suite_cannot_reach_a_live_service():
    from planner.conftest import LiveServiceCall

    with pytest.raises(LiveServiceCall, match="photon.komoot.io"):
        requests.get("https://photon.komoot.io/api/?q=Boise", timeout=1)
