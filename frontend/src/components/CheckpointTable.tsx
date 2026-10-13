import Accordion from '@mui/material/Accordion'
import AccordionDetails from '@mui/material/AccordionDetails'
import AccordionSummary from '@mui/material/AccordionSummary'
import Table from '@mui/material/Table'
import TableBody from '@mui/material/TableBody'
import TableCell from '@mui/material/TableCell'
import TableContainer from '@mui/material/TableContainer'
import TableHead from '@mui/material/TableHead'
import TableRow from '@mui/material/TableRow'
import Typography from '@mui/material/Typography'
import { memo } from 'react'
import { formatDayTime, timeZoneLabel } from '../format'
import type { PlannedRoute } from '../types'
import { ExpandIcon } from './icons'
import RiskChip from './RiskChip'

interface Props {
  route: PlannedRoute
  intervalMi: number
  onFocus?: (index: number) => void // shows the checkpoint on the map; absent when there is no map
}

/** Every checkpoint on the selected route: where, when the truck is there, the forecast then, and the level. */
function CheckpointTable({ route, intervalMi, onFocus }: Props) {
  const zone = timeZoneLabel(route.checkpoints[0]?.eta ?? new Date().toISOString())
  return (
    <Accordion defaultExpanded className="checkpoints" slotProps={{ heading: { component: 'h2' } }}>
      <AccordionSummary expandIcon={<ExpandIcon />}>
        <Typography component="span" variant="body2" sx={{ fontWeight: 600 }}>
          {route.name}: {route.checkpoints.length} checkpoints, every {intervalMi} mi
        </Typography>
      </AccordionSummary>
      <AccordionDetails sx={{ p: 0 }}>
        <TableContainer sx={{ maxHeight: 320, borderTop: 1, borderColor: 'divider' }}>
          <Table size="small" stickyHeader sx={{ '& td, & th': { whiteSpace: 'nowrap', fontVariantNumeric: 'tabular-nums' } }}>
            <TableHead>
              <TableRow>
                <TableCell align="right">Mile</TableCell>
                <TableCell>Arrives ({zone})</TableCell>
                <TableCell align="right" title="Wind speed at 10 m, mph">
                  Wind
                </TableCell>
                <TableCell align="right" title="Rain, inches per hour">
                  Rain
                </TableCell>
                <TableCell align="right" title="Snowfall, inches per hour">
                  Snow
                </TableCell>
                <TableCell>Risk</TableCell>
              </TableRow>
            </TableHead>
            <TableBody>
              {route.checkpoints.map((c) => (
                <TableRow
                  key={c.index}
                  hover={Boolean(onFocus)}
                  className={onFocus ? 'clickable' : undefined}
                  tabIndex={onFocus ? 0 : undefined}
                  onClick={onFocus ? () => onFocus(c.index) : undefined}
                  onKeyDown={
                    onFocus
                      ? (e) => {
                          if (e.key === 'Enter' || e.key === ' ') {
                            e.preventDefault()
                            onFocus(c.index)
                          }
                        }
                      : undefined
                  }
                  title={c.reasons.join('; ') || undefined}
                  sx={onFocus ? { cursor: 'pointer', '&:focus-visible': { outline: 2, outlineColor: 'primary.main', outlineOffset: -2 } } : undefined}
                >
                  <TableCell align="right">{c.mile.toFixed(0)}</TableCell>
                  <TableCell>{formatDayTime(c.eta)}</TableCell>
                  <TableCell align="right">{c.wind_mph.toFixed(0)}</TableCell>
                  <TableCell align="right">{c.rain_in_hr.toFixed(2)}</TableCell>
                  <TableCell align="right">{c.snow_in_hr.toFixed(2)}</TableCell>
                  <TableCell>
                    <RiskChip level={c.level} />
                  </TableCell>
                </TableRow>
              ))}
            </TableBody>
          </Table>
        </TableContainer>
      </AccordionDetails>
    </Accordion>
  )
}

export default memo(CheckpointTable)
