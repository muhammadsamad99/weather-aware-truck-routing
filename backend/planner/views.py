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

# What a person reads when an outside service fails, by service and kind of failure. The technical message
# (status codes, exception names, the service's own wording) goes to the log, not to the screen.
TRY_LATER = "Please try again in a few minutes."
FAILURE_MESSAGES = {
    ("place search", "unavailable"): "Place search isn't responding right now, so place names can't be looked up. "
                                     "Enter coordinates instead (latitude, longitude), for example 28.54, -81.38, "
                                     "or try again in a few minutes.",
    ("routing", "no_route"): "No truck route was found between these places. Check that both can be reached by road.",
    ("routing", "busy"): "The routing service is busy right now. Please try again in a minute.",
    ("routing", "unavailable"): f"The routing service isn't responding right now. {TRY_LATER}",
    ("routing", "bad_answer"): f"The routing service sent an answer the app couldn't read. {TRY_LATER}",
    ("weather", "busy"): "The weather service is busy right now. Please try again in a minute.",
    ("weather", "daily_limit"): "Forecasts can't be loaded right now because the free weather service's daily "
                                "limit has been reached. The limit resets each day, so please try again later.",
    ("weather", "unavailable"): f"The weather service isn't responding right now. {TRY_LATER}",
    ("weather", "bad_answer"): f"The weather service sent an answer the app couldn't read. {TRY_LATER}",
    ("weather", "missing"): "The forecast is incomplete for part of this trip, so it can't be rated safely. "
                            "Please try again later, or choose another departure time.",
    ("weather", "backup_range"): "The main weather service isn't answering, and the backup forecasts only about the "
                                 "next 2½ days hour by hour, which this trip runs past. Choose an earlier "
                                 "departure, or try again later.",
}


def failure_message(err: Exception) -> str:
    """The plain-language message for a failed outside service."""
    service = ("place search" if isinstance(err, GeocodeError) else
               "routing" if isinstance(err, RoutingError) else "weather")
    kind = getattr(err, "kind", "unavailable")
    return FAILURE_MESSAGES.get((service, kind)) or FAILURE_MESSAGES[(service, "unavailable")]


@api_view(["GET"])
def health(request):
    return Response({"ok": True})


@api_view(["GET"])
def geocode(request):
    query = request.query_params.get("q", "")
    if len(query.strip()) < 3:
        return Response({"results": []})
    try:
        places = service.make_suggest_geocoder().search(query, limit=5)
    except GeocodeError as err:
        log.warning("place search failed: %s", err)
        return Response({"error": failure_message(err)}, status=502)
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
        log.warning("plan failed (%s): %s", getattr(err, "kind", "unavailable"), err)
        return Response({"error": failure_message(err)}, status=502)


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
