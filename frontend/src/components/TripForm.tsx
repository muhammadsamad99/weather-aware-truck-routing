import Button from '@mui/material/Button'
import FormControl from '@mui/material/FormControl'
import FormLabel from '@mui/material/FormLabel'
import InputAdornment from '@mui/material/InputAdornment'
import Stack from '@mui/material/Stack'
import TextField from '@mui/material/TextField'
import ToggleButton from '@mui/material/ToggleButton'
import ToggleButtonGroup from '@mui/material/ToggleButtonGroup'
import type { Dispatch, FormEvent, SetStateAction } from 'react'
import type { TripForm as TripFormValues } from '../types'
import PlaceInput from './PlaceInput'

export const INTERVALS = [10, 25, 50] as const
export const MAX_LOAD_LB = 80_000

interface Props {
  values: TripFormValues
  onChange: Dispatch<SetStateAction<TripFormValues>>
  onSubmit: () => void
  busy: boolean
  fieldErrors: Record<string, string>
}

export default function TripForm({ values, onChange, onSubmit, busy, fieldErrors }: Props) {
  // Functional updates: one interaction can report two changes in the same tick (the place box does).
  const set = <K extends keyof TripFormValues>(key: K, value: TripFormValues[K]) =>
    onChange((current) => ({ ...current, [key]: value }))

  const submit = (e: FormEvent) => {
    e.preventDefault()
    onSubmit()
  }

  return (
    <Stack component="form" spacing={1.5} noValidate onSubmit={submit}>
      <PlaceInput
        label="Origin"
        placeholder="City, address or lat, lon"
        value={values.origin}
        onChange={(v) => set('origin', v)}
        error={fieldErrors.origin}
      />
      <PlaceInput
        label="Destination"
        placeholder="City, address or lat, lon"
        value={values.destination}
        onChange={(v) => set('destination', v)}
        error={fieldErrors.destination}
      />
      <Stack direction={{ xs: 'column', sm: 'row' }} spacing={1.5}>
        <TextField
          label="Departure"
          type="datetime-local"
          value={values.departure}
          onChange={(e) => set('departure', e.target.value)}
          error={Boolean(fieldErrors.departure)}
          helperText={fieldErrors.departure}
          slotProps={{ inputLabel: { shrink: true } }}
          sx={{ flex: 1 }}
        />
        <TextField
          label="Load"
          type="number"
          value={values.loadLb}
          onChange={(e) => set('loadLb', e.target.value)}
          error={Boolean(fieldErrors.load_lb)}
          helperText={fieldErrors.load_lb}
          slotProps={{
            input: { endAdornment: <InputAdornment position="end">lb</InputAdornment> },
            htmlInput: { min: 1, max: MAX_LOAD_LB, step: 500, inputMode: 'numeric' },
          }}
          sx={{ width: { sm: 124 }, flexShrink: 0 }}
        />
      </Stack>
      <FormControl component="fieldset">
        <FormLabel component="legend" id="interval-label" sx={{ typography: 'body2', mb: 0.5 }}>
          Check the weather every
        </FormLabel>
        <ToggleButtonGroup
          exclusive
          fullWidth
          size="small"
          color="primary"
          value={values.intervalMi}
          onChange={(_, mi: TripFormValues['intervalMi'] | null) => {
            if (mi !== null) set('intervalMi', mi) // one interval is always chosen
          }}
          aria-labelledby="interval-label"
        >
          {INTERVALS.map((mi) => (
            <ToggleButton key={mi} value={mi}>
              {mi} mi
            </ToggleButton>
          ))}
        </ToggleButtonGroup>
      </FormControl>
      <Button type="submit" variant="contained" size="large" loading={busy} loadingPosition="start">
        {busy ? 'Planning…' : 'Plan routes'}
      </Button>
    </Stack>
  )
}
