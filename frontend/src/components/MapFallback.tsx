import { Component, type ReactNode } from 'react'
import { mapProblem, type MapProblem } from '../mapProblem'

/** Shown in place of the map when it can't be drawn; the panel still has every result. */
export function MapUnavailable({ problem }: { problem: MapProblem }) {
  if (problem === 'webgl') {
    return (
      <div className="map-unavailable" role="note">
        <strong>The map can't be drawn in this browser.</strong>
        <p>
          It needs WebGL, which this browser isn't providing (common on a computer without a graphics card, or with
          hardware acceleration off). The routes, checkpoints and recommendation are all in the panel.
        </p>
        <p>
          To see the map, turn on hardware acceleration (in Chrome: Settings → System → Use graphics acceleration when
          available) and restart the browser, or open the app in another browser.
        </p>
      </div>
    )
  }
  return (
    <div className="map-unavailable" role="note">
      <strong>The map stopped working.</strong>
      <p>The routes, checkpoints and recommendation are all in the panel. Reloading the page may bring the map back.</p>
    </div>
  )
}

interface BoundaryProps {
  children: ReactNode
  onError: () => void
}

/** Keeps a map failure to the map: the rest of the app stays usable. */
export class MapBoundary extends Component<BoundaryProps, { problem: MapProblem | null }> {
  state: { problem: MapProblem | null } = { problem: null }

  static getDerivedStateFromError(error: unknown) {
    return { problem: mapProblem(error) }
  }

  componentDidCatch(error: unknown) {
    console.warn('The map stopped working.', error)
    this.props.onError()
  }

  render() {
    return this.state.problem ? <MapUnavailable problem={this.state.problem} /> : this.props.children
  }
}
