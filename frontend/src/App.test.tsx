import { act, cleanup, fireEvent, render, screen, waitFor } from '@testing-library/react'
import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest'
import App from './App'
import AppProviders from './AppProviders'
import { MapBoundary } from './components/MapFallback'
import MapView from './components/MapView'
import type { Plan } from './types'

// MapLibre needs WebGL, which jsdom doesn't have; the fake map can be told to fail the way MapLibre does.
const mapStart = vi.hoisted(() => ({ error: null as Error | null, handlers: {} as Record<string, (() => void)[]> }))

vi.mock('maplibre-gl', () => {
  class FakeMap {
    constructor() {
      if (mapStart.error) throw mapStart.error
    }
    addControl() {}
    on(type: string, layerOrHandler: unknown, handler?: () => void) {
      const fn = (typeof layerOrHandler === 'function' ? layerOrHandler : handler) as () => void
      ;(mapStart.handlers[type] ??= []).push(fn)
    }
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
  tradeoff: null,
  levels: ['Low', 'Moderate', 'High', 'Severe', 'No Travel'],
  weather_grid_deg: 0.1,
  heatmap: { start: T0, hours: 48, step_deg: 0.2, points: [[-90, 40]], frames: Array.from({ length: 49 }, () => [0]) },
}

const CHICAGO = { label: 'Chicago, Illinois, US', lat: 41.8756, lon: -87.6244 }
const api = vi.hoisted(() => ({ suggestions: [] as unknown[], planReply: null as null | { status: number; body: unknown } }))

const json = (body: unknown, status = 200) =>
  new Response(JSON.stringify(body), { status, headers: { 'Content-Type': 'application/json' } })

beforeEach(() => {
  mapStart.error = null
  mapStart.handlers = {}
  api.suggestions = []
  api.planReply = null
  vi.spyOn(console, 'warn').mockImplementation(() => {})
  vi.stubGlobal(
    'fetch',
    vi.fn(async (url: string) => {
      if (url.startsWith('/api/geocode')) return json({ results: api.suggestions })
      return api.planReply ? json(api.planReply.body, api.planReply.status) : json(PLAN)
    }),
  )
})

const fetchCalls = () => (fetch as unknown as { mock: { calls: [string, RequestInit?][] } }).mock.calls

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
    const { container } = render(<App />, { wrapper: AppProviders })
    expect(await screen.findByText("The map can't be drawn in this browser.")).toBeTruthy()

    await planATrip()
    expect(container.querySelectorAll('.route-card')).toHaveLength(1)
    expect(container.querySelectorAll('.checkpoints tbody tr')).toHaveLength(2)
    expect(container.querySelectorAll('.checkpoints tbody tr.clickable')).toHaveLength(0)
    expect(screen.queryByRole('switch', { name: /Risk heatmap/ })).toBeNull()
  })
})

describe('with a working map', () => {
  it('shows the heatmap control and lets checkpoint rows find the checkpoint on the map', async () => {
    const { container } = render(<App />, { wrapper: AppProviders })
    expect(screen.queryByRole('note')).toBeNull()

    await planATrip()
    expect(screen.getByRole('switch', { name: /Risk heatmap/ })).toBeTruthy()
    await waitFor(() => expect(container.querySelectorAll('.checkpoints tbody tr.clickable')).toHaveLength(2))
  })
})

describe('when the map fails for another reason', () => {
  it('says the map stopped working without blaming WebGL', async () => {
    mapStart.error = new Error("Invalid type: 'container' must be a String or HTMLElement.")
    render(<App />, { wrapper: AppProviders })
    expect(await screen.findByText('The map stopped working.')).toBeTruthy()
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

describe('the place boxes', () => {
  it('search only from three letters, once per pause in typing', async () => {
    render(<App />, { wrapper: AppProviders })
    const origin = screen.getByRole('combobox', { name: 'Origin' })
    fireEvent.change(origin, { target: { value: 'Ch' } })
    await new Promise((r) => setTimeout(r, 500))
    expect(fetchCalls().filter(([u]) => u.startsWith('/api/geocode'))).toHaveLength(0)
    fireEvent.change(origin, { target: { value: 'Chic' } })
    fireEvent.change(origin, { target: { value: 'Chica' } })
    await waitFor(() => expect(fetchCalls().filter(([u]) => u.startsWith('/api/geocode'))).toHaveLength(1))
    expect(fetchCalls()[0][0]).toBe('/api/geocode?q=Chica')
  })

  it('keep a picked place, drop it when typed over, and send picked places as coordinates', async () => {
    api.suggestions = [CHICAGO]
    render(<App />, { wrapper: AppProviders })
    const origin = screen.getByRole('combobox', { name: 'Origin' })
    fireEvent.change(origin, { target: { value: 'Chica' } })
    fireEvent.click(await screen.findByRole('option', { name: 'Chicago, Illinois, US' }))
    expect(screen.getByText('41.8756, -87.6244')).toBeTruthy()
    expect((origin as HTMLInputElement).value).toBe('Chicago, Illinois, US')

    fireEvent.change(origin, { target: { value: 'Chicago, Illinois, US!' } })
    expect(screen.queryByText('41.8756, -87.6244')).toBeNull()
    fireEvent.change(origin, { target: { value: 'Chica' } })
    fireEvent.click(await screen.findByRole('option', { name: 'Chicago, Illinois, US' }))

    fireEvent.change(screen.getByRole('combobox', { name: 'Destination' }), { target: { value: 'Denver, CO' } })
    fireEvent.click(screen.getByRole('button', { name: 'Plan routes' }))
    await screen.findByText('Only one route was found.')
    const [, init] = fetchCalls().find(([u]) => u === '/api/plan')!
    const sent = JSON.parse(String(init?.body))
    expect(sent.origin).toEqual(CHICAGO)
    expect(sent.destination).toBe('Denver, CO')
  })
})

describe('a re-plan that fails', () => {
  it('keeps the last results on screen and says so', async () => {
    const { container } = render(<App />, { wrapper: AppProviders })
    await planATrip()
    api.planReply = { status: 400, body: { error: "No place matches 'Atlantis'." } }
    fireEvent.change(screen.getByLabelText('Origin'), { target: { value: 'Atlantis' } })
    fireEvent.click(screen.getByRole('button', { name: 'Plan routes' }))
    expect((await screen.findByRole('alert')).textContent).toBe(
      "No place matches 'Atlantis'. The map still shows the last plan.",
    )
    expect(container.querySelectorAll('.route-card')).toHaveLength(1)
  })
})

describe("when the browser takes the map's graphics away", () => {
  it('says so, and clears the notice when they come back', () => {
    render(
      <MapView plan={null} selected="" hour={0} showHeatmap focus={null} onSelectRoute={() => {}} onUnavailable={() => {}} />,
      { wrapper: AppProviders },
    )
    const notice = /The browser paused the map's graphics/
    expect(screen.queryByText(notice)).toBeNull()
    act(() => mapStart.handlers.webglcontextlost.forEach((fn) => fn()))
    expect(screen.getByText(notice)).toBeTruthy()
    act(() => mapStart.handlers.webglcontextrestored.forEach((fn) => fn()))
    expect(screen.queryByText(notice)).toBeNull()
  })
})
