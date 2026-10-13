import { levelColor } from '../levels'
import { formatDayTime, timeZoneLabel } from '../format'
import type { PlannedRoute } from '../types'

interface Props {
  route: PlannedRoute
  intervalMi: number
  onFocus: (index: number) => void
}

/** Every checkpoint on the selected route: where, when the truck is there, the forecast then, and the level. */
export default function CheckpointTable({ route, intervalMi, onFocus }: Props) {
  return (
    <details className="checkpoints" open>
      <summary>
        {route.name}: {route.checkpoints.length} checkpoints, every {intervalMi} mi
      </summary>
      <div className="table-wrap">
        <table>
          <thead>
            <tr>
              <th scope="col">Mile</th>
              <th scope="col">Arrives ({timeZoneLabel(route.checkpoints[0]?.eta ?? new Date().toISOString())})</th>
              <th scope="col" title="Wind speed at 10 m, mph">Wind</th>
              <th scope="col" title="Rain, inches per hour">Rain</th>
              <th scope="col" title="Snowfall, inches per hour">Snow</th>
              <th scope="col">Risk</th>
            </tr>
          </thead>
          <tbody>
            {route.checkpoints.map((c) => (
              <tr key={c.index} onClick={() => onFocus(c.index)} title={c.reasons.join('; ') || undefined}>
                <td>{c.mile.toFixed(0)}</td>
                <td>{formatDayTime(c.eta)}</td>
                <td>{c.wind_mph.toFixed(0)}</td>
                <td>{c.rain_in_hr.toFixed(2)}</td>
                <td>{c.snow_in_hr.toFixed(2)}</td>
                <td>
                  <span className="level-chip" style={{ background: levelColor(c.level) }}>
                    {c.level_name}
                  </span>
                </td>
              </tr>
            ))}
          </tbody>
        </table>
      </div>
    </details>
  )
}
