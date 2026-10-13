/** Display helpers. Times are shown in the browser's own time zone, with its abbreviation. */

const dateTime = new Intl.DateTimeFormat(undefined, {
  weekday: 'short',
  month: 'short',
  day: 'numeric',
  hour: 'numeric',
  minute: '2-digit',
  timeZoneName: 'short',
})

export const formatDateTime = (iso: string | Date) => dateTime.format(typeof iso === 'string' ? new Date(iso) : iso)

const dayTime = new Intl.DateTimeFormat(undefined, { weekday: 'short', hour: 'numeric', minute: '2-digit' })

/** "Wed 3:14 AM": for tables, where the time zone is given once in the header. */
export const formatDayTime = (iso: string) => dayTime.format(new Date(iso))

/** The browser's time zone abbreviation at a moment, such as "CDT" or "GMT+5". */
export function timeZoneLabel(iso: string): string {
  const parts = new Intl.DateTimeFormat(undefined, { timeZoneName: 'short' }).formatToParts(new Date(iso))
  return parts.find((p) => p.type === 'timeZoneName')?.value ?? ''
}

export function formatDuration(seconds: number): string {
  const minutes = Math.round(seconds / 60)
  return `${Math.floor(minutes / 60)} h ${String(minutes % 60).padStart(2, '0')} min`
}

export const formatMiles = (miles: number) => `${miles.toLocaleString(undefined, { maximumFractionDigits: 0 })} mi`

export const formatLoad = (lb: number) => `${lb.toLocaleString()} lb`

/** A `datetime-local` value for the next whole hour, in local time. */
export function nextHourLocal(now = new Date()): string {
  const d = new Date(now)
  d.setMinutes(0, 0, 0)
  d.setHours(d.getHours() + 1)
  return toLocalInput(d)
}

export function toLocalInput(d: Date): string {
  const pad = (n: number) => String(n).padStart(2, '0')
  return `${d.getFullYear()}-${pad(d.getMonth() + 1)}-${pad(d.getDate())}T${pad(d.getHours())}:${pad(d.getMinutes())}`
}
