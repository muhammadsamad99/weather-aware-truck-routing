import logging
from concurrent.futures import ThreadPoolExecutor

from rest_framework.decorators import api_view
from rest_framework.response import Response
from rest_framework.views import exception_handler as drf_exception_handler

from . import service
from .geocode import GeocodeError, Place, PlaceNotFound
from .providers.base import RoutingError
from .serializers import PlanRequestSerializer
from .weather import ForecastRangeError, WeatherError

log = logging.getLogger(__name__)


@api_view(["GET"])
def health(request):
    return Response({"ok": True})


@api_view(["GET"])
def geocode(request):
    query = request.query_params.get("q", "")
    if len(query.strip()) < 3:
        return Response({"results": []})
    try:
        places = service.make_geocoder().search(query, limit=5)
    except GeocodeError as err:
        return Response({"error": str(err)}, status=502)
    return Response({"results": [p.as_dict() for p in places]})


@api_view(["POST"])
def plan(request):
    form = PlanRequestSerializer(data=request.data)
    if not form.is_valid():
        return Response({"error": "Please check the trip details.", "fields": form.errors}, status=400)
    data = form.validated_data
    try:
        geocoder = service.make_geocoder()
        with ThreadPoolExecutor(max_workers=2) as pool:  # two typed places are looked up at the same time
            origin, destination = pool.map(lambda value: _place(geocoder, value), (data["origin"], data["destination"]))
        trip = service.TripRequest(origin=origin, destination=destination, departure=data["departure"],
                                   load_lb=data["load_lb"], interval_mi=int(data["interval_mi"]))
        return Response(service.plan_trip(trip))
    except (PlaceNotFound, service.InvalidTrip) as err:
        return Response({"error": str(err)}, status=400)
    except ForecastRangeError as err:
        return Response({"error": str(err), "fields": {"departure": [str(err)]}}, status=400)
    except (GeocodeError, RoutingError, WeatherError) as err:
        log.warning("plan failed: %s", err)
        return Response({"error": str(err)}, status=502)


def _place(geocoder, value) -> Place:
    if isinstance(value, dict):
        return Place(label=value["label"], lat=value["lat"], lon=value["lon"])
    return geocoder.first(value)


def exception_handler(exc, context):
    """DRF's own errors (malformed JSON, a wrong method) in the API's error shape: {"error": "..."}."""
    response = drf_exception_handler(exc, context)
    if response is not None and isinstance(response.data, dict) and "detail" in response.data:
        response.data = {"error": str(response.data["detail"])}
    return response
