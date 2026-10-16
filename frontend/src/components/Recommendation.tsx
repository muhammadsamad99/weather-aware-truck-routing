import Alert from '@mui/material/Alert'
import Paper from '@mui/material/Paper'
import Typography from '@mui/material/Typography'
import { alpha } from '@mui/material/styles'
import { formatDateTime, formatLoad } from '../format'
import { brand } from '../theme'
import type { Plan } from '../types'

/** The recommended route, why, what it trades for time, and the trip it was planned for. */
export default function Recommendation({ plan }: { plan: Plan }) {
  return (
    <Paper
      variant="outlined"
      className="recommendation"
      sx={{ p: 2, bgcolor: alpha(brand.primary, 0.05), borderColor: alpha(brand.primary, 0.3) }}
    >
      <Typography variant="h2" component="p" sx={{ fontWeight: 400 }}>
        Recommended: <strong>{plan.recommended}</strong>
      </Typography>
      <Typography variant="body2" sx={{ mt: 0.75 }}>
        {plan.reason}
      </Typography>
      {plan.tradeoff && (
        <Typography variant="body2" sx={{ mt: 0.5 }}>
          {plan.tradeoff}
        </Typography>
      )}
      <Typography variant="caption" component="p" color="text.secondary" sx={{ mt: 1 }}>
        {plan.origin.label} → {plan.destination.label}
        <br />
        Leaves {formatDateTime(plan.departure)} · {formatLoad(plan.load_lb)} · checked every {plan.interval_mi} mi
      </Typography>
      {plan.provider === 'osrm' && (
        <Alert severity="warning" sx={{ mt: 1 }}>
          <strong>Backup routes from OSRM</strong>, because the truck routing service didn't answer. They follow car
          roads and car driving times; the truck's weight isn't considered.
        </Alert>
      )}
      {plan.weather_source === 'met-norway' && (
        <Typography variant="caption" component="p" color="text.secondary" sx={{ mt: 0.5 }}>
          <strong>Backup forecast from MET Norway</strong>, because the main weather service didn't answer. Snow is
          estimated from the type of precipitation, and the heatmap covers only the hours MET Norway forecasts hour by
          hour.
        </Typography>
      )}
      {plan.weather_grid_deg > 0.1 && (
        <Typography variant="caption" component="p" color="text.secondary" sx={{ mt: 0.5 }}>
          A long trip: the forecast is read on a {plan.weather_grid_deg}° grid (about{' '}
          {Math.round(plan.weather_grid_deg * 69)} mi) to stay within the weather service's limits.
        </Typography>
      )}
    </Paper>
  )
}
