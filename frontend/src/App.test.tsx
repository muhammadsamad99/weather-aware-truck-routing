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
const api = vi.hoisted(() => ({
  suggestions: [] as unknown[],
  planReply: null as null | { status: number; body: unknown },
  rawPlanReply: null as null | Response,
  holdNextPlan: false, // the next plan request waits until it is aborted, or released
  release: () => {},
}))

const json = (body: unknown, status = 200) =>
  new Response(JSON.stringify(body), { status, headers: { 'Content-Type': 'application/json' } })

beforeEach(() => {
  mapStart.error = null
  mapStart.handlers = {}
  api.suggestions = []
  api.planReply = null
  api.rawPlanReply = null
  api.holdNextPlan = false
  vi.spyOn(console, 'warn').mockImplementation(() => {})
  vi.stubGlobal(
    'fetch',
    vi.fn(async (url: string, init?: RequestInit) => {
      if (url.startsWith('/api/geocode')) return json({ results: api.suggestions })
      if (api.holdNextPlan) {
        api.holdNextPlan = false
        return new Promise<Response>((resolve, reject) => {
          api.release = () => resolve(json(PLAN))
          init?.signal?.addEventListener('abort', () => reject(new DOMException('aborted', 'AbortError')))
        })
      }
      if (api.rawPlanReply) return api.rawPlanReply
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

const ROUTE_B = {
  ...PLAN.routes[0],
  name: 'Route B',
  rank: 2,
  recommended: false,
  checkpoints: [
    ...PLAN.routes[0].checkpoints,
    { ...PLAN.routes[0].checkpoints[1], index: 2, mile: 80 },
  ],
}
const TWO_ROUTES: Plan = { ...PLAN, routes: [PLAN.routes[0], ROUTE_B] }
const planCalls = () => fetchCalls().filter(([u]) => u === '/api/plan')
const geocodeCalls = () => fetchCalls().filter(([u]) => u.startsWith('/api/geocode'))

describe('the results', () => {
  it('switch to the route whose card is picked, in the cards and the checkpoint table', async () => {
    api.planReply = { status: 200, body: TWO_ROUTES }
    const { container } = render(<App />, { wrapper: AppProviders })
    fireEvent.change(screen.getByLabelText('Origin'), { target: { value: 'Here' } })
    fireEvent.change(screen.getByLabelText('Destination'), { target: { value: 'There' } })
    fireEvent.click(screen.getByRole('button', { name: 'Plan routes' }))
    const cardB = await screen.findByRole('button', { name: /^Route B, rank 2:/ })
    const cardA = screen.getByRole('button', { name: /^Route A, rank 1, recommended:/ })
    expect(cardA.getAttribute('aria-pressed')).toBe('true')
    expect(screen.getByText('Route A: 2 checkpoints, every 25 mi')).toBeTruthy()
    fireEvent.click(cardB)
    expect(cardB.getAttribute('aria-pressed')).toBe('true')
    expect(cardA.getAttribute('aria-pressed')).toBe('false')
    expect(screen.getByText('Route B: 3 checkpoints, every 25 mi')).toBeTruthy()
    expect(container.querySelectorAll('.checkpoints tbody tr')).toHaveLength(3)
  })

  it('announce the plan once in a status region, without the running seconds', async () => {
    render(<App />, { wrapper: AppProviders })
    api.holdNextPlan = true
    fireEvent.change(screen.getByLabelText('Origin'), { target: { value: 'Here' } })
    fireEvent.change(screen.getByLabelText('Destination'), { target: { value: 'There' } })
    fireEvent.click(screen.getByRole('button', { name: 'Plan routes' }))
    expect(screen.getByRole('status').textContent).toBe('Routing and checking the forecast…')
    await act(async () => api.release())
    await screen.findByText('Only one route was found.')
    expect(screen.getByRole('status').textContent).toBe('Planned: Route A is recommended.')
  })

  it('give the checkpoint table one Tab stop, with the arrow keys moving between rows', async () => {
    api.planReply = { status: 200, body: TWO_ROUTES }
    const { container } = render(<App />, { wrapper: AppProviders })
    fireEvent.change(screen.getByLabelText('Origin'), { target: { value: 'Here' } })
    fireEvent.change(screen.getByLabelText('Destination'), { target: { value: 'There' } })
    fireEvent.click(screen.getByRole('button', { name: 'Plan routes' }))
    await screen.findByText('Route A: 2 checkpoints, every 25 mi')
    const rows = () => [...container.querySelectorAll<HTMLElement>('.checkpoints tbody tr')]
    await waitFor(() => expect(rows().map((r) => r.tabIndex)).toEqual([0, -1]))
    act(() => rows()[0].focus())
    fireEvent.keyDown(rows()[0], { key: 'ArrowDown' })
    expect(document.activeElement).toBe(rows()[1])
    expect(rows().map((r) => r.tabIndex)).toEqual([-1, 0])
    fireEvent.keyDown(rows()[1], { key: 'ArrowUp' })
    expect(document.activeElement).toBe(rows()[0])
  })

  it('leave no id reference dangling and no id used twice', async () => {
    api.planReply = { status: 200, body: TWO_ROUTES }
    const { container } = render(<App />, { wrapper: AppProviders })
    fireEvent.change(screen.getByLabelText('Origin'), { target: { value: 'Here' } })
    fireEvent.change(screen.getByLabelText('Destination'), { target: { value: 'There' } })
    fireEvent.click(screen.getByRole('button', { name: 'Plan routes' }))
    await screen.findByText('Route A: 2 checkpoints, every 25 mi')
    const ids = [...container.querySelectorAll('[id]')].map((e) => e.id)
    expect(ids.filter((id, i) => ids.indexOf(id) !== i)).toEqual([])
    const refs = [...container.querySelectorAll('[aria-labelledby], [aria-describedby], [aria-controls], label[for]')]
      .flatMap((e) =>
        ['aria-labelledby', 'aria-describedby', 'aria-controls', 'for'].flatMap((a) => (e.getAttribute(a) ?? '').split(/\s+/)),
      )
      .filter(Boolean)
    expect(refs.length).toBeGreaterThan(5)
    expect(refs.filter((id) => !document.getElementById(id))).toEqual([])
  })
})

describe('the form', () => {
  it('checks the trip before asking the server', () => {
    render(<App />, { wrapper: AppProviders })
    fireEvent.change(screen.getByLabelText('Destination'), { target: { value: 'There' } })
    fireEvent.click(screen.getByRole('button', { name: 'Plan routes' }))
    expect(screen.getByText('Enter where the trip starts.')).toBeTruthy()
    expect(planCalls()).toHaveLength(0)
  })

  it("shows the server's message under the field it is about", async () => {
    api.planReply = { status: 400, body: { error: 'Please check the trip details.', fields: { load_lb: ['Too heavy.'] } } }
    render(<App />, { wrapper: AppProviders })
    fireEvent.change(screen.getByLabelText('Origin'), { target: { value: 'Here' } })
    fireEvent.change(screen.getByLabelText('Destination'), { target: { value: 'There' } })
    fireEvent.click(screen.getByRole('button', { name: 'Plan routes' }))
    expect(await screen.findByText('Too heavy.')).toBeTruthy()
    expect(screen.getByLabelText('Load').getAttribute('aria-invalid')).toBe('true')
  })

  it('replaces a plan still in progress, without reporting the replaced one as an error', async () => {
    render(<App />, { wrapper: AppProviders })
    api.holdNextPlan = true
    fireEvent.change(screen.getByLabelText('Origin'), { target: { value: 'Here' } })
    fireEvent.change(screen.getByLabelText('Destination'), { target: { value: 'There' } })
    const button = screen.getByRole('button', { name: 'Plan routes' })
    act(() => {
      // both clicks before the button can show it is busy, as with a fast double click
      fireEvent.click(button)
      fireEvent.click(button)
    })
    await screen.findByText('Only one route was found.')
    expect(planCalls()).toHaveLength(2)
    expect(planCalls()[0][1]?.signal?.aborted).toBe(true)
    expect(screen.queryByRole('alert')).toBeNull()
  })

  it("doesn't look up the example's places in the background", async () => {
    render(<App />, { wrapper: AppProviders })
    fireEvent.click(screen.getByRole('button', { name: /Try an example/ }))
    expect((screen.getByLabelText('Origin') as HTMLInputElement).value).toBe('Chicago, IL')
    await new Promise((r) => setTimeout(r, 600))
    expect(geocodeCalls()).toHaveLength(0)
  })

  it('steps the load in whole 500 lb steps from the default', () => {
    render(<App />, { wrapper: AppProviders })
    const load = screen.getByLabelText('Load') as HTMLInputElement
    expect(load.value).toBe('40000')
    load.stepUp()
    expect(load.value).toBe('40500')
  })

  it('searches from exactly three letters, after a pause', async () => {
    render(<App />, { wrapper: AppProviders })
    fireEvent.change(screen.getByRole('combobox', { name: 'Origin' }), { target: { value: 'Chi' } })
    await new Promise((r) => setTimeout(r, 250))
    expect(geocodeCalls()).toHaveLength(0) // still waiting for the pause
    await waitFor(() => expect(geocodeCalls()).toHaveLength(1))
    expect(geocodeCalls()[0][0]).toBe('/api/geocode?q=Chi')
  })
})

describe('an answer the app cannot read', () => {
  it('is reported, and the last plan stays', async () => {
    const { container } = render(<App />, { wrapper: AppProviders })
    await planATrip()
    api.rawPlanReply = new Response('<html>Bad Gateway</html>', { status: 200, headers: { 'Content-Type': 'text/html' } })
    fireEvent.click(screen.getByRole('button', { name: 'Plan routes' }))
    expect((await screen.findByRole('alert')).textContent).toBe(
      'The server sent an answer that could not be read. Try again. The map still shows the last plan.',
    )
    expect(container.querySelectorAll('.route-card')).toHaveLength(1)
    api.rawPlanReply = json({ ok: true }) // JSON, but not a plan
    fireEvent.click(screen.getByRole('button', { name: 'Plan routes' }))
    await waitFor(() => expect(planCalls()).toHaveLength(3))
    expect((await screen.findByRole('alert')).textContent).toMatch(/^The server sent an answer that could not be read/)
    expect(container.querySelectorAll('.route-card')).toHaveLength(1)
  })

  it('in place search leaves the box working', async () => {
    vi.mocked(fetch).mockImplementation(async (url) =>
      String(url).startsWith('/api/geocode') ? json({ unexpected: true }) : json(PLAN),
    )
    render(<App />, { wrapper: AppProviders })
    const origin = screen.getByRole('combobox', { name: 'Origin' })
    fireEvent.change(origin, { target: { value: 'Chica' } })
    await waitFor(() => expect(geocodeCalls()).toHaveLength(1))
    await new Promise((r) => setTimeout(r, 50))
    expect(screen.getByLabelText('Origin')).toBe(origin)
  })
})

describe('the heatmap control', () => {
  async function planned() {
    render(<App />, { wrapper: AppProviders })
    await planATrip()
    return screen.getByRole('slider', { name: 'Hours after departure' })
  }

  it('plays hour by hour, wraps at the end, and turns the heatmap off', async () => {
    const slider = await planned()
    vi.useFakeTimers()
    try {
      fireEvent.click(screen.getByRole('button', { name: 'Play the next 48 hours' }))
      act(() => vi.advanceTimersByTime(1400))
      expect(slider.getAttribute('aria-valuenow')).toBe('2')
      fireEvent.click(screen.getByRole('button', { name: 'Pause' }))
      fireEvent.keyDown(slider, { key: 'End' })
      expect(slider.getAttribute('aria-valuenow')).toBe('48')
      fireEvent.click(screen.getByRole('button', { name: 'Play the next 48 hours' }))
      act(() => vi.advanceTimersByTime(700))
      expect(slider.getAttribute('aria-valuenow')).toBe('0')
    } finally {
      vi.useRealTimers()
    }
    const toggle = screen.getByRole('switch', { name: /Risk heatmap/ }) as HTMLInputElement
    expect(toggle.checked).toBe(true)
    fireEvent.click(toggle)
    expect(toggle.checked).toBe(false)
  })

  it('starts again at departure for a new plan', async () => {
    const slider = await planned()
    fireEvent.keyDown(slider, { key: 'End' })
    expect(slider.getAttribute('aria-valuenow')).toBe('48')
    api.planReply = { status: 200, body: { ...PLAN, departure: '2026-10-16T12:00:00+00:00' } }
    fireEvent.click(screen.getByRole('button', { name: 'Plan routes' }))
    await waitFor(() =>
      expect(screen.getByRole('slider', { name: 'Hours after departure' }).getAttribute('aria-valuenow')).toBe('0'),
    )
  })
})
