import type { Place, Plan } from './types'

export class ApiError extends Error {
  fields: Record<string, string[]>

  constructor(message: string, fields: Record<string, string[]> = {}) {
    super(message)
    this.fields = fields
  }
}

const UNREADABLE = 'The server sent an answer that could not be read. Try again.'

async function request<T>(url: string, init?: RequestInit): Promise<T> {
  let response: Response
  try {
    response = await fetch(url, init)
  } catch (err) {
    if ((err as Error).name === 'AbortError') throw err
    throw new ApiError('Could not reach the server. Check your connection and try again.')
  }
  let body: { error?: string; fields?: Record<string, string[]> } | null = null
  try {
    body = await response.json()
  } catch (err) {
    if ((err as Error).name === 'AbortError') throw err // a newer request replaced this one
  }
  if (!response.ok) {
    throw new ApiError(body?.error ?? `The server answered ${response.status}.`, body?.fields ?? {})
  }
  if (body === null || typeof body !== 'object') throw new ApiError(UNREADABLE)
  return body as T
}


export async function searchPlaces(query: string, signal: AbortSignal): Promise<Place[]> {
  const data = await request<{ results?: unknown }>(`/api/geocode?q=${encodeURIComponent(query)}`, { signal })
  return Array.isArray(data.results) ? (data.results as Place[]) : []
}

export interface PlanRequest {
  origin: string | Place
  destination: string | Place
  departure: string // ISO 8601 with a time zone
  load_lb: number
  interval_mi: number
}

export async function planTrip(trip: PlanRequest, signal: AbortSignal): Promise<Plan> {
  const plan = await request<Plan>('/api/plan', {
    method: 'POST',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify(trip),
    signal,
  })
  if (!Array.isArray(plan.routes) || typeof plan.recommended !== 'string') throw new ApiError(UNREADABLE)
  return plan
}
