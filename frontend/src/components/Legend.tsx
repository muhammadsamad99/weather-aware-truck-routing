import Accordion from '@mui/material/Accordion'
import AccordionDetails from '@mui/material/AccordionDetails'
import AccordionSummary from '@mui/material/AccordionSummary'
import Box from '@mui/material/Box'
import Typography from '@mui/material/Typography'
import { memo } from 'react'
import { LEVELS } from '../levels'
import { ExpandIcon } from './icons'

/** Risk colours with the thresholds behind them (backend/planner/risk.py; test_legend.py keeps them equal). */
const THRESHOLDS = [
  'wind < 25 mph · rain < 0.10 in/hr · snow < 0.5 in/hr',
  'wind 25 to < 35 · rain 0.10 to < 0.25 · snow 0.5 to < 1.0',
  'wind 35 to < 45 · rain 0.25 to < 0.50 · snow 1.0 to < 2.0',
  'wind 45 to < 55 · rain 0.50 to 1.00 · snow 2.0 to 3.0',
  'wind ≥ 55 · rain > 1.00 · snow > 3.0',
]

const COLUMNS = [
  { name: 'Wind', unit: 'mph' },
  { name: 'Rain', unit: 'in/hr' },
  { name: 'Snow', unit: 'in/hr' },
]
// "wind 25 to < 35 · rain 0.10 to < 0.25 · snow 0.5 to < 1.0" -> ["25 to < 35", "0.10 to < 0.25", "0.5 to < 1.0"]:
// the table shows each tested string in its three columns, with the names and units in the header.
const cells = (row: string) => row.split(' · ').map((part) => part.replace(/^(wind|rain|snow) /, '').replace(/ (mph|in\/hr)$/, ''))
const ROWS = LEVELS.map((level, i) => ({ level, values: cells(THRESHOLDS[i]) }))

const cellSx = { px: 0.75, py: 0.5, textAlign: 'left', verticalAlign: 'middle', whiteSpace: 'nowrap', typography: 'caption' } as const
const headSx = { ...cellSx, verticalAlign: 'top', fontWeight: 600 } as const
const tableSx = { borderCollapse: 'collapse', mx: -0.75, '& td': { color: 'text.secondary', fontVariantNumeric: 'tabular-nums' } }

function LevelName({ name, color }: { name: string; color: string }) {
  return (
    <Box component="span" sx={{ display: 'inline-flex', alignItems: 'center', gap: 1, fontWeight: 600 }}>
      <Box component="span" sx={{ width: 12, height: 12, flexShrink: 0, borderRadius: 0.5, bgcolor: color }} />
      {name}
    </Box>
  )
}

function ColumnHeads() {
  return COLUMNS.map((c) => (
    <Box component="th" scope="col" key={c.name} sx={headSx}>
      {c.name}
      <Box component="span" sx={{ display: 'block', color: 'text.secondary', fontWeight: 400 }}>
        {c.unit}
      </Box>
    </Box>
  ))
}

function Legend() {
  return (
    <Accordion slotProps={{ heading: { component: 'h2' } }}>
      <AccordionSummary expandIcon={<ExpandIcon />} id="legend-summary" aria-controls="legend-details">
        <Typography component="span" variant="body2" sx={{ fontWeight: 600 }}>
          Risk levels
        </Typography>
      </AccordionSummary>
      <AccordionDetails>
        {/* Wider panels: one row per level. Phones: each level's name on its own row, above its values, so the
            three value columns fit a 320 px screen. Only one of the two is displayed (and read out). */}
        <Box component="table" sx={{ ...tableSx, display: { xs: 'none', sm: 'table' } }}>
          <thead>
            <tr>
              <Box component="th" scope="col" sx={headSx}>
                Level
              </Box>
              <ColumnHeads />
            </tr>
          </thead>
          <tbody>
            {ROWS.map(({ level, values }) => (
              <tr key={level.name}>
                <Box component="th" scope="row" sx={cellSx}>
                  <LevelName name={level.name} color={level.color} />
                </Box>
                {values.map((v, j) => (
                  <Box component="td" key={COLUMNS[j].name} sx={cellSx}>
                    {v}
                  </Box>
                ))}
              </tr>
            ))}
          </tbody>
        </Box>
        <Box component="table" sx={{ ...tableSx, display: { xs: 'table', sm: 'none' } }}>
          <thead>
            <tr>
              <ColumnHeads />
            </tr>
          </thead>
          {ROWS.map(({ level, values }, i) => (
            <tbody key={level.name}>
              <tr>
                <Box component="th" scope="rowgroup" colSpan={3} sx={{ ...cellSx, pt: i ? 1.25 : 0.75, pb: 0.25 }}>
                  <LevelName name={level.name} color={level.color} />
                </Box>
              </tr>
              <tr>
                {values.map((v, j) => (
                  <Box component="td" key={COLUMNS[j].name} sx={{ ...cellSx, pt: 0 }}>
                    {v}
                  </Box>
                ))}
              </tr>
            </tbody>
          ))}
        </Box>
        <Typography variant="caption" component="p" color="text.secondary" sx={{ mt: 1 }}>
          A checkpoint takes its worst condition. Over 30,000 lb, Severe wind is No Travel; over 40,000 lb, High wind is
          Severe.
        </Typography>
      </AccordionDetails>
    </Accordion>
  )
}

export default memo(Legend)
