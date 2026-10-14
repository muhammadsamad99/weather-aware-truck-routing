import pytest
from django.core.cache import cache

from planner.geocode import GeocodeError, Geocoder, PlaceNotFound
from planner.tests.fakes import FakeResponse


def feature(name, osm_key, osm_value, lon, lat, state="Missouri"):
    return {"type": "Feature", "geometry": {"type": "Point", "coordinates": [lon, lat]},
            "properties": {"name": name, "osm_key": osm_key, "osm_value": osm_value, "state": state,
                           "countrycode": "US"}}


# Photon's own order for "St. Louis, MO"
ST_LOUIS = [
    feature("Washington University in St. Louis", "amenity", "university", -90.30, 38.65),
    feature("Saint Louis", "place", "city", -90.20, 38.63),
    feature("Saint Louis County", "boundary", "administrative", -90.44, 38.64),
]


class FakeSession:
    def __init__(self, features):
        self.features, self.headers, self.calls = features, {}, []

    def get(self, url, params, timeout, stream=False):
        self.calls.append(params)
        return FakeResponse(200, {"features": self.features[:params["limit"]]})


@pytest.fixture(autouse=True)
def clear_cache():
    cache.clear()


def geocoder(features):
    return Geocoder("https://photon.example/api/", "test-agent", session=FakeSession(features))


def test_a_town_ranks_above_a_landmark_named_after_it():
    g = geocoder(ST_LOUIS)
    assert [p.label for p in g.search("St. Louis, MO")][:2] == ["Saint Louis, Missouri, US",
                                                               "Saint Louis County, Missouri, US"]
    assert g.first("St. Louis, MO").label == "Saint Louis, Missouri, US"


def test_an_address_keeps_photons_order():
    g = geocoder(ST_LOUIS)
    assert g.first("1 Brookings Dr, St. Louis").label.startswith("Washington University")


def test_typed_coordinates_need_no_lookup():
    g = geocoder([])
    assert g.first("38.63, -90.2").lat == 38.63
    assert g.session.calls == []


def test_no_match_is_an_error():
    with pytest.raises(PlaceNotFound, match="No place matches"):
        geocoder([]).first("zzqqxxv")


def test_results_are_cached():
    g = geocoder(ST_LOUIS)
    g.search("St. Louis, MO")
    g.first("st. louis, mo")
    assert len(g.session.calls) == 1


class AnswerSession(FakeSession):
    def __init__(self, status, data):
        super().__init__([])
        self.status, self.data = status, data

    def get(self, url, params, timeout, stream=False):
        self.calls.append(params)
        return FakeResponse(self.status, self.data)


def test_a_failing_place_service_is_not_reported_as_no_match():
    for status, data in ((503, {"message": "down"}), (200, ["not", "an", "object"]), (200, None)):
        g = Geocoder("https://photon.example/api/", "test-agent", session=AnswerSession(status, data))
        with pytest.raises(GeocodeError) as caught:
            g.first("Boise")
        assert not isinstance(caught.value, PlaceNotFound)


def test_suggestions_get_a_shorter_budget_than_plans():
    # The autocomplete gives up fast when Photon stalls; the plan-time lookup stays patient.
    from planner import service

    quick, patient = service.make_suggest_geocoder(), service.make_geocoder()
    assert (quick.timeout, quick.deadline_s) == (service.SUGGEST_TIMEOUT_SECONDS, service.SUGGEST_DEADLINE_SECONDS)
    assert quick.timeout < patient.timeout
    assert quick.deadline_s < patient.deadline_s


def test_search_reads_the_body_under_its_own_deadline(monkeypatch):
    seen = {}

    def fake_read_json(resp, deadline_s=None, **kwargs):
        seen["deadline_s"] = deadline_s
        return {"features": []}

    monkeypatch.setattr("planner.geocode.read_json", fake_read_json)
    g = Geocoder("https://photon.example/api/", "test-agent", timeout=2.5,
                 session=FakeSession(ST_LOUIS), deadline_s=4.0)
    g.search("Denver")
    assert seen["deadline_s"] == 4.0
