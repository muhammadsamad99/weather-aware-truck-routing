"""What every routing provider returns, so the rest of the planner never depends on one API."""
from dataclasses import dataclass
from typing import Protocol


class RoutingError(Exception):
    """The provider could not route the trip (bad input, no road connection, or the service failed)."""


@dataclass(frozen=True)
class RouteOption:
    """One candidate route.

    points: the route geometry as (lat, lon), in driving order.
    miles: cumulative distance in miles at each point (miles[0] == 0).
    seconds: cumulative driving time in seconds at each point, from the provider's own timing, so slow
        stretches (cities, grades) take the time they really take rather than an average speed.
    """

    name: str
    points: tuple[tuple[float, float], ...]
    miles: tuple[float, ...]
    seconds: tuple[float, ...]
    provider: str

    @property
    def total_miles(self) -> float:
        return self.miles[-1]

    @property
    def total_seconds(self) -> float:
        return self.seconds[-1]


class RoutingProvider(Protocol):
    name: str

    def routes(self, origin: tuple[float, float], destination: tuple[float, float], load_lb: float,
               count: int = 3) -> list[RouteOption]:
        """Up to `count` distinct truck routes from origin to destination, best first."""
        ...
