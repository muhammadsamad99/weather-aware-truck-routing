from urllib.parse import urlsplit

import pytest
import requests
from django.core.cache import caches

LOCAL_HOSTS = {"127.0.0.1", "localhost", "::1"}
real_send = requests.adapters.HTTPAdapter.send


class LiveServiceCall(AssertionError):
    pass


@pytest.fixture(autouse=True)
def no_live_services(monkeypatch):
    """No test may reach a live service: any request to a host other than this machine fails the test."""

    def guarded_send(adapter, request, *args, **kwargs):
        host = urlsplit(request.url).hostname
        if host not in LOCAL_HOSTS:
            raise LiveServiceCall(f"a test tried to reach {host}")
        return real_send(adapter, request, *args, **kwargs)

    monkeypatch.setattr(requests.adapters.HTTPAdapter, "send", guarded_send)


@pytest.fixture(autouse=True)
def empty_caches():
    for cache in caches.all():
        cache.clear()
    yield
