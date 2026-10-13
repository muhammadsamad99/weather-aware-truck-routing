import FormControlLabel from '@mui/material/FormControlLabel'
import IconButton from '@mui/material/IconButton'
import Paper from '@mui/material/Paper'
import Slider from '@mui/material/Slider'
import Stack from '@mui/material/Stack'
import Switch from '@mui/material/Switch'
import Typography from '@mui/material/Typography'
import { type Dispatch, type SetStateAction, useEffect } from 'react'
import { formatDateTime } from '../format'
import { PauseIcon, PlayIcon } from './icons'

const PLAY_STEP_MS = 700

interface Props {
  start: string
  hours: number
  spacingMi: [number, number] // east-west, north-south
  hour: number
  onHour: Dispatch<SetStateAction<number>>
  visible: boolean
  onVisible: (visible: boolean) => void
  playing: boolean
  onPlaying: (playing: boolean) => void
}

/** The 0-48 hour slider for the risk heatmap, with play/pause. */
export default function HeatmapControl(props: Props) {
  const { start, hours, spacingMi, hour, onHour, visible, onVisible, playing, onPlaying } = props

  useEffect(() => {
    if (!playing) return
    const timer = window.setInterval(() => onHour((h) => (h >= hours ? 0 : h + 1)), PLAY_STEP_MS)
    return () => window.clearInterval(timer)
  }, [playing, hours, onHour])

  const moment = new Date(Date.parse(start) + hour * 3_600_000)
  const spacing = spacingMi[0] === spacingMi[1] ? `${spacingMi[0]}` : `${spacingMi[0]}–${spacingMi[1]}`
  return (
    <Paper
      elevation={4}
      className="heat-control"
      sx={{
        position: 'absolute',
        left: '50%',
        transform: 'translateX(-50%)',
        bottom: { xs: 36, md: 28 },
        width: 'min(560px, calc(100% - 16px))',
        px: 2,
        pt: 1,
        pb: 0.5,
        zIndex: 2,
      }}
    >
      <Stack direction="row" sx={{ alignItems: 'center', justifyContent: 'space-between', flexWrap: 'wrap', columnGap: 1 }}>
        <Stack direction="row" sx={{ alignItems: 'baseline', columnGap: 1 }}>
          <FormControlLabel
            control={<Switch size="small" checked={visible} onChange={(e) => onVisible(e.target.checked)} />}
            label={<Typography variant="body2" sx={{ fontWeight: 600 }}>Risk heatmap</Typography>}
            sx={{ mr: 0 }}
          />
          <Typography
            variant="caption"
            color="text.secondary"
            title="The heatmap is coarser than the checkpoints, which use the forecast where the truck is"
          >
            points {spacing} mi apart
          </Typography>
        </Stack>
        {/* not a live region: during playback it changes every 0.7 s; the slider's value text carries it */}
        <Typography variant="body2" sx={{ fontVariantNumeric: 'tabular-nums', minWidth: '15ch', textAlign: 'right' }}>
          +{hour} h · {formatDateTime(moment)}
        </Typography>
      </Stack>
      <Stack direction="row" spacing={1.5} sx={{ alignItems: 'center' }}>
        <IconButton
          size="small"
          onClick={() => onPlaying(!playing)}
          aria-label={playing ? 'Pause' : 'Play the next 48 hours'}
          title={playing ? 'Pause' : 'Play'}
          sx={{ border: 1, borderColor: 'divider', mb: 2.5 }}
        >
          {playing ? <PauseIcon fontSize="small" /> : <PlayIcon fontSize="small" />}
        </IconButton>
        <Slider
          value={hour}
          min={0}
          max={hours}
          step={1}
          marks={[
            { value: 0, label: 'departure' },
            { value: 24, label: '+24 h' },
            { value: hours, label: `+${hours} h` },
          ]}
          onChange={(_, value) => {
            onPlaying(false)
            onHour(value as number)
          }}
          aria-label="Hours after departure"
          getAriaValueText={(h) => `${h} hours after departure, ${formatDateTime(new Date(Date.parse(start) + h * 3_600_000))}`}
          sx={{
            '& .MuiSlider-markLabel': { typography: 'caption', color: 'text.secondary' },
            '& .MuiSlider-markLabel[data-index="0"]': { transform: 'none' },
            '& .MuiSlider-markLabel[data-index="2"]': { transform: 'translateX(-100%)' },
          }}
        />
      </Stack>
    </Paper>
  )
}
