import Box from '@mui/material/Box'
import Typography from '@mui/material/Typography'
import { Component, type ReactNode } from 'react'
import { mapProblem, type MapProblem } from '../mapProblem'

/** Shown in place of the map when it can't be drawn; the panel still has every result. */
export function MapUnavailable({ problem }: { problem: MapProblem }) {
  return (
    <Box
      className="map-unavailable"
      role="note"
      sx={{
        position: 'absolute',
        inset: 0,
        display: 'flex',
        flexDirection: 'column',
        justifyContent: 'center',
        gap: 1,
        px: { xs: 3, md: '12%' },
        bgcolor: 'grey.50',
        '& p': { maxWidth: '60ch' },
      }}
    >
      {problem === 'webgl' ? (
        <>
          <Typography variant="subtitle1" component="strong" sx={{ fontWeight: 700 }}>
            The map can't be drawn in this browser.
          </Typography>
          <Typography variant="body2" color="text.secondary">
            It needs WebGL, which this browser isn't providing (common on a computer without a graphics card, or with
            hardware acceleration off). The routes, checkpoints and recommendation are all in the panel.
          </Typography>
          <Typography variant="body2" color="text.secondary">
            To see the map, turn on hardware acceleration (in Chrome: Settings → System → Use graphics acceleration when
            available) and restart the browser, or open the app in another browser.
          </Typography>
        </>
      ) : (
        <>
          <Typography variant="subtitle1" component="strong" sx={{ fontWeight: 700 }}>
            The map stopped working.
          </Typography>
          <Typography variant="body2" color="text.secondary">
            The routes, checkpoints and recommendation are all in the panel. Reloading the page may bring the map back.
          </Typography>
        </>
      )}
    </Box>
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
