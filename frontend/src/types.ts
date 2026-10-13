/** The shapes returned by the Django API (backend/planner/service.py). */

export type LevelName = 'Low' | 'Moderate' | 'High' | 'Severe' | 'No Travel'

export interface Place {
  label: string
  lat: number
  lon: number
}

export interface Checkpoint {
  index: number
  mile: number
  lat: number
  lon: number
  eta: string
  wind_mph: number
  rain_in_hr: number
  snow_in_hr: number
  level: number
  level_name: LevelName
  reasons: string[]
}

export interface RouteRisk {
  miles_by_level: Record<LevelName, number>
  average: number
  severe_miles: number
  high_miles: number
  no_travel_miles: number
}

export interface PlannedRoute {
  name: string
  provider: string
  miles: number
  seconds: number
  arrival: string
  geometry: [number, number][] // [lon, lat]
  checkpoints: Checkpoint[]
  risk: RouteRisk
  rank: number
  recommended: boolean
}

export interface Heatmap {
  start: string
  hours: number
  step_deg: number
  points: [number, number][] // [lon, lat]
  frames: (number | null)[][] // frames[hour][point] = risk level, or null where the forecast has no value
}

export interface Plan {
  origin: Place
  destination: Place
  departure: string
  load_lb: number
  interval_mi: number
  provider: string
  routes: PlannedRoute[]
  recommended: string
  reason: string
  levels: LevelName[]
  weather_grid_deg: number // 0.1 normally; wider on long trips, to stay within the forecast service's limits
  heatmap: Heatmap
}

/** A place as typed text, or as a picked suggestion with coordinates. */
export type PlaceInputValue = { text: string; place: Place | null }

export interface TripForm {
  origin: PlaceInputValue
  destination: PlaceInputValue
  departure: string // datetime-local value, in the browser's time zone
  loadLb: string
  intervalMi: 10 | 25 | 50
}
