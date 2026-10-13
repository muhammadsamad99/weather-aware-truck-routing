"""Reading JSON answers from the routing, weather and place services within a time and size limit.

A request's `timeout` bounds each wait for data, not the whole answer: a server that sends a few bytes now
and then keeps a request (and a server thread) busy indefinitely. So requests are made with `stream=True`
and the body is read here against a deadline and a size cap. It is read with `read1`, which returns whatever
has arrived; `iter_content(n)` would wait for n bytes (or the end) before the deadline could be checked.
"""
import json
import time

DEADLINE_SECONDS = 30.0
MAX_BYTES = 40 * 1024 * 1024  # a coast-to-coast route with alternates is a few MB


class SlowResponse(Exception):
    """The answer took longer than the deadline or was larger than the cap."""


def read_json(resp, deadline_s: float = DEADLINE_SECONDS, max_bytes: int = MAX_BYTES):
    """The response body parsed as JSON. Raises SlowResponse past the deadline or the size cap, and ValueError
    when the body is not JSON. The response is closed either way."""
    deadline = time.monotonic() + deadline_s
    chunks, size = [], 0
    try:
        while chunk := resp.raw.read1(64 * 1024, decode_content=True):
            size += len(chunk)
            if size > max_bytes:
                raise SlowResponse(f"the answer was larger than {max_bytes // (1024 * 1024)} MB")
            if time.monotonic() > deadline:
                raise SlowResponse(f"the answer took longer than {deadline_s:.0f} s")
            chunks.append(chunk)
    finally:
        resp.close()
    return json.loads(b"".join(chunks))
