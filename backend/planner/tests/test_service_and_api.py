import json
from datetime import UTC, datetime, timedelta

import pytest
from django.core.cache import cache
from django.test import Client, override_settings

from planner import service
from planner.geo import cumulative_miles, offset_point
from planner.geocode import Place
from planner.providers.base import RouteOption, RoutingError
from planner.risk import HIGH, LOW, NO_TRAVEL
from planner.weather import ForecastRangeError, HourWeather, WeatherError

DEPARTURE = (datetime.now(UTC) + timedelta(days=1)).replace(hour=11, minute=0, second=0, microsecond=0)
ORIGIN = Place("Origin", 40.0, -90.0)


def route(name, bearing, miles, mph=60.0):
    pts = [offset_point((40.0, -90.0), bearing, m) for m in range(int(miles) + 1)]
    cum = cumulative_miles(pts)
    return RouteOption(name=name, points=tuple(pts), miles=tuple(cum), seconds=tuple(m / mph * 3600 for m in cum),
                       provider="fake")


class FakeProvider:
    name = "fake"

    def __init__(self, routes):
        self._routes, self.calls = routes, 0

    def routes(self, origin, destination, load_lb, count=3):
        self.calls += 1
        return self._routes


class FakeForecasts:
    """Weather by rule: `weather(lat, lon, moment)` decides each reading."""

    def __init__(self, weather):
        self.weather, self.loaded = weather, []

    def load(self, locations, start, end):
        self.loaded.append((len(locations), start, end))

    def at(self, lat, lon, moment):
        return self.weather(lat, lon, moment)


def calm(lat, lon, moment):
    return HourWeather(wind_mph=5, rain_in_hr=0, snow_in_hr=0)


@pytest.fixture(autouse=True)
def clear_cache():
    cache.clear()


def trip(load=20_000, interval=25):
    destination = Place("Destination", *offset_point((40.0, -90.0), 0, 100))
    return service.TripRequest(origin=ORIGIN, destination=destination, departure=DEPARTURE, load_lb=load,
                               interval_mi=interval)


def test_the_plan_recommends_the_route_that_avoids_rain():
    north, east, west = route("Route A", 0, 100), route("Route B", 45, 110), route("Route C", 315, 120)
    # heavy rain on every point north-east of the start: Route B crosses it, the others don't
    def weather(lat, lon, moment):
        rain = 0.3 if (lon > -89.95 and lat > 40.05) else 0.0
        return HourWeather(wind_mph=5, rain_in_hr=rain, snow_in_hr=0)

    plan = service.plan_trip(trip(), provider=FakeProvider([east, north, west]), forecasts=FakeForecasts(weather))
    assert plan["recommended"] == "Route A"
    by_name = {r["name"]: r for r in plan["routes"]}
    assert by_name["Route B"]["risk"]["high_miles"] > 0
    assert by_name["Route A"]["risk"]["high_miles"] == 0
    assert [r["rank"] for r in plan["routes"]] == [3, 1, 2]
    assert plan["reason"] == "Same weather risk as the next route; shorter travel time (1 h 40 min vs 2 h 00 min)."
    cps = by_name["Route B"]["checkpoints"]
    assert [c["mile"] for c in cps] == [0, 25, 50, 75, 100, 110]
    assert all(c["level"] in (LOW, HIGH) for c in cps)
    assert cps[1]["eta"] == (DEPARTURE + timedelta(minutes=25)).replace(microsecond=0).isoformat()


def test_heavy_wind_with_a_heavy_load_is_no_travel_and_never_recommended_over_a_passable_route():
    windy, calm_route = route("Route A", 0, 100), route("Route B", 90, 150)

    def weather(lat, lon, moment):
        return HourWeather(wind_mph=48 if lat > 40.5 else 5, rain_in_hr=0, snow_in_hr=0)

    plan = service.plan_trip(trip(load=36_000), provider=FakeProvider([windy, calm_route]),
                             forecasts=FakeForecasts(weather))
    assert plan["recommended"] == "Route B"
    windy_json = next(r for r in plan["routes"] if r["name"] == "Route A")
    assert windy_json["risk"]["no_travel_miles"] > 0
    assert any(c["level"] == NO_TRAVEL and "load 36,000 lb" in c["reasons"] for c in windy_json["checkpoints"])
    assert "No Travel" in plan["reason"]


def test_the_heatmap_has_one_frame_per_hour_for_48_hours():
    calls = []

    def weather(lat, lon, moment):
        calls.append(moment)
        return HourWeather(wind_mph=60 if moment >= DEPARTURE + timedelta(hours=24) else 5, rain_in_hr=0, snow_in_hr=0)

    plan = service.plan_trip(trip(), provider=FakeProvider([route("Route A", 0, 100)]),
                             forecasts=FakeForecasts(weather))
    h = plan["heatmap"]
    assert h["hours"] == 48 and len(h["frames"]) == 49
    assert all(len(f) == len(h["points"]) for f in h["frames"])
    assert h["step_deg"] > 0
    assert max(h["frames"][0]) == LOW and min(h["frames"][24]) == NO_TRAVEL
    assert plan["reason"] == "Only one route was found."


def test_routes_are_cached_between_plans():
    provider = FakeProvider([route("Route A", 0, 100)])
    for _ in range(2):
        service.plan_trip(trip(), provider=provider, forecasts=FakeForecasts(calm))
    assert provider.calls == 1


def test_the_same_place_twice_is_refused():
    t = service.TripRequest(origin=ORIGIN, destination=ORIGIN, departure=DEPARTURE, load_lb=1000, interval_mi=10)
    with pytest.raises(RoutingError, match="same place"):
        service.plan_trip(t, provider=FakeProvider([]), forecasts=FakeForecasts(calm))


# ---- the HTTP API ----

def post(body):
    return Client().post("/api/plan", data=json.dumps(body), content_type="application/json")


def valid_body(**over):
    body = {"origin": {"label": "Origin", "lat": 40.0, "lon": -90.0},
            "destination": {"label": "Dest", "lat": 41.4, "lon": -90.0},
            "departure": DEPARTURE.isoformat(), "load_lb": 20000, "interval_mi": 25}
    body.update(over)
    return body


@override_settings(ALLOWED_HOSTS=["testserver"])
def test_bad_input_is_a_400_with_the_fields_named():
    r = post(valid_body(load_lb=0, interval_mi=15, departure="2020-01-01T00:00:00Z"))
    assert r.status_code == 400
    assert set(r.json()["fields"]) == {"load_lb", "interval_mi", "departure"}
    r = post(valid_body(origin={"lat": 95, "lon": 0}))
    assert r.status_code == 400 and "origin" in r.json()["fields"]
    r = post(valid_body(departure=(datetime.now(UTC) + timedelta(days=20)).isoformat()))
    assert r.status_code == 400 and "departure" in r.json()["fields"]


@override_settings(ALLOWED_HOSTS=["testserver"])
def test_a_valid_request_returns_the_plan(monkeypatch):
    monkeypatch.setattr(service, "make_provider", lambda: FakeProvider([route("Route A", 0, 100)]))
    monkeypatch.setattr(service, "make_forecasts", lambda: FakeForecasts(calm))
    r = post(valid_body())
    assert r.status_code == 200
    data = r.json()
    assert data["recommended"] == "Route A"
    assert data["routes"][0]["geometry"][0] == [-90.0, 40.0]


@override_settings(ALLOWED_HOSTS=["testserver"])
def test_service_failures_are_a_502_with_a_readable_message(monkeypatch):
    class Broken:
        name = "broken"

        def routes(self, *args, **kwargs):
            raise RoutingError("No truck route was found between these places.")

    monkeypatch.setattr(service, "make_provider", lambda: Broken())
    r = post(valid_body())
    assert r.status_code == 502 and r.json()["error"] == "No truck route was found between these places."

    def weather_down(lat, lon, moment):
        raise WeatherError("The weather service could not be reached (ConnectTimeout).")

    monkeypatch.setattr(service, "make_provider", lambda: FakeProvider([route("Route A", 0, 100)]))
    monkeypatch.setattr(service, "make_forecasts", lambda: FakeForecasts(weather_down))
    cache.clear()
    r = post(valid_body())
    assert r.status_code == 502 and "weather service" in r.json()["error"]


@override_settings(ALLOWED_HOSTS=["testserver"])
def test_geocode_needs_three_characters_and_accepts_coordinates():
    c = Client()
    assert c.get("/api/geocode", {"q": "ab"}).json() == {"results": []}
    coords = {"label": "41.8800, -87.6300", "lat": 41.88, "lon": -87.63}
    assert c.get("/api/geocode", {"q": "41.88, -87.63"}).json() == {"results": [coords]}
    assert c.get("/api/health").json() == {"ok": True}


class FakeGeocoder:
    def __init__(self, error=None):
        self.error = error

    def first(self, query):
        if self.error:
            raise self.error
        return Place(query, 40.0, -90.0) if query == "Here" else Place(query, 41.4, -90.0)


@override_settings(ALLOWED_HOSTS=["testserver"])
def test_an_unknown_place_is_a_400_but_a_failing_place_service_is_a_502(monkeypatch):
    from planner.geocode import GeocodeError, PlaceNotFound

    monkeypatch.setattr(service, "make_geocoder", lambda: FakeGeocoder(PlaceNotFound("No place matches 'Nowhere'.")))
    r = post(valid_body(origin="Nowhere"))
    assert r.status_code == 400 and r.json()["error"] == "No place matches 'Nowhere'."
    monkeypatch.setattr(service, "make_geocoder", lambda: FakeGeocoder(GeocodeError("Place search failed (HTTP 503).")))
    r = post(valid_body(origin="Nowhere"))
    assert r.status_code == 502


@override_settings(ALLOWED_HOSTS=["testserver"])
def test_typed_places_are_looked_up(monkeypatch):
    monkeypatch.setattr(service, "make_geocoder", lambda: FakeGeocoder())
    monkeypatch.setattr(service, "make_provider", lambda: FakeProvider([route("Route A", 0, 100)]))
    monkeypatch.setattr(service, "make_forecasts", lambda: FakeForecasts(calm))
    r = post(valid_body(origin="Here", destination="There"))
    assert r.status_code == 200
    assert (r.json()["origin"]["label"], r.json()["destination"]["label"]) == ("Here", "There")


@override_settings(ALLOWED_HOSTS=["testserver"])
def test_a_trip_ending_past_the_forecast_is_a_400_on_the_departure(monkeypatch):
    class TooFar(FakeForecasts):
        def load(self, locations, start, end):
            raise ForecastRangeError("Forecasts reach about two weeks ahead.")

    monkeypatch.setattr(service, "make_provider", lambda: FakeProvider([route("Route A", 0, 100)]))
    monkeypatch.setattr(service, "make_forecasts", lambda: TooFar(calm))
    r = post(valid_body())
    assert r.status_code == 400 and "departure" in r.json()["fields"]


def test_routes_are_cached_for_the_exact_load_only():
    provider = FakeProvider([route("Route A", 0, 100)])
    for load in (44_600, 45_400, 44_600):  # either side of 80,000 lb gross with a 35,000 lb tractor-trailer
        service.plan_trip(trip(load=load), provider=provider, forecasts=FakeForecasts(calm))
    assert provider.calls == 2


def test_the_plan_reports_the_weather_grid():
    plan = service.plan_trip(trip(), provider=FakeProvider([route("Route A", 0, 100)]),
                             forecasts=FakeForecasts(calm))
    assert plan["weather_grid_deg"] == 0.1
