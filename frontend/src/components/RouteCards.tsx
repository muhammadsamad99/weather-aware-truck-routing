import { LEVELS } from '../levels'
import { formatDateTime, formatDuration, formatMiles } from '../format'
import type { PlannedRoute } from '../types'

interface Props {
  routes: PlannedRoute[]
  selected: string
  onSelect: (name: string) => void
}

/** One card per route, best first: distance, time, arrival and the miles at each risk level. */
export default function RouteCards({ routes, selected, onSelect }: Props) {
  const ordered = [...routes].sort((a, b) => a.rank - b.rank)
  return (
    <ol className="route-cards">
      {ordered.map((r) => (
        <li key={r.name}>
          <button
            type="button"
            className={`route-card${r.name === selected ? ' selected' : ''}${r.recommended ? ' recommended' : ''}`}
            aria-pressed={r.name === selected}
            onClick={() => onSelect(r.name)}
          >
            <div className="card-head">
              <span className="rank">#{r.rank}</span>
              <span className="name">{r.name}</span>
              {r.recommended && <span className="badge">Recommended</span>}
            </div>
            <div className="card-stats">
              <span>{formatMiles(r.miles)}</span>
              <span>{formatDuration(r.seconds)}</span>
              <span title="Arrival">arrives {formatDateTime(r.arrival)}</span>
            </div>
            <RiskBar route={r} />
            <dl className="card-risk">
              <div>
                <dt>No Travel</dt>
                <dd>{formatMiles(r.risk.no_travel_miles)}</dd>
              </div>
              <div>
                <dt>Severe</dt>
                <dd>{formatMiles(r.risk.severe_miles)}</dd>
              </div>
              <div>
                <dt>High</dt>
                <dd>{formatMiles(r.risk.high_miles)}</dd>
              </div>
              <div>
                <dt>Avg risk</dt>
                <dd>{r.risk.average.toFixed(2)}</dd>
              </div>
            </dl>
          </button>
        </li>
      ))}
    </ol>
  )
}

function RiskBar({ route }: { route: PlannedRoute }) {
  const total = Object.values(route.risk.miles_by_level).reduce((a, b) => a + b, 0)
  const parts = LEVELS.map((l) => ({ ...l, miles: route.risk.miles_by_level[l.name] ?? 0 })).filter((p) => p.miles > 0)
  const label = parts.map((p) => `${p.name} ${Math.round(p.miles)} mi`).join(', ')
  return (
    <div className="risk-bar" role="img" aria-label={`Miles by risk level: ${label}`} title={label}>
      {parts.map((p) => (
        <span key={p.name} style={{ width: `${(p.miles / total) * 100}%`, background: p.color }} />
      ))}
    </div>
  )
}
