"""Django settings. Everything that differs between a laptop and Render comes from the environment."""
import os
from pathlib import Path

BASE_DIR = Path(__file__).resolve().parent.parent
FRONTEND_DIST = BASE_DIR.parent / "frontend" / "dist"

DEBUG = os.environ.get("DJANGO_DEBUG", "0") == "1"
SECRET_KEY = os.environ.get("DJANGO_SECRET_KEY") or ("dev-only-insecure-key" if DEBUG else None)
if not SECRET_KEY:
    raise RuntimeError("Set DJANGO_SECRET_KEY (or DJANGO_DEBUG=1 for local development).")

ALLOWED_HOSTS = [
    h.strip() for h in os.environ.get("DJANGO_ALLOWED_HOSTS", "localhost,127.0.0.1").split(",") if h.strip()
]
if os.environ.get("RENDER_EXTERNAL_HOSTNAME"):
    ALLOWED_HOSTS.append(os.environ["RENDER_EXTERNAL_HOSTNAME"])
CSRF_TRUSTED_ORIGINS = [f"https://{h}" for h in ALLOWED_HOSTS if h not in ("localhost", "127.0.0.1")]

INSTALLED_APPS = [
    "django.contrib.staticfiles",
    "rest_framework",
    "planner",
]

# No sessions, cookies or logins: the API keeps no state and changes nothing on the server, so there is
# nothing for cross-site request forgery to abuse, and the CSRF middleware is left out.
MIDDLEWARE = [
    "django.middleware.security.SecurityMiddleware",
    "whitenoise.middleware.WhiteNoiseMiddleware",
    "django.middleware.gzip.GZipMiddleware",  # API answers only; WhiteNoise serves the app pre-compressed
    "django.middleware.common.CommonMiddleware",
    "django.middleware.clickjacking.XFrameOptionsMiddleware",
]

ROOT_URLCONF = "config.urls"
WSGI_APPLICATION = "config.wsgi.application"

TEMPLATES = [
    {
        "BACKEND": "django.template.backends.django.DjangoTemplates",
        "DIRS": [],
        "APP_DIRS": True,
        "OPTIONS": {"context_processors": []},
    }
]

# The app keeps no data of its own: routes and forecasts are fetched per request and cached.
DATABASES = {}

# Sized for a 512 MB instance: a forecast series is about 10 KB and a cached trip's routes 1-3 MB.
CACHES = {
    "default": {
        "BACKEND": "django.core.cache.backends.locmem.LocMemCache",
        "LOCATION": "forecasts-and-places",
        "OPTIONS": {"MAX_ENTRIES": 6000},
    },
    "routes": {
        "BACKEND": "django.core.cache.backends.locmem.LocMemCache",
        "LOCATION": "routes",
        "OPTIONS": {"MAX_ENTRIES": 40},
    },
}

REST_FRAMEWORK = {
    "DEFAULT_RENDERER_CLASSES": ["rest_framework.renderers.JSONRenderer"],
    "DEFAULT_PARSER_CLASSES": ["rest_framework.parsers.JSONParser"],
    "DEFAULT_AUTHENTICATION_CLASSES": [],
    "DEFAULT_PERMISSION_CLASSES": [],
    "UNAUTHENTICATED_USER": None,
}

LANGUAGE_CODE = "en-us"
TIME_ZONE = "UTC"
USE_TZ = True

STATIC_URL = "/static/"
STATIC_ROOT = BASE_DIR / "staticfiles"
# The built React app (frontend/dist) is served from the site root by WhiteNoise.
WHITENOISE_ROOT = FRONTEND_DIST if FRONTEND_DIST.exists() else None
WHITENOISE_INDEX_FILE = True
# Vite puts a content hash in every asset's name, so those can be cached for good.
WHITENOISE_IMMUTABLE_FILE_TEST = r"^/assets/.+-[A-Za-z0-9_-]{8}\.(?:js|css)$"

# The app's page may load scripts only from this site, map tiles, fonts and sprites only from OpenFreeMap,
# and may not be framed. MapLibre draws on workers made from blob: URLs.
MAP_HOST = "https://tiles.openfreemap.org"
CONTENT_SECURITY_POLICY = "; ".join([
    "default-src 'self'",
    "script-src 'self'",
    "style-src 'self' 'unsafe-inline'",
    f"img-src 'self' data: blob: {MAP_HOST}",
    f"connect-src 'self' {MAP_HOST}",
    "worker-src 'self' blob:",
    "child-src blob:",
    "font-src 'self'",
    "object-src 'none'",
    "base-uri 'none'",
    "form-action 'self'",
    "frame-ancestors 'none'",
])


def _page_headers(headers, path, url):
    if path.endswith(".html"):
        headers["Content-Security-Policy"] = CONTENT_SECURITY_POLICY
        headers["X-Frame-Options"] = "DENY"
        headers["Referrer-Policy"] = "same-origin"
    headers["X-Content-Type-Options"] = "nosniff"


WHITENOISE_ADD_HEADERS_FUNCTION = _page_headers

SECURE_PROXY_SSL_HEADER = ("HTTP_X_FORWARDED_PROTO", "https")
SECURE_CONTENT_TYPE_NOSNIFF = True

# Third-party services. Each one is a public endpoint; override them to point at your own instances.
ROUTING_PROVIDER = os.environ.get("ROUTING_PROVIDER", "valhalla")
VALHALLA_URL = os.environ.get("VALHALLA_URL", "https://valhalla1.openstreetmap.de")
# The public server's usage policy (FOSSGIS): at most one request per second. Set 0 for your own server.
VALHALLA_MIN_INTERVAL_SECONDS = float(os.environ.get("VALHALLA_MIN_INTERVAL_SECONDS", "1.0"))
OPEN_METEO_URL = os.environ.get("OPEN_METEO_URL", "https://api.open-meteo.com/v1/forecast")
PHOTON_URL = os.environ.get("PHOTON_URL", "https://photon.komoot.io/api/")
HTTP_USER_AGENT = "weather-aware-truck-routing/1.0 (+https://github.com/muhammadsamad99/weather-aware-truck-routing)"
HTTP_TIMEOUT_SECONDS = float(os.environ.get("HTTP_TIMEOUT_SECONDS", "20"))

LOGGING = {
    "version": 1,
    "disable_existing_loggers": False,
    "handlers": {"console": {"class": "logging.StreamHandler"}},
    "root": {"handlers": ["console"], "level": os.environ.get("LOG_LEVEL", "INFO")},
}
