import { LEVELS } from '../levels'

/** Risk colours with the thresholds behind them (backend/planner/risk.py). */
const THRESHOLDS = [
  'wind < 25 mph · rain < 0.10 in/hr · snow < 0.5 in/hr',
  'wind 25 to < 35 · rain 0.10 to < 0.25 · snow 0.5 to < 1.0',
  'wind 35 to < 45 · rain 0.25 to < 0.50 · snow 1.0 to < 2.0',
  'wind 45 to < 55 · rain 0.50 to 1.00 · snow 2.0 to 3.0',
  'wind ≥ 55 · rain > 1.00 · snow > 3.0',
]

export default function Legend() {
  return (
    <details className="legend">
      <summary>Risk levels</summary>
      <ul>
        {LEVELS.map((l, i) => (
          <li key={l.name}>
            <span className="swatch" style={{ background: l.color }} />
            <strong>{l.name}</strong>
            <span className="threshold">{THRESHOLDS[i]}</span>
          </li>
        ))}
      </ul>
      <p className="note">
        A checkpoint takes its worst condition. Over 30,000 lb, Severe wind is No Travel; over 40,000 lb, High wind is
        Severe.
      </p>
    </details>
  )
}
