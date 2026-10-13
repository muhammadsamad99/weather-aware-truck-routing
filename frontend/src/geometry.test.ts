import { describe, expect, it } from 'vitest'
import { positionAt } from './geometry'
import type { PlannedRoute } from './types'

const route = {
  geometry: [
    [-90, 40],
    [-90, 41],
  ],
  checkpoints: [
    { mile: 0, eta: '2026-10-15T12:00:00Z' },
    { mile: 69, eta: '2026-10-15T13:00:00Z' },
  ],
} as unknown as PlannedRoute

describe('positionAt', () => {
  it('is null before departure and after arrival', () => {
    expect(positionAt(route, new Date('2026-10-15T11:59:00Z'))).toBeNull()
    expect(positionAt(route, new Date('2026-10-15T13:01:00Z'))).toBeNull()
  })

  it('places the truck by its timetable along the route', () => {
    const halfway = positionAt(route, new Date('2026-10-15T12:30:00Z'))!
    expect(halfway.mile).toBeCloseTo(34.5)
    expect(halfway.lonLat[0]).toBeCloseTo(-90)
    expect(halfway.lonLat[1]).toBeCloseTo(40.5, 2)
  })
})
