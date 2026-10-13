import { useEffect } from 'react'
import { formatDateTime } from '../format'

const PLAY_STEP_MS = 700

interface Props {
  start: string
  hours: number
  hour: number
  onHour: (hour: number) => void
  visible: boolean
  onVisible: (visible: boolean) => void
  playing: boolean
  onPlaying: (playing: boolean) => void
}

/** The 0-48 hour slider for the risk heatmap, with play/pause. */
export default function HeatmapControl({ start, hours, hour, onHour, visible, onVisible, playing, onPlaying }: Props) {
  useEffect(() => {
    if (!playing) return
    const timer = window.setInterval(() => onHour(hour >= hours ? 0 : hour + 1), PLAY_STEP_MS)
    return () => window.clearInterval(timer)
  }, [playing, hour, hours, onHour])

  const moment = new Date(Date.parse(start) + hour * 3_600_000)
  return (
    <div className="heat-control">
      <div className="heat-head">
        <label className="toggle">
          <input type="checkbox" checked={visible} onChange={(e) => onVisible(e.target.checked)} />
          Risk heatmap
        </label>
        <span className="heat-time" aria-live="polite">
          +{hour} h · {formatDateTime(moment)}
        </span>
      </div>
      <div className="heat-slider">
        <button
          type="button"
          className="play"
          onClick={() => onPlaying(!playing)}
          aria-label={playing ? 'Pause' : 'Play the next 48 hours'}
          title={playing ? 'Pause' : 'Play'}
        >
          {playing ? '❚❚' : '▶'}
        </button>
        <input
          type="range"
          min={0}
          max={hours}
          step={1}
          value={hour}
          aria-label="Hours after departure"
          aria-valuetext={`${hour} hours after departure, ${formatDateTime(moment)}`}
          onChange={(e) => {
            onPlaying(false)
            onHour(Number(e.target.value))
          }}
        />
      </div>
      <div className="heat-scale" aria-hidden="true">
        <span>departure</span>
        <span>+24 h</span>
        <span>+{hours} h</span>
      </div>
    </div>
  )
}
