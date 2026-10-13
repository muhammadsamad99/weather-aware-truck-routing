import pytest
from django.core.cache import cache

from planner.geocode import GeocodeError, Geocoder


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


class FakeResponse:
    def __init__(self, data):
        self.data = data

    def raise_for_status(self):
        pass

    def json(self):
        return self.data


class FakeSession:
    def __init__(self, features):
        self.features, self.headers, self.calls = features, {}, []

    def get(self, url, params, timeout):
        self.calls.append(params)
        return FakeResponse({"features": self.features[:params["limit"]]})


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
    with pytest.raises(GeocodeError, match="No place matches"):
        geocoder([]).first("zzqqxxv")


def test_results_are_cached():
    g = geocoder(ST_LOUIS)
    g.search("St. Louis, MO")
    g.first("st. louis, mo")
    assert len(g.session.calls) == 1
