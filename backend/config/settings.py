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

MIDDLEWARE = [
    "django.middleware.security.SecurityMiddleware",
    "whitenoise.middleware.WhiteNoiseMiddleware",
    "django.middleware.common.CommonMiddleware",
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

CACHES = {
    "default": {
        "BACKEND": "django.core.cache.backends.locmem.LocMemCache",
        "LOCATION": "weather-aware-truck-routing",
        "OPTIONS": {"MAX_ENTRIES": 20000},
    }
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

SECURE_PROXY_SSL_HEADER = ("HTTP_X_FORWARDED_PROTO", "https")
SECURE_CONTENT_TYPE_NOSNIFF = True

# Third-party services. Each one is a public endpoint; override them to point at your own instances.
ROUTING_PROVIDER = os.environ.get("ROUTING_PROVIDER", "valhalla")
VALHALLA_URL = os.environ.get("VALHALLA_URL", "https://valhalla1.openstreetmap.de")
HERE_API_KEY = os.environ.get("HERE_API_KEY", "")
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
