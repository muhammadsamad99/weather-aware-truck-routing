import { cleanup, fireEvent, render, screen, waitFor } from '@testing-library/react'
import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest'
import App from './App'
import { MapBoundary } from './components/MapFallback'
import MapView from './components/MapView'
import type { Plan } from './types'

// MapLibre needs WebGL, which jsdom doesn't have; the fake map can be told to fail the way MapLibre does.
const mapStart = vi.hoisted(() => ({ error: null as Error | null }))

vi.mock('maplibre-gl', () => {
  class FakeMap {
    constructor() {
      if (mapStart.error) throw mapStart.error
    }
    addControl() {}
    on() {}
    remove() {}
    fitBounds() {}
    getContainer() {
      return { clientWidth: 1000 }
    }
  }
  class FakeLayerThing {
    setLngLat() {
      return this
    }
    addTo() {
      return this
    }
    remove() {}
  }
  return {
    Map: FakeMap,
    NavigationControl: FakeLayerThing,
    ScaleControl: FakeLayerThing,
    Popup: FakeLayerThing,
    Marker: FakeLayerThing,
    setWorkerUrl: () => {},
  }
})

const T0 = '2026-10-15T12:00:00+00:00'
const PLAN: Plan = {
  origin: { label: 'Here', lat: 40, lon: -90 },
  destination: { label: 'There', lat: 41, lon: -90 },
  departure: T0,
  load_lb: 40000,
  interval_mi: 25,
  provider: 'valhalla',
  routes: [
    {
      name: 'Route A',
      provider: 'valhalla',
      miles: 69,
      seconds: 3600,
      arrival: '2026-10-15T13:00:00+00:00',
      geometry: [
        [-90, 40],
        [-90, 41],
      ],
      checkpoints: [
        { index: 0, mile: 0, lat: 40, lon: -90, eta: T0, wind_mph: 5, rain_in_hr: 0, snow_in_hr: 0, level: 0, level_name: 'Low', reasons: [] },
        { index: 1, mile: 69, lat: 41, lon: -90, eta: '2026-10-15T13:00:00+00:00', wind_mph: 30, rain_in_hr: 0, snow_in_hr: 0, level: 1, level_name: 'Moderate', reasons: ['wind 30 mph'] },
      ],
      risk: { miles_by_level: { Low: 0, Moderate: 69, High: 0, Severe: 0, 'No Travel': 0 }, average: 1, severe_miles: 0, high_miles: 0, no_travel_miles: 0 },
      rank: 1,
      recommended: true,
    },
  ],
  recommended: 'Route A',
  reason: 'Only one route was found.',
  levels: ['Low', 'Moderate', 'High', 'Severe', 'No Travel'],
  weather_grid_deg: 0.1,
  heatmap: { start: T0, hours: 48, step_deg: 0.2, points: [[-90, 40]], frames: Array.from({ length: 49 }, () => [0]) },
}

beforeEach(() => {
  mapStart.error = null
  vi.spyOn(console, 'warn').mockImplementation(() => {})
  vi.stubGlobal(
    'fetch',
    vi.fn(async (url: string) => {
      const body = url.startsWith('/api/geocode') ? { results: [] } : PLAN
      return new Response(JSON.stringify(body), { status: 200, headers: { 'Content-Type': 'application/json' } })
    }),
  )
})

afterEach(() => {
  cleanup()
  vi.unstubAllGlobals()
  vi.restoreAllMocks()
})

async function planATrip() {
  fireEvent.change(screen.getByLabelText('Origin'), { target: { value: 'Here' } })
  fireEvent.change(screen.getByLabelText('Destination'), { target: { value: 'There' } })
  fireEvent.click(screen.getByRole('button', { name: 'Plan routes' }))
  await screen.findByText('Only one route was found.')
}

describe('without WebGL', () => {
  it('keeps the form and results, says why the map is missing, and drops the map-only controls', async () => {
    mapStart.error = new Error('Failed to initialize WebGL')
    const { container } = render(<App />)
    expect(screen.getByText("The map can't be drawn in this browser.")).toBeTruthy()

    await planATrip()
    expect(container.querySelectorAll('.route-card')).toHaveLength(1)
    expect(container.querySelectorAll('.checkpoints tbody tr')).toHaveLength(2)
    expect(container.querySelectorAll('.checkpoints tbody tr.clickable')).toHaveLength(0)
    expect(screen.queryByRole('checkbox', { name: /Risk heatmap/ })).toBeNull()
  })
})

describe('with a working map', () => {
  it('shows the heatmap control and lets checkpoint rows find the checkpoint on the map', async () => {
    const { container } = render(<App />)
    expect(screen.queryByRole('note')).toBeNull()

    await planATrip()
    expect(screen.getByRole('checkbox', { name: /Risk heatmap/ })).toBeTruthy()
    await waitFor(() => expect(container.querySelectorAll('.checkpoints tbody tr.clickable')).toHaveLength(2))
  })
})

describe('when the map fails for another reason', () => {
  it('says the map stopped working without blaming WebGL', () => {
    mapStart.error = new Error("Invalid type: 'container' must be a String or HTMLElement.")
    render(<App />)
    expect(screen.getByText('The map stopped working.')).toBeTruthy()
    expect(screen.queryByText(/WebGL/)).toBeNull()
    expect(screen.getByLabelText('Origin')).toBeTruthy()
  })

  it('catches an error thrown while drawing the map and keeps the rest of the page', () => {
    vi.spyOn(console, 'error').mockImplementation(() => {})
    const onError = vi.fn()
    function Broken(): never {
      throw new Error('boom')
    }
    render(
      <main>
        <p>panel</p>
        <MapBoundary onError={onError}>
          <Broken />
        </MapBoundary>
      </main>,
    )
    expect(screen.getByText('panel')).toBeTruthy()
    expect(screen.getByText('The map stopped working.')).toBeTruthy()
    expect(onError).toHaveBeenCalledOnce()
  })
})

describe('the map on its own', () => {
  it('reports that it is unavailable instead of throwing when WebGL is missing', () => {
    mapStart.error = new Error('Failed to initialize WebGL')
    const onUnavailable = vi.fn()
    render(
      <MapView
        plan={null}
        selected=""
        hour={0}
        showHeatmap
        focus={null}
        onSelectRoute={() => {}}
        onUnavailable={onUnavailable}
      />,
    )
    expect(screen.getByText("The map can't be drawn in this browser.")).toBeTruthy()
    expect(onUnavailable).toHaveBeenCalledOnce()
  })
})
