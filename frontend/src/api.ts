import type { Place, Plan } from './types'

export class ApiError extends Error {
  fields: Record<string, string[]>

  constructor(message: string, fields: Record<string, string[]> = {}) {
    super(message)
    this.fields = fields
  }
}

async function request<T>(url: string, init?: RequestInit): Promise<T> {
  let response: Response
  try {
    response = await fetch(url, init)
  } catch (err) {
    if ((err as Error).name === 'AbortError') throw err
    throw new ApiError('Could not reach the server. Check your connection and try again.')
  }
  const body = await response.json().catch(() => null)
  if (!response.ok) {
    throw new ApiError(body?.error ?? `The server answered ${response.status}.`, body?.fields ?? {})
  }
  return body as T
}

export async function searchPlaces(query: string, signal: AbortSignal): Promise<Place[]> {
  const data = await request<{ results: Place[] }>(`/api/geocode?q=${encodeURIComponent(query)}`, { signal })
  return data.results
}

export interface PlanRequest {
  origin: string | Place
  destination: string | Place
  departure: string // ISO 8601 with a time zone
  load_lb: number
  interval_mi: number
}

export function planTrip(trip: PlanRequest, signal: AbortSignal): Promise<Plan> {
  return request<Plan>('/api/plan', {
    method: 'POST',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify(trip),
    signal,
  })
}
