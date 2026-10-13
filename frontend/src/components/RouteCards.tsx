import Box from '@mui/material/Box'
import Card from '@mui/material/Card'
import CardActionArea from '@mui/material/CardActionArea'
import Chip from '@mui/material/Chip'
import Stack from '@mui/material/Stack'
import Tooltip from '@mui/material/Tooltip'
import Typography from '@mui/material/Typography'
import { memo } from 'react'
import { LEVELS } from '../levels'
import { formatDateTime, formatDuration, formatMiles } from '../format'
import type { PlannedRoute } from '../types'

interface Props {
  routes: PlannedRoute[]
  selected: string
  onSelect: (name: string) => void
}

/** One card per route, best first: distance, time, arrival and the miles at each risk level. */
function RouteCards({ routes, selected, onSelect }: Props) {
  const ordered = [...routes].sort((a, b) => a.rank - b.rank)
  return (
    <Stack component="ol" spacing={1} sx={{ listStyle: 'none', m: 0, p: 0 }}>
      {ordered.map((r) => {
        const isSelected = r.name === selected
        return (
          <li key={r.name}>
            <Card
              variant="outlined"
              sx={{
                borderColor: isSelected ? 'primary.main' : 'divider',
                boxShadow: isSelected ? (t) => `inset 0 0 0 1px ${t.palette.primary.main}` : 'none',
              }}
            >
              {/* A button holds only phrasing content, so the card's parts are spans. */}
              <CardActionArea
                className="route-card"
                aria-pressed={isSelected}
                aria-label={cardLabel(r)}
                onClick={() => onSelect(r.name)}
                sx={{ p: 1.5, display: 'block' }}
              >
                <Box component="span" sx={{ display: 'flex', alignItems: 'center', gap: 1 }}>
                  <Typography component="span" sx={{ fontWeight: 700, color: 'text.secondary' }}>
                    #{r.rank}
                  </Typography>
                  <Typography component="span" sx={{ fontWeight: 600 }}>
                    {r.name}
                  </Typography>
                  {r.recommended && (
                    <Chip component="span" size="small" color="primary" label="Recommended" sx={{ ml: 'auto' }} />
                  )}
                </Box>
                <Box component="span" sx={{ display: 'flex', flexWrap: 'wrap', columnGap: 1.5, mt: 0.5 }}>
                  <Typography component="span" variant="body2">
                    {formatMiles(r.miles)}
                  </Typography>
                  <Typography component="span" variant="body2">
                    {formatDuration(r.seconds)}
                  </Typography>
                  <Typography component="span" variant="body2" color="text.secondary">
                    arrives {formatDateTime(r.arrival)}
                  </Typography>
                </Box>
                <RiskBar route={r} />
                <Box
                  component="span"
                  sx={{ display: 'grid', gridTemplateColumns: 'repeat(4, 1fr)', mt: 0.75, fontVariantNumeric: 'tabular-nums' }}
                >
                  <Figure label="No Travel" value={formatMiles(r.risk.no_travel_miles)} />
                  <Figure label="Severe" value={formatMiles(r.risk.severe_miles)} />
                  <Figure label="High" value={formatMiles(r.risk.high_miles)} />
                  <Figure label="Avg risk" value={r.risk.average.toFixed(2)} />
                </Box>
              </CardActionArea>
            </Card>
          </li>
        )
      })}
    </Stack>
  )
}

export default memo(RouteCards)

function Figure({ label, value }: { label: string; value: string }) {
  return (
    <Box component="span" sx={{ display: 'block' }}>
      <Typography component="span" variant="caption" color="text.secondary" sx={{ display: 'block' }}>
        {label}
      </Typography>
      <Typography component="span" variant="body2" sx={{ display: 'block', fontWeight: 600 }}>
        {value}
      </Typography>
    </Box>
  )
}

function RiskBar({ route }: { route: PlannedRoute }) {
  const total = Object.values(route.risk.miles_by_level).reduce((a, b) => a + b, 0)
  const parts = LEVELS.map((l) => ({ ...l, miles: route.risk.miles_by_level[l.name] ?? 0 })).filter((p) => p.miles > 0)
  const label = parts.map((p) => `${p.name} ${Math.round(p.miles)} mi`).join(', ')
  return (
    <Box
      component="span"
      role="img"
      aria-label={`Miles by risk level: ${label}`}
      sx={{ display: 'flex', height: 8, mt: 1, borderRadius: 1, overflow: 'hidden', bgcolor: 'grey.100' }}
    >
      {parts.map((p) => (
        <Tooltip key={p.name} title={`${p.name}: ${Math.round(p.miles)} mi`} disableInteractive>
          {/* width and colour vary per route, so they are inline styles rather than generated classes */}
          <span style={{ width: `${(p.miles / total) * 100}%`, background: p.color }} />
        </Tooltip>
      ))}
    </Box>
  )
}

/** The card as one sentence for screen readers; the card's own text runs together without its layout. */
function cardLabel(r: PlannedRoute): string {
  const risk = r.risk
  return (
    `${r.name}, rank ${r.rank}${r.recommended ? ', recommended' : ''}: ${formatMiles(r.miles)}, ` +
    `${formatDuration(r.seconds)}, arrives ${formatDateTime(r.arrival)}. No Travel ${formatMiles(risk.no_travel_miles)}, ` +
    `Severe ${formatMiles(risk.severe_miles)}, High ${formatMiles(risk.high_miles)}, ` +
    `average risk ${risk.average.toFixed(2)}.`
  )
}
