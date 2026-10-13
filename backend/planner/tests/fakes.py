import io
import json


class FakeRaw(io.BytesIO):
    def read1(self, size=-1, decode_content=None):
        return super().read1(size)


class FakeResponse:
    """A streamed `requests` response carrying `data` as JSON (or, for None, a body that is not JSON)."""

    def __init__(self, status, data):
        self.status_code, self.closed = status, False
        self.raw = FakeRaw(b"<html>Bad Gateway</html>" if data is None else json.dumps(data).encode())

    def close(self):
        self.closed = True
