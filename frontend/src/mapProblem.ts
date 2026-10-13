/** Why the map isn't showing: the browser has no WebGL, or something else broke. */
export type MapProblem = 'webgl' | 'error'

export function mapProblem(error: unknown): MapProblem {
  const message = error instanceof Error ? error.message : String(error)
  return /webgl/i.test(message) ? 'webgl' : 'error'
}
