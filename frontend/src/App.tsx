import { useCallback, useEffect, useRef, useState } from 'react'
import { ApiError, planTrip } from './api'
import CheckpointTable from './components/CheckpointTable'
import HeatmapControl from './components/HeatmapControl'
import Legend from './components/Legend'
import { MapBoundary } from './components/MapFallback'
import MapView, { type Focus } from './components/MapView'
import RouteCards from './components/RouteCards'
import TripForm, { MAX_LOAD_LB } from './components/TripForm'
import { formatDateTime, formatLoad, nextHourLocal } from './format'
import type { Plan, TripForm as TripFormValues } from './types'

const EXAMPLE: Pick<TripFormValues, 'origin' | 'destination'> = {
  origin: { text: 'Chicago, IL', place: null },
  destination: { text: 'Denver, CO', place: null },
}

export default function App() {
  const [form, setForm] = useState<TripFormValues>(() => ({
    origin: { text: '', place: null },
    destination: { text: '', place: null },
    departure: nextHourLocal(),
    loadLb: '40000',
    intervalMi: 25,
  }))
  const [plan, setPlan] = useState<Plan | null>(null)
  const [selected, setSelected] = useState('')
  const [hour, setHour] = useState(0)
  const [showHeatmap, setShowHeatmap] = useState(true)
  const [playing, setPlaying] = useState(false)
  const [focus, setFocus] = useState<Focus | null>(null)
  const [mapWorks, setMapWorks] = useState(true)
  const mapFailed = useCallback(() => setMapWorks(false), [])
  const [busy, setBusy] = useState(false)
  const [elapsed, setElapsed] = useState(0)
  const [error, setError] = useState('')
  const [fieldErrors, setFieldErrors] = useState<Record<string, string>>({})
  const inFlight = useRef<AbortController | null>(null)

  useEffect(() => {
    if (!busy) return
    const started = Date.now()
    setElapsed(0)
    const timer = window.setInterval(() => setElapsed(Math.floor((Date.now() - started) / 1000)), 1000)
    return () => window.clearInterval(timer)
  }, [busy])

  const submit = async () => {
    const problems = validate(form)
    setFieldErrors(problems)
    setError('')
    if (Object.keys(problems).length) return

    inFlight.current?.abort()
    const controller = new AbortController()
    inFlight.current = controller
    setBusy(true)
    try {
      const result = await planTrip(
        {
          origin: form.origin.place ?? form.origin.text.trim(),
          destination: form.destination.place ?? form.destination.text.trim(),
          departure: new Date(form.departure).toISOString(),
          load_lb: Number(form.loadLb),
          interval_mi: form.intervalMi,
        },
        controller.signal,
      )
      setPlan(result)
      setSelected(result.recommended)
      setHour(0)
      setPlaying(false)
      setFocus(null)
    } catch (err) {
      if ((err as Error).name === 'AbortError') return
      const e = err as ApiError
      setError(plan ? `${e.message} The map still shows the last plan.` : e.message)
      setFieldErrors(Object.fromEntries(Object.entries(e.fields ?? {}).map(([k, v]) => [k, v.join(' ')])))
    } finally {
      if (inFlight.current === controller) {
        inFlight.current = null
        setBusy(false)
      }
    }
  }

  const selectedRoute = plan?.routes.find((r) => r.name === selected)
  const onFocus = useCallback((index: number) => setFocus({ route: selected, index, nonce: Date.now() }), [selected])

  return (
    <div className="app">
      <aside className="panel">
        <header>
          <h1>Weather-Aware Truck Routing</h1>
          <p>Three routes, the forecast at each checkpoint when the truck gets there, and the safest way to go.</p>
        </header>

        <TripForm values={form} onChange={setForm} onSubmit={submit} busy={busy} fieldErrors={fieldErrors} />
        {!plan && !busy && (
          <button type="button" className="link" onClick={() => setForm({ ...form, ...EXAMPLE })}>
            Try an example: Chicago, IL → Denver, CO
          </button>
        )}

        {busy && (
          <div className="status" role="status">
            <span className="spinner" aria-hidden="true" /> Routing and checking the forecast… {elapsed} s
            {elapsed >= 15 && (
              <span className="hint">
                Long trips take longer: the free routing and weather services are asked at a limited pace.
              </span>
            )}
          </div>
        )}
        {error && (
          <div className="error" role="alert">
            {error}
          </div>
        )}

        {plan && (
          <section className="results" aria-label="Results">
            <div className="recommendation">
              <div className="rec-title">
                Recommended: <strong>{plan.recommended}</strong>
              </div>
              <p>{plan.reason}</p>
              {plan.tradeoff && <p>{plan.tradeoff}</p>}
              <p className="trip-summary">
                {plan.origin.label} → {plan.destination.label}
                <br />
                Leaves {formatDateTime(plan.departure)} · {formatLoad(plan.load_lb)} · checked every {plan.interval_mi} mi
              </p>
              {plan.weather_grid_deg > 0.1 && (
                <p className="trip-summary">
                  A long trip: the forecast is read on a {plan.weather_grid_deg}° grid (about{' '}
                  {Math.round(plan.weather_grid_deg * 69)} mi) to stay within the weather service's limits.
                </p>
              )}
            </div>
            <RouteCards routes={plan.routes} selected={selected} onSelect={setSelected} />
            {selectedRoute && (
              <CheckpointTable
                route={selectedRoute}
                intervalMi={plan.interval_mi}
                onFocus={mapWorks ? onFocus : undefined}
              />
            )}
          </section>
        )}

        <Legend />
        <footer>
          Routes: <a href="https://valhalla.github.io/valhalla/">Valhalla</a> on the{' '}
          <a href="https://www.fossgis.de/">FOSSGIS</a> server · Map data ©{' '}
          <a href="https://www.openstreetmap.org/copyright">OpenStreetMap contributors</a> (
          <a href="https://www.openstreetmap.org/fixthemap">fix the map</a>) · Weather data by{' '}
          <a href="https://open-meteo.com/">Open-Meteo.com</a> · Places:{' '}
          <a href="https://photon.komoot.io/">Photon</a> · Map: <a href="https://openfreemap.org/">OpenFreeMap</a>
        </footer>
      </aside>

      <main className="map-area">
        <MapBoundary onError={mapFailed}>
          <MapView
            plan={plan}
            selected={selected}
            hour={hour}
            showHeatmap={showHeatmap}
            focus={focus}
            onSelectRoute={setSelected}
            onUnavailable={mapFailed}
          />
        </MapBoundary>
        {plan && mapWorks && (
          <HeatmapControl
            start={plan.heatmap.start}
            hours={plan.heatmap.hours}
            spacingMi={gridSpacingMi(plan)}
            hour={hour}
            onHour={setHour}
            visible={showHeatmap}
            onVisible={setShowHeatmap}
            playing={playing}
            onPlaying={setPlaying}
          />
        )}
      </main>
    </div>
  )
}

/** The heatmap grid's spacing in miles: [east-west, north-south] (a degree of longitude shrinks with latitude). */
function gridSpacingMi(plan: Plan): [number, number] {
  const lats = plan.heatmap.points.map((p) => p[1])
  const midLat = lats.length ? (Math.min(...lats) + Math.max(...lats)) / 2 : 39
  const northSouth = plan.heatmap.step_deg * 69
  return [Math.round(northSouth * Math.cos((midLat * Math.PI) / 180)), Math.round(northSouth)]
}

function validate(form: TripFormValues): Record<string, string> {
  const problems: Record<string, string> = {}
  if (!form.origin.text.trim()) problems.origin = 'Enter where the trip starts.'
  if (!form.destination.text.trim()) problems.destination = 'Enter where the trip ends.'
  if (!form.departure || Number.isNaN(new Date(form.departure).getTime())) problems.departure = 'Choose a departure time.'
  const load = Number(form.loadLb)
  if (!form.loadLb.trim() || !Number.isFinite(load) || load < 1 || load > MAX_LOAD_LB) {
    problems.load_lb = `Enter a load from 1 to ${MAX_LOAD_LB.toLocaleString()} lb.`
  }
  return problems
}
