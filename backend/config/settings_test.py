"""Settings for the test run: a fixed key and private caches. Outside calls are refused by planner/conftest.py."""
import os

os.environ.setdefault("DJANGO_SECRET_KEY", "test-only-key")

from .settings import *  # noqa: E402,F403

CACHES = {
    "default": {"BACKEND": "django.core.cache.backends.locmem.LocMemCache", "LOCATION": "tests"},
    "routes": {"BACKEND": "django.core.cache.backends.locmem.LocMemCache", "LOCATION": "tests-routes"},
}
