import Accordion from '@mui/material/Accordion'
import AccordionDetails from '@mui/material/AccordionDetails'
import AccordionSummary from '@mui/material/AccordionSummary'
import Box from '@mui/material/Box'
import Stack from '@mui/material/Stack'
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

function Legend() {
  return (
    <Accordion slotProps={{ heading: { component: 'h2' } }}>
      <AccordionSummary expandIcon={<ExpandIcon />}>
        <Typography component="span" variant="body2" sx={{ fontWeight: 600 }}>
          Risk levels
        </Typography>
      </AccordionSummary>
      <AccordionDetails>
        <Stack component="ul" spacing={0.75} sx={{ listStyle: 'none', m: 0, p: 0 }}>
          {LEVELS.map((l, i) => (
            <Box component="li" key={l.name} sx={{ display: 'grid', gridTemplateColumns: '14px 76px 1fr', gap: 1, alignItems: 'baseline' }}>
              <Box sx={{ width: 14, height: 14, borderRadius: 0.5, bgcolor: l.color, alignSelf: 'center' }} />
              <Typography variant="body2" sx={{ fontWeight: 600 }}>
                {l.name}
              </Typography>
              <Typography variant="caption" color="text.secondary">
                {THRESHOLDS[i]}
              </Typography>
            </Box>
          ))}
        </Stack>
        <Typography variant="caption" component="p" color="text.secondary" sx={{ mt: 1 }}>
          A checkpoint takes its worst condition. Over 30,000 lb, Severe wind is No Travel; over 40,000 lb, High wind is
          Severe.
        </Typography>
      </AccordionDetails>
    </Accordion>
  )
}

export default memo(Legend)
