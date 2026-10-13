import type { Checkpoint, PlannedRoute } from './types'

const EARTH_RADIUS_MI = 3958.7613

export function haversineMi([lon1, lat1]: [number, number], [lon2, lat2]: [number, number]): number {
  const rad = Math.PI / 180
  const dLat = (lat2 - lat1) * rad
  const dLon = (lon2 - lon1) * rad
  const a = Math.sin(dLat / 2) ** 2 + Math.cos(lat1 * rad) * Math.cos(lat2 * rad) * Math.sin(dLon / 2) ** 2
  return 2 * EARTH_RADIUS_MI * Math.asin(Math.min(1, Math.sqrt(a)))
}

/**
 * Where the truck is at `moment` on this route, or null before departure or after arrival.
 * The mile is interpolated between the checkpoints' ETAs (the truck's own timetable), then placed
 * on the route's geometry at that mile.
 */
export function positionAt(route: PlannedRoute, moment: Date): { lonLat: [number, number]; mile: number } | null {
  const t = moment.getTime()
  const cps = route.checkpoints
  const times = cps.map((c) => Date.parse(c.eta))
  if (cps.length === 0 || t < times[0] || t > times[times.length - 1]) return null
  let i = 0
  while (i < cps.length - 2 && t > times[i + 1]) i++
  const span = times[i + 1] - times[i]
  const f = span > 0 ? (t - times[i]) / span : 0
  const mile = cps.length > 1 ? cps[i].mile + f * (cps[i + 1].mile - cps[i].mile) : cps[0].mile
  return { lonLat: pointAtMile(route.geometry, mile, cps), mile }
}

function pointAtMile(geometry: [number, number][], mile: number, cps: Checkpoint[]): [number, number] {
  // The geometry is thinned, so its own length is a touch shorter than the route's; scale to match.
  const lengths = [0]
  for (let k = 1; k < geometry.length; k++) lengths.push(lengths[k - 1] + haversineMi(geometry[k - 1], geometry[k]))
  const total = lengths[lengths.length - 1]
  const routeMiles = cps[cps.length - 1].mile || total
  const target = total > 0 ? (mile / routeMiles) * total : 0
  let k = 1
  while (k < geometry.length - 1 && lengths[k] < target) k++
  const seg = lengths[k] - lengths[k - 1]
  const f = seg > 0 ? Math.min(1, Math.max(0, (target - lengths[k - 1]) / seg)) : 0
  const [a, b] = [geometry[k - 1], geometry[k] ?? geometry[k - 1]]
  return [a[0] + f * (b[0] - a[0]), a[1] + f * (b[1] - a[1])]
}

export function bounds(routes: PlannedRoute[]): [[number, number], [number, number]] {
  let [w, s, e, n] = [180, 90, -180, -90]
  for (const r of routes) {
    for (const [lon, lat] of r.geometry) {
      w = Math.min(w, lon)
      e = Math.max(e, lon)
      s = Math.min(s, lat)
      n = Math.max(n, lat)
    }
  }
  return [
    [w, s],
    [e, n],
  ]
}
