import { memo, useState } from 'react'
import type { Plan } from '../types'
import HeatmapControl from './HeatmapControl'
import { MapBoundary } from './MapFallback'
import MapView, { type Focus } from './MapView'

interface Props {
  plan: Plan | null
  selected: string
  focus: Focus | null
  onSelectRoute: (name: string) => void
  mapWorks: boolean
  onMapFailed: () => void
}

/**
 * The map and its heatmap control. The heatmap's hour, playback and visibility live here, so moving the
 * slider or playing it re-renders only the map, not the panel and its checkpoint table.
 */
function MapPane({ plan, selected, focus, onSelectRoute, mapWorks, onMapFailed }: Props) {
  const [hour, setHour] = useState(0)
  const [playing, setPlaying] = useState(false)
  const [showHeatmap, setShowHeatmap] = useState(true)
  const [shownPlan, setShownPlan] = useState(plan)
  if (plan !== shownPlan) {
    // a new plan starts at departure, paused (adjusting state during render, so the map isn't remounted)
    setShownPlan(plan)
    setHour(0)
    setPlaying(false)
  }

  return (
    <>
      <MapBoundary onError={onMapFailed}>
        <MapView
          plan={plan}
          selected={selected}
          hour={hour}
          showHeatmap={showHeatmap}
          focus={focus}
          onSelectRoute={onSelectRoute}
          onUnavailable={onMapFailed}
        />
      </MapBoundary>
      {plan && mapWorks && (
        <HeatmapControl
          start={plan.heatmap.start}
          hours={plan.heatmap.hours}
          spacingMi={gridSpacingMi(plan)}
          hour={hour}
          onHour={setHour}
          visible={showHeatmap}
          onVisible={setShowHeatmap}
          playing={playing}
          onPlaying={setPlaying}
        />
      )}
    </>
  )
}

export default memo(MapPane)

/** The heatmap grid's spacing in miles: [east-west, north-south] (a degree of longitude shrinks with latitude). */
function gridSpacingMi(plan: Plan): [number, number] {
  const lats = plan.heatmap.points.map((p) => p[1])
  const midLat = lats.length ? (Math.min(...lats) + Math.max(...lats)) / 2 : 39
  const northSouth = plan.heatmap.step_deg * 69
  return [Math.round(northSouth * Math.cos((midLat * Math.PI) / 180)), Math.round(northSouth)]
}
