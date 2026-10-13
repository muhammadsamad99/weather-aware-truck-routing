import maplibregl, {
  type ExpressionSpecification,
  type GeoJSONSource,
  type MapLayerMouseEvent,
  type StyleSpecification,
} from 'maplibre-gl'
import 'maplibre-gl/dist/maplibre-gl.css'
import { useEffect, useMemo, useRef, useState } from 'react'
import { bounds, haversineMi, positionAt } from '../geometry'
import { levelColor, levelColorExpression } from '../levels'
import { formatDateTime, formatMiles } from '../format'
import type { Checkpoint, Plan, PlannedRoute } from '../types'

const BASE_STYLE = 'https://tiles.openfreemap.org/styles/liberty'
// Used only if the base map cannot load, so the routes and the weather still show.
const FALLBACK_STYLE: StyleSpecification = {
  version: 8,
  sources: {},
  layers: [{ id: 'background', type: 'background', paint: { 'background-color': '#eef1f4' } }],
}
const SELECTED_COLOR = '#1d4ed8'
const OTHER_COLOR = '#7b8698'
const METERS_PER_DEGREE = 111_320
const METERS_PER_PIXEL_AT_ZOOM_0 = 78_271.517 // 512 px tiles, at the equator

export interface Focus {
  route: string
  index: number
  nonce: number
}

interface Props {
  plan: Plan | null
  selected: string
  hour: number
  showHeatmap: boolean
  focus: Focus | null
  onSelectRoute: (name: string) => void
}

const empty: GeoJSON.FeatureCollection = { type: 'FeatureCollection', features: [] }

export default function MapView({ plan, selected, hour, showHeatmap, focus, onSelectRoute }: Props) {
  const container = useRef<HTMLDivElement>(null)
  const mapRef = useRef<maplibregl.Map | null>(null)
  const [ready, setReady] = useState(0) // bumps each time a style (and our layers) finishes loading
  const [baseMapFailed, setBaseMapFailed] = useState(false)
  const planRef = useRef(plan)
  const selectRef = useRef(onSelectRoute)
  const popup = useRef<maplibregl.Popup | null>(null)
  const markers = useRef<maplibregl.Marker[]>([])
  const truck = useRef<maplibregl.Marker | null>(null)

  useEffect(() => {
    planRef.current = plan
    selectRef.current = onSelectRoute
  })

  // The map is created once; its layers are added whenever a style loads.
  useEffect(() => {
    const map = new maplibregl.Map({
      container: container.current!,
      style: BASE_STYLE,
      center: [-96, 39],
      zoom: 3.4,
      attributionControl: { compact: true },
    })
    mapRef.current = map
    map.addControl(new maplibregl.NavigationControl({ showCompass: false }), 'top-right')
    map.addControl(new maplibregl.ScaleControl({ unit: 'imperial' }), 'bottom-left')
    popup.current = new maplibregl.Popup({ closeButton: true, maxWidth: '280px', offset: 10 })

    let styleLoaded = false
    map.on('style.load', () => {
      styleLoaded = true
      addLayers(map)
      setReady((n) => n + 1)
    })
    map.on('error', (e) => {
      if (!styleLoaded) {
        console.warn('Base map unavailable, using a plain background.', e.error)
        styleLoaded = true
        setBaseMapFailed(true)
        map.setStyle(FALLBACK_STYLE)
      }
    })

    map.on('click', 'checkpoints', (e: MapLayerMouseEvent) => {
      const f = e.features?.[0]
      if (!f) return
      const { route, index } = f.properties as { route: string; index: number }
      const cp = findCheckpoint(planRef.current, route, index)
      if (cp) showPopup(map, popup.current!, route, cp)
    })
    map.on('click', 'routes', (e: MapLayerMouseEvent) => {
      if (map.queryRenderedFeatures(e.point, { layers: ['checkpoints'] }).length) return
      const name = e.features?.[0]?.properties?.name
      if (name) selectRef.current(name)
    })
    for (const layer of ['checkpoints', 'routes']) {
      map.on('mouseenter', layer, () => (map.getCanvas().style.cursor = 'pointer'))
      map.on('mouseleave', layer, () => (map.getCanvas().style.cursor = ''))
    }
    return () => {
      map.remove()
      mapRef.current = null
    }
  }, [])

  // Routes, checkpoints, end markers and route labels.
  useEffect(() => {
    const map = mapRef.current
    if (!map || !ready) return
    ;(map.getSource('routes') as GeoJSONSource).setData(plan ? routesData(plan.routes, selected) : empty)
    ;(map.getSource('checkpoints') as GeoJSONSource).setData(plan ? checkpointsData(plan.routes, selected) : empty)
    markers.current.forEach((m) => m.remove())
    markers.current = plan ? endMarkers(plan).concat(routeLabels(plan.routes, selected, selectRef)) : []
    markers.current.forEach((m) => m.addTo(map))
  }, [plan, selected, ready])

  // Fit the map to a new plan, and close any popup from the last one.
  useEffect(() => {
    const map = mapRef.current
    if (!map || !plan) return
    popup.current?.remove()
    const wide = map.getContainer().clientWidth > 700
    map.fitBounds(bounds(plan.routes), { padding: wide ? 70 : 30, duration: 800, maxZoom: 11 })
  }, [plan])

  // The heatmap: every frame is built once per plan, so moving the slider only swaps data.
  const frames = useMemo(() => (plan ? heatFrames(plan) : []), [plan])
  useEffect(() => {
    const map = mapRef.current
    if (!map || !ready) return
    ;(map.getSource('heat') as GeoJSONSource).setData(frames[hour] ?? empty)
  }, [frames, hour, ready])
  useEffect(() => {
    const map = mapRef.current
    if (!map || !ready || !plan) return
    map.setPaintProperty('heat', 'circle-radius', heatRadius(plan))
  }, [plan, ready])
  useEffect(() => {
    const map = mapRef.current
    if (!map || !ready) return
    map.setLayoutProperty('heat', 'visibility', showHeatmap ? 'visible' : 'none')
  }, [showHeatmap, ready])

  // Where the truck is on the selected route at the slider's hour.
  useEffect(() => {
    const map = mapRef.current
    if (!map) return
    const route = plan?.routes.find((r) => r.name === selected)
    const at = route && plan ? positionAt(route, new Date(Date.parse(plan.heatmap.start) + hour * 3_600_000)) : null
    if (!at) {
      truck.current?.remove()
      truck.current = null
      return
    }
    if (!truck.current) {
      const el = document.createElement('div')
      el.className = 'truck-marker'
      el.title = 'The truck at the slider time'
      truck.current = new maplibregl.Marker({ element: el })
    }
    truck.current.setLngLat(at.lonLat).addTo(map)
  }, [plan, selected, hour])

  // Fly to a checkpoint picked in the table.
  useEffect(() => {
    const map = mapRef.current
    if (!map || !focus) return
    const cp = findCheckpoint(planRef.current, focus.route, focus.index)
    if (!cp) return
    map.flyTo({ center: [cp.lon, cp.lat], zoom: Math.max(map.getZoom(), 8), duration: 700 })
    showPopup(map, popup.current!, focus.route, cp)
  }, [focus])

  return (
    <div className="map-wrap">
      <div ref={container} className="map" role="region" aria-label="Map of the routes and the weather risk" />
      {baseMapFailed && <div className="map-notice">The base map could not load; routes and weather still show.</div>}
    </div>
  )
}

function addLayers(map: maplibregl.Map) {
  map.addSource('heat', { type: 'geojson', data: empty })
  map.addSource('routes', { type: 'geojson', data: empty })
  map.addSource('checkpoints', { type: 'geojson', data: empty })
  // The heatmap goes under the base map's labels, so place names stay readable.
  const firstLabel = map.getStyle().layers.find((l) => l.type === 'symbol')?.id
  map.addLayer(
    {
      id: 'heat',
      type: 'circle',
      source: 'heat',
      paint: {
        'circle-color': levelColorExpression,
        'circle-opacity': ['interpolate', ['linear'], ['get', 'level'], 0, 0.18, 1, 0.45, 4, 0.62],
        'circle-blur': 0.75,
        'circle-radius': 8,
        'circle-pitch-alignment': 'map',
      },
    },
    firstLabel,
  )
  map.addLayer({
    id: 'routes-casing',
    type: 'line',
    source: 'routes',
    layout: { 'line-join': 'round', 'line-cap': 'round', 'line-sort-key': ['get', 'order'] },
    paint: { 'line-color': '#ffffff', 'line-width': ['case', ['get', 'selected'], 10, 7] },
  })
  map.addLayer({
    id: 'routes',
    type: 'line',
    source: 'routes',
    layout: { 'line-join': 'round', 'line-cap': 'round', 'line-sort-key': ['get', 'order'] },
    paint: {
      'line-color': ['case', ['get', 'selected'], SELECTED_COLOR, OTHER_COLOR],
      'line-width': ['case', ['get', 'selected'], 6, 4],
      'line-opacity': ['case', ['get', 'selected'], 1, 0.75],
    },
  })
  map.addLayer({
    id: 'checkpoints',
    type: 'circle',
    source: 'checkpoints',
    layout: { 'circle-sort-key': ['case', ['get', 'selected'], 1, 0] },
    paint: {
      'circle-color': levelColorExpression,
      'circle-radius': ['case', ['get', 'selected'], 6.5, 4],
      'circle-stroke-color': '#ffffff',
      'circle-stroke-width': ['case', ['get', 'selected'], 2, 1],
      'circle-opacity': ['case', ['get', 'selected'], 1, 0.7],
      'circle-stroke-opacity': ['case', ['get', 'selected'], 1, 0.7],
    },
  })
}

function routesData(routes: PlannedRoute[], selected: string): GeoJSON.FeatureCollection {
  return {
    type: 'FeatureCollection',
    features: routes.map((r) => ({
      type: 'Feature',
      properties: { name: r.name, selected: r.name === selected, order: r.name === selected ? 2 : r.recommended ? 1 : 0 },
      geometry: { type: 'LineString', coordinates: r.geometry },
    })),
  }
}

function checkpointsData(routes: PlannedRoute[], selected: string): GeoJSON.FeatureCollection {
  return {
    type: 'FeatureCollection',
    features: routes.flatMap((r) =>
      r.checkpoints.map((c) => ({
        type: 'Feature' as const,
        properties: { route: r.name, index: c.index, level: c.level, selected: r.name === selected },
        geometry: { type: 'Point' as const, coordinates: [c.lon, c.lat] },
      })),
    ),
  }
}

function heatFrames(plan: Plan): GeoJSON.FeatureCollection[] {
  const { points, frames } = plan.heatmap
  return frames.map((levels) => ({
    type: 'FeatureCollection',
    features: points.map((coordinates, i) => ({
      type: 'Feature',
      properties: { level: levels[i] },
      geometry: { type: 'Point', coordinates },
    })),
  }))
}

/** Disc size that follows the zoom, so each grid point's disc covers a little more than its grid cell on the
 * ground and neighbouring discs blend into one field. */
function heatRadius(plan: Plan): ExpressionSpecification {
  const lats = plan.heatmap.points.map((p) => p[1])
  const midLat = lats.length ? (Math.min(...lats) + Math.max(...lats)) / 2 : 39
  const meters = plan.heatmap.step_deg * METERS_PER_DEGREE * 1.15
  const atZoom0 = meters / (METERS_PER_PIXEL_AT_ZOOM_0 * Math.cos((midLat * Math.PI) / 180))
  return ['interpolate', ['exponential', 2], ['zoom'], 0, atZoom0, 20, atZoom0 * 2 ** 20]
}

function findCheckpoint(plan: Plan | null, route: string, index: number): Checkpoint | undefined {
  return plan?.routes.find((r) => r.name === route)?.checkpoints.find((c) => c.index === index)
}

function showPopup(map: maplibregl.Map, popup: maplibregl.Popup, route: string, cp: Checkpoint) {
  const root = document.createElement('div')
  root.className = 'cp-popup'
  const head = document.createElement('div')
  head.className = 'cp-head'
  const chip = document.createElement('span')
  chip.className = 'level-chip'
  chip.style.background = levelColor(cp.level)
  chip.textContent = cp.level_name
  const title = document.createElement('strong')
  title.textContent = `${route} · mile ${cp.mile.toFixed(0)}`
  head.append(title, chip)
  const rows: [string, string][] = [
    ['Truck arrives', formatDateTime(cp.eta)],
    ['Wind', `${cp.wind_mph.toFixed(0)} mph`],
    ['Rain', `${cp.rain_in_hr.toFixed(2)} in/hr`],
    ['Snow', `${cp.snow_in_hr.toFixed(2)} in/hr`],
  ]
  if (cp.reasons.length) rows.push(['Why', cp.reasons.join('; ')])
  const dl = document.createElement('dl')
  for (const [k, v] of rows) {
    const dt = document.createElement('dt')
    dt.textContent = k
    const dd = document.createElement('dd')
    dd.textContent = v
    dl.append(dt, dd)
  }
  root.append(head, dl)
  popup.setLngLat([cp.lon, cp.lat]).setDOMContent(root).addTo(map)
}

function endMarkers(plan: Plan): maplibregl.Marker[] {
  return [
    { place: plan.origin, cls: 'origin', text: 'A' },
    { place: plan.destination, cls: 'destination', text: 'B' },
  ].map(({ place, cls, text }) => {
    const el = document.createElement('div')
    el.className = `end-marker ${cls}`
    el.textContent = text
    el.title = place.label
    return new maplibregl.Marker({ element: el }).setLngLat([place.lon, place.lat])
  })
}

/** A name tag on each route, at the point where it is furthest from the other routes, so tags do not stack. */
function routeLabels(
  routes: PlannedRoute[],
  selected: string,
  selectRef: React.RefObject<(name: string) => void>,
): maplibregl.Marker[] {
  return routes.map((r) => {
    const el = document.createElement('button')
    el.type = 'button'
    el.className = `route-label${r.name === selected ? ' selected' : ''}`
    el.textContent = `${r.name} · ${formatMiles(r.miles)}${r.recommended ? ' · Recommended' : ''}`
    el.addEventListener('click', (e) => {
      e.stopPropagation()
      selectRef.current(r.name)
    })
    const others = routes.filter((o) => o !== r).map((o) => sample(o.geometry, 200))
    return new maplibregl.Marker({ element: el, anchor: 'bottom', offset: [0, -6] }).setLngLat(labelPoint(r, others))
  })
}

function labelPoint(route: PlannedRoute, others: [number, number][][]): [number, number] {
  const candidates = sample(route.geometry, 200)
  // keep away from the two ends, where every route meets
  const inner = candidates.slice(Math.floor(candidates.length * 0.15), Math.ceil(candidates.length * 0.85))
  if (!others.length || !inner.length) return route.geometry[Math.floor(route.geometry.length / 2)]
  let best = inner[0]
  let bestGap = -1
  for (const p of inner) {
    let gap = Infinity
    for (const line of others) for (const q of line) gap = Math.min(gap, haversineMi(p, q))
    if (gap > bestGap) [best, bestGap] = [p, gap]
  }
  return best
}

function sample(points: [number, number][], max: number): [number, number][] {
  const step = Math.max(1, Math.floor(points.length / max))
  return points.filter((_, i) => i % step === 0)
}
