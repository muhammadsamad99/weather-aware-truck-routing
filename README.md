# Weather-Aware Truck Routing

[![CI](https://github.com/muhammadsamad99/weather-aware-truck-routing/actions/workflows/ci.yml/badge.svg)](https://github.com/muhammadsamad99/weather-aware-truck-routing/actions/workflows/ci.yml)

Helps a truck driver choose the safest route for a trip. Enter the origin, destination, departure time and
load. The app finds three routes and checks the forecast at checkpoints every 10, 25 or 50 miles, for the
hour the truck will be at each one. It rates each checkpoint on the risk table, adjusted for the load, and
recommends a route with the reason. A heatmap with a 0–48 hour slider shows the weather risk along the
trip corridor.

React + TypeScript + Material UI + MapLibre GL on the front end, Django + Django REST Framework behind it.

![Chicago to Denver: three routes tagged with distance and driving time, the recommended route with what its extra time buys, checkpoints coloured by risk, and the corridor heatmap 24 hours after departure](docs/screenshot.jpg)

## Using it

1. **Enter the trip:**
   - Origin and destination. Pick a suggestion, or type a place or `lat, lon`.
   - Departure (your local time), load in pounds, and how often to check the weather.
2. **Read the result.** The panel names the recommended route and why it was chosen. Each route has a card
   with:
   - distance, driving time and arrival;
   - miles at each risk level, as a bar;
   - No Travel, Severe and High miles;
   - the average risk.

   When the recommended route isn't the fastest, the panel also says how much longer it takes and what that
   buys.

   Click a card, or a route on the map, to select it. The table below the cards lists the selected route's
   checkpoints with their arrival times, forecast and risk. Click a row (or press Enter on it) to find that
   checkpoint on the map.
3. **On the map:**
   - Each route has a tag with its distance and driving time.
   - Every checkpoint is coloured by its risk; hover one for its arrival time, click it for the details.
   - The slider moves the heatmap through the next 48 hours from departure; ▶ plays it.
   - The dark square marks where the truck is, on the selected route, at the slider's hour.

## How the brief is covered

| The brief asks for | Where it is | Checked by |
|---|---|---|
| Origin, destination, departure date/time, load | `TripForm`, `PlaceInput` → `POST /api/plan`, validated in `planner/serializers.py` | `test_service_and_api.py`, `App.test.tsx` |
| 3 route options from a routing API | `planner/providers/valhalla.py` | `test_valhalla.py` |
| Weather every 10/25/50 mi at the truck's ETA | `planner/checkpoints.py`, `planner/weather.py` | `test_checkpoints.py`, `test_weather.py` |
| The risk table and load rules | `planner/risk.py` | `test_risk.py`, `test_legend.py` |
| A recommendation that balances risk and time, in the brief's order | `planner/recommend.py` (the order, the reason, the trade-off line) | `test_recommend.py`, `test_service_and_api.py` |
| Routes, checkpoints, risk levels, ETAs and route summaries on a map | `MapView.tsx` (route lines and tags, coloured checkpoints, hover and popups), `RouteCards.tsx` | `App.test.tsx` for the panel; the drawn map was checked in headless Chrome during development (not in CI) |
| A heatmap along the corridor with a 0–48 h slider | `planner/heatmap.py`, `service._heatmap`, `HeatmapControl.tsx` | `test_heatmap.py`, `test_service_and_api.py` |

## How a plan is made

| Step | What happens | Code |
|---|---|---|
| Places | Typed places are looked up with [Photon](https://photon.komoot.io) (OpenStreetMap). For a name without digits, towns and cities rank above landmarks: Photon puts a university first for "St. Louis, MO". | `planner/geocode.py` |
| Routes | See [Routes](#routes) below. | `planner/providers/valhalla.py` |
| Checkpoints | At 0, N, 2N, … miles along each route, and at the destination. Each checkpoint's ETA is the departure plus Valhalla's driving time to that point. | `planner/checkpoints.py` |
| Weather at the ETA | See [Weather at each checkpoint's ETA](#weather-at-each-checkpoints-eta) below. | `planner/weather.py` |
| Risk | The worst of the wind (after the load rules), rain and snow levels. See [Risk rules and edge cases](#risk-rules-and-edge-cases). | `planner/risk.py` |
| Route totals | The stretch between two checkpoints takes the **worse** of their two levels, so no stretch is rated safer than either end of it. Average risk is the mile-weighted mean of the stretch levels, from 0 (Low) to 4 (No Travel). | `planner/recommend.py` |
| Recommendation | See [The recommendation](#the-recommendation). | `planner/recommend.py` |
| Heatmap | See [The heatmap](#the-heatmap). | `planner/heatmap.py`, `planner/service.py` |

### Routes

- Valhalla's `truck` costing is used, with the gross weight set to an empty tractor-trailer (35,000 lb)
  plus the load.
- Valhalla returns the best route and its own alternates. When there are fewer than three, more are made
  by routing through a waypoint pushed to one side of the best route's midpoint.
- A candidate is kept only if:
  - under 80% of it is the same road as a route already kept;
  - it takes at most 1.6× the best route's time;
  - it doesn't run back over itself for more than 3 miles.
- A waypoint can land on a side road, so the route would drive up to it and back. Where that happens the
  legs are joined where they part.
- The routes are cached for 6 hours per trip and exact load, because the truck's weight decides which roads
  and bridges it may use.

### Weather at each checkpoint's ETA

The forecast is [Open-Meteo](https://open-meteo.com) hourly data:

- **Wind:** speed at 10 m, in mph.
- **Rain:** `rain` + `showers` (both fall on the road), in inches per hour.
- **Snow:** snowfall, in inches per hour.

Rain and snow at a timestamp are the totals for the hour before it. So a truck at a checkpoint at 10:20
gets rain and snow from the 10:00–11:00 hour, and wind interpolated between the 10:00 and 11:00 readings.

A value the forecast leaves out is never read as calm weather: a checkpoint whose hour has no value can't
be rated, so the plan stops with a message, and a heatmap point without a value is left off the map.

Each checkpoint takes the forecast of the 0.1° cell (about 7 mi) it falls in. A plan asks for at most 450
cells, to stay within the free service's limits (see [Services](#services-and-their-limits)). A long trip
checked every 10 mi needs more, so its grid widens until the plan fits: Los Angeles to New York every 10 mi
is read on a 0.4° grid. The panel says so whenever the grid is wider than 0.1°.

### The recommendation

1. Any route with a No Travel stretch ranks behind every route without one.
2. Then routes are ranked by the brief's order:
   1. fewest Severe miles;
   2. fewest High miles;
   3. lowest average risk;
   4. shortest travel time.

The reason names the first criterion that separates the winner from the runner-up.

### The heatmap

- **The grid:** points every 0.2° within 40 mi of any route. The spacing widens until there are at most 180
  points, so a long trip needs no more forecast data than a short one.
- **The frames:** the risk at every point for each hour from departure to departure + 48 h. The plan
  includes all 49 frames, so the slider needs no network requests.
- **On the map:** each point is drawn as a soft disc in its level's colour, about one grid cell wide.

## Risk rules and edge cases

| Condition | Low | Moderate | High | Severe | No Travel |
|---|---|---|---|---|---|
| Wind | < 25 mph | 25 to < 35 | 35 to < 45 | 45 to < 55 | ≥ 55 mph |
| Rain | < 0.10 in/hr | 0.10 to < 0.25 | 0.25 to < 0.50 | 0.50 to 1.00 | > 1.00 |
| Snow | < 0.5 in/hr | 0.5 to < 1.0 | 1.0 to < 2.0 | 2.0 to 3.0 | > 3.0 |

Load rules, applied to wind:

| Wind | Load | Level |
|---|---|---|
| 45–54 mph | over 30,000 lb | No Travel |
| 35–44 mph | over 40,000 lb | Severe |
| 55 mph or more | any | No Travel |

Decisions where the brief leaves room:

- **Shared edges.** The brief's table repeats some values (rain 0.25 and 0.50, snow 1.0 and 2.0). A shared
  value belongs to the **higher** band, and each band runs from its lower edge up to, but not including,
  the next one.
- **No Travel thresholds.** For rain and snow these are strict, as the table writes them (> 1.00, > 3.0),
  so exactly 1.00 in/hr of rain is Severe. Wind No Travel is inclusive (≥ 55 mph).
- **Values between the table's whole numbers.** The wind bands are whole numbers in the brief (25–34,
  35–44). A forecast of 34.6 mph is Moderate: it is below 35.
- **Load reasons.** When the load raises a checkpoint's level, the checkpoint's reasons say so ("load
  42,000 lb").
- **No Travel ranks first.** No Travel is worse than Severe, and the brief treats it as "do not drive". So a
  route that crosses any of it is never recommended over one that does not, even with fewer Severe miles.
- **The order is applied as written, and its cost in time is shown.** The brief asks for a balance of risk
  and time, then gives the order: Severe miles, High miles, average risk, travel time. The app applies that
  order as written rather than inventing its own weighting. Two things keep the balance visible and bounded:
  - Routes that take more than 1.6× the time of Valhalla's best route are never offered.
  - When the recommended route isn't the fastest, the panel says what the extra time buys, for example
    "4 h 02 min longer than Route A, the fastest route, for lower average risk (0.08 vs 0.17)". The driver
    can then pick the faster card.
  - Risk figures are compared at the precision the panel shows them (whole miles, average risk to two
    decimals), so a difference too small to see never decides the ranking, and a reason never reads
    "0.16 vs 0.16".
- **Truck weight.** Valhalla is given the gross weight: 35,000 lb tare plus the load.
- **Time zones.** Times are sent in UTC and shown in the browser's time zone.
- **Departure window.** A departure from an hour ago up to 14 days ahead is accepted, which is what the
  forecast covers.

## Services and their limits

Every service is free and needs no API key.

| Service | Used for | Limits |
|---|---|---|
| [Valhalla](https://valhalla.github.io/valhalla/) public server, run by [FOSSGIS](https://www.fossgis.de/) | Truck routes | The [usage policy](https://routing.openstreetmap.de/about.html) allows at most one request per second, with attribution and a "fix the map" link (both in the panel footer). The whole service spaces its requests a second apart, and routes are cached. One request may not span more than 1,500 km, so longer trips are routed in legs and joined. The server is sometimes busy, so a busy or "overloaded" answer is tried twice more, 1.5 s and then 3 s later. |
| [Open-Meteo](https://open-meteo.com) | Hourly forecasts | Free for non-commercial use: 600 calls a minute and 10,000 a day. The terms don't say how a request for many locations counts, but each location seems to count as a call: one coast-to-coast plan of about 1,000 locations hit the per-minute limit on its own. So a plan asks for at most 450 (see above), and the whole service asks for at most 560 in any minute: a plan that would go over waits until the minute frees up (at most a minute). Open-Meteo's own limit message can still appear, for example if the host shares its outgoing address with other apps that use Open-Meteo. A request now and then gets no answer for 20 s although the same request a moment later takes a second or two, so a request that gets no answer, or a 502-504, is asked once more a second later (and counts against the minute again). Forecasts are cached for an hour per cell. |
| [Photon](https://photon.komoot.io) | Place search | Fair use. Results are cached for a day. |
| [OpenFreeMap](https://openfreemap.org) | Base map | None stated. If the base map style cannot load, the routes and weather still draw on a plain background. |

Each service's URL can be changed by an environment variable (see `.env.example`), for example to point at
a self-hosted Valhalla.

**Adding a routing provider.** Routing sits behind a small interface (`planner/providers/base.py`): a provider
has a `name` (used in the route cache key and the plan) and a `routes(origin, destination, load_lb, count=3)`
method that returns up to `count` distinct `RouteOption`s, best first, each with its points and cumulative
miles and seconds. Implement one next to `valhalla.py` and select it in `service.make_provider` with
`ROUTING_PROVIDER`; checkpoints, weather, risk and ranking work on `RouteOption`s and don't change.

## Running it locally

You need Python 3.11 or newer and a current Node LTS. It is tested with Python 3.11.9 and Node 24.21.0, the
versions `render.yaml` and CI pin.

```bash
python3 -m venv .venv && source .venv/bin/activate
pip install -r backend/requirements-dev.txt
DJANGO_DEBUG=1 python backend/manage.py runserver      # the API, on :8000

cd frontend && npm ci && npm run dev                   # the app, on http://localhost:5173
```

The Vite dev server passes `/api` requests to Django.

To run it the way it runs in production, with one server for the app and the API:

```bash
DJANGO_SECRET_KEY=change-me ./build.sh
DJANGO_SECRET_KEY=change-me gunicorn --chdir backend config.wsgi:application --bind 127.0.0.1:8000
```

## Tests and checks

```bash
cd backend && pytest && ruff check .
cd frontend && npm run lint && npx tsc -b && npm test
```

CI runs all of these on every push to `main` and on every pull request (`.github/workflows/ci.yml`).

The backend tests (142) cover:

- **Risk table:** every edge and every load rule.
- **Ranking:** each step of the recommendation order, its reason messages and the trade-off line.
- **Checkpoints:** spacing and ETAs.
- **Polyline decoding and trip parsing:** against a recorded Valhalla response.
- **Route candidates:** alternates, detours, near-duplicates, spurs, and long trips split into legs.
- **Weather:** the forecast-hour rule, the unit checks, missing values, the location budget, the
  per-minute quota, and which failures are asked again.
- **Pacing:** requests to the routing server are spaced a second apart, across threads.
- **Corridor grid.**
- **Place ranking**, and telling "no such place" from a failing place service.
- **Reading the services' answers:** a server that sends its answer a byte at a time is given up at the
  deadline (tested against a real local socket), and answers in an unexpected shape are reported as errors.
- **The legend:** the map legend's thresholds are checked against the risk table the backend applies.
- **The API:** with routing, weather and places replaced by fakes. Any request a test makes to a host other
  than this machine fails the test.

The frontend tests (13, Vitest and Testing Library) cover:

- **The place boxes:** a search only from three letters and once per pause in typing, a picked place kept
  until typed over, and picked places sent as coordinates.
- **A failed re-plan:** keeps the last results on screen and says so.
- **The map's failure paths:** the app without WebGL (the form and every result still work, and the map area
  says why the map is missing), a map that breaks for another reason, and a lost graphics context.
- **Risk chips:** every label reads at 4.5:1 or better on its colour.
- **The truck's position** at an hour.

## Deploying

`render.yaml` is a [Render Blueprint](https://render.com/docs/infrastructure-as-code) for one web service:

- **Build:** `build.sh` installs the Python packages, builds the React app and collects static files.
- **Run:** gunicorn serves the API, and WhiteNoise serves the app.
- **Process:** one gunicorn worker with threads, so the in-memory route and forecast caches are shared.
- **Secret key:** generated by Render.

On Render's free plan the service sleeps after 15 minutes without traffic. The first request after that
takes about a minute.

## Security

- There are no accounts and nothing is stored, so there are no sessions or cookies to protect.
- Every input is validated on the server: the places, the departure window, the load and the interval.
- The app's page may load scripts only from its own site and map data only from OpenFreeMap (a
  Content-Security-Policy), and other sites can't frame it.
- Answers from the outside services are read within a time and size limit, so a slow or broken service
  can't hold the server.
- Dependencies were audited on 2026-10-14: `npm audit` reported no vulnerabilities, and `pip-audit` none in
  `backend/requirements*.txt`. CI doesn't run these audits, so re-run them before a release.

## Project layout

```
backend/
  config/                 Django settings and URLs (no database: nothing is stored)
  planner/
    providers/            routing: the provider interface and Valhalla
    risk.py               risk table and load rules
    checkpoints.py        checkpoints and ETAs
    weather.py            Open-Meteo forecasts at a place and time
    recommend.py          route risk totals, ranking and the reason
    heatmap.py            corridor grid for the heatmap
    http.py               reads the services' answers within a time and size limit
    service.py            puts a plan together
    views.py, serializers.py
    tests/
frontend/src/
  App.tsx                 form state and the page layout
  theme.ts                the Material UI theme; levels.ts holds the risk colours
  components/
    TripForm, PlaceInput  the trip form and the place search
    Recommendation, RouteCards, CheckpointTable, Legend
    MapPane, MapView      the map (MapLibre, loaded separately) and its heatmap state
    HeatmapControl        the 0-48 h slider
    MapFallback           what shows when the map can't be drawn
  api.ts, types.ts        the API and its response shapes
  geometry.ts             the truck's position at an hour, map bounds
render.yaml, build.sh     deployment
.github/workflows/ci.yml  tests, lint, type check and build on pushes to main and on pull requests
```

## Known limitations

- **ETAs assume continuous driving.** They come from Valhalla's truck travel times, with no traffic, fuel
  stops or hours-of-service breaks. On a trip longer than a driver's shift, the truck would really reach
  later checkpoints later than shown.
- **Forecasts are forecasts.** They are less certain further out. They are read on a 0.1° grid (about 7
  miles), and on a wider one for long trips checked often (see above).
- **Some trips have fewer than three routes.** Extra routes are made with waypoints. Where the roads allow
  only one or two sensible routes, the app shows what it found.
- **The heatmap and the checkpoints answer different questions.** The heatmap shows the whole corridor at
  one hour, from grid points 0.2° or more apart (about 9-14 miles across the lower 48 states; the slider
  shows the spacing), so a strong cell near the road can colour the map around a checkpoint that is itself
  calmer. The checkpoints show the weather at the hour the truck reaches each one, where it is.
- **The map needs WebGL.** A browser without it (often on a computer or VM without a graphics card, or with
  hardware acceleration off) gets a note in the map area instead of the map; the form, the recommendation,
  the route cards and the checkpoint table still work.
- **The free services have rate limits** (see above), so the first plan for a trip is slow. In testing,
  Chicago to Denver took 8-10 seconds, and Los Angeles to New York took about a minute when it ran right
  after another plan and had to wait for the weather service's per-minute limit. A repeat plan for the same
  trip reuses the cached routes and forecasts.
