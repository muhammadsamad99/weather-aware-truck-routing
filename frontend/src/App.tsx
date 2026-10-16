import Alert from '@mui/material/Alert'
import Box from '@mui/material/Box'
import CircularProgress from '@mui/material/CircularProgress'
import Link from '@mui/material/Link'
import Stack from '@mui/material/Stack'
import Typography from '@mui/material/Typography'
import { useCallback, useEffect, useRef, useState } from 'react'
import { ApiError, planTrip } from './api'
import CheckpointTable from './components/CheckpointTable'
import Legend from './components/Legend'
import MapPane from './components/MapPane'
import type { Focus } from './components/MapView'
import Recommendation from './components/Recommendation'
import RouteCards from './components/RouteCards'
import TripForm, { MAX_LOAD_LB } from './components/TripForm'
import { nextHourLocal } from './format'
import type { Plan, TripForm as TripFormValues } from './types'

const EXAMPLE: Pick<TripFormValues, 'origin' | 'destination'> = {
  origin: { text: 'Chicago, IL', place: null },
  destination: { text: 'Denver, CO', place: null },
}

const CREDITS: [string, string][] = [
  ['Valhalla', 'https://valhalla.github.io/valhalla/'],
  ['FOSSGIS', 'https://www.fossgis.de/'],
  ['OSRM', 'https://project-osrm.org/'],
  ['OpenStreetMap contributors', 'https://www.openstreetmap.org/copyright'],
  ['fix the map', 'https://www.openstreetmap.org/fixthemap'],
  ['Open-Meteo.com', 'https://open-meteo.com/'],
  ['MET Norway', 'https://api.met.no/'],
  ['CC BY 4.0', 'https://creativecommons.org/licenses/by/4.0/'],
  ['Photon', 'https://photon.komoot.io/'],
  ['Nominatim', 'https://nominatim.org/'],
  ['OpenFreeMap', 'https://openfreemap.org/'],
]
// Read by screen readers, not shown.
const SCREEN_READER_ONLY = {
  position: 'absolute',
  width: '1px',
  height: '1px',
  overflow: 'hidden',
  clip: 'rect(0 0 0 0)',
  whiteSpace: 'nowrap',
} as const

const credit = (name: string) => {
  const url = CREDITS.find(([n]) => n === name)![1]
  return (
    <Link href={url} color="inherit" underline="always">
      {name}
    </Link>
  )
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
    <Box
      sx={(theme) => ({
        display: 'grid',
        // minmax(0, …): a column must not grow to fit its widest content (the checkpoint table scrolls instead)
        gridTemplateColumns: 'minmax(0, 1fr)',
        gridTemplateRows: 'auto 70vh auto',
        gridTemplateAreas: '"panel" "map" "footer"',
        [theme.breakpoints.up('md')]: {
          gridTemplateColumns: 'minmax(360px, 420px) minmax(0, 1fr)',
          gridTemplateRows: '1fr auto',
          gridTemplateAreas: '"panel map" "footer map"',
          height: '100vh',
          '@supports (height: 100dvh)': { height: '100dvh' },
        },
      })}
    >
      <Box
        component="main"
        sx={{
          gridArea: 'panel',
          minWidth: 0,
          overflowY: { md: 'auto' },
          scrollbarGutter: { md: 'stable' },
          borderRight: { md: 1 },
          borderColor: { md: 'divider' },
          px: 2.5,
          pt: 2.5,
          pb: 2,
        }}
      >
        <Stack spacing={2}>
          <header>
            <Typography variant="h1">Weather-Aware Truck Routing</Typography>
            <Typography variant="body2" color="text.secondary" sx={{ mt: 0.5 }}>
              Three routes, the forecast at each checkpoint when the truck gets there, and the safest way to go.
            </Typography>
          </header>

          <TripForm values={form} onChange={setForm} onSubmit={submit} busy={busy} fieldErrors={fieldErrors} />
          {!plan && !busy && (
            <Link
              component="button"
              type="button"
              variant="body2"
              onClick={() => setForm((f) => ({ ...f, ...EXAMPLE }))}
              sx={{ alignSelf: 'flex-start' }}
            >
              Try an example: Chicago, IL → Denver, CO
            </Link>
          )}

          {/* One status region, always there, so screen readers announce the start and the result once each;
              the running seconds sit outside it so they aren't read out every second. */}
          <Box sx={busy ? undefined : SCREEN_READER_ONLY}>
            <Stack direction="row" spacing={1} sx={{ alignItems: 'center' }}>
              {busy && <CircularProgress size={16} aria-hidden="true" />}
              <Typography role="status" variant="body2" color="text.secondary">
                {busy ? 'Routing and checking the forecast…' : plan ? `Planned: ${plan.recommended} is recommended.` : ''}
              </Typography>
              {busy && (
                <Typography variant="body2" color="text.secondary" aria-hidden="true">
                  {elapsed} s
                </Typography>
              )}
            </Stack>
            {busy && elapsed >= 15 && (
              <Typography variant="caption" component="p" color="text.secondary" sx={{ mt: 0.5 }}>
                Long trips take longer: the free routing and weather services are asked at a limited pace.
              </Typography>
            )}
          </Box>
          {error && <Alert severity="error">{error}</Alert>}

          {plan && (
            <Stack component="section" spacing={1.5} aria-label="Results">
              <Recommendation plan={plan} />
              <RouteCards routes={plan.routes} selected={selected} onSelect={setSelected} />
              {selectedRoute && (
                <CheckpointTable
                  route={selectedRoute}
                  intervalMi={plan.interval_mi}
                  onFocus={mapWorks ? onFocus : undefined}
                />
              )}
            </Stack>
          )}

          <Legend />
        </Stack>
      </Box>

      <Box
        component="section"
        aria-label="Map"
        sx={{ gridArea: 'map', position: 'relative', minHeight: 0 }}
        className="map-area"
      >
        <MapPane
          plan={plan}
          selected={selected}
          focus={focus}
          onSelectRoute={setSelected}
          mapWorks={mapWorks}
          onMapFailed={mapFailed}
        />
      </Box>

      <Box
        component="footer"
        sx={{ gridArea: 'footer', px: 2.5, py: 1.5, borderRight: { md: 1 }, borderTop: 1, borderColor: 'divider' }}
      >
        <Typography variant="caption" component="p" color="text.secondary">
          Routes: {credit('Valhalla')} on the {credit('FOSSGIS')} server (backup: {credit('OSRM')}) · Map data © {credit('OpenStreetMap contributors')}{' '}
          ({credit('fix the map')}) · Weather data by {credit('Open-Meteo.com')} (backup:{' '}
          {credit('MET Norway')}, {credit('CC BY 4.0')}) · Places: {credit('Photon')} (backups:{' '}
          {credit('Nominatim')}, {credit('Open-Meteo.com')}) · Map:{' '}
          {credit('OpenFreeMap')}
        </Typography>
      </Box>
    </Box>
  )
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
