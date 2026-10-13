"""HERE Routing v8 (https://developer.here.com/documentation/routing-api/), planned as a second provider.

HERE's truck mode takes the vehicle's gross weight and returns up to six alternatives, with no distance
limit per request. Set ROUTING_PROVIDER=here and HERE_API_KEY to use it once it is implemented.
"""
from .base import RoutingError


class HereProvider:
    name = "here"

    def __init__(self, api_key: str, user_agent: str, timeout: float = 20.0):
        if not api_key:
            raise RoutingError("HERE_API_KEY is not set.")
        self.api_key, self.user_agent, self.timeout = api_key, user_agent, timeout

    def routes(self, origin, destination, load_lb, count=3):
        raise RoutingError("The HERE provider is not implemented yet; use ROUTING_PROVIDER=valhalla.")
