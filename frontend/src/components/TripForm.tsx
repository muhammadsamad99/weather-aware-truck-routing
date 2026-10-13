import type { FormEvent } from 'react'
import type { TripForm as TripFormValues } from '../types'
import PlaceInput from './PlaceInput'

export const INTERVALS = [10, 25, 50] as const
export const MAX_LOAD_LB = 80_000

interface Props {
  values: TripFormValues
  onChange: (values: TripFormValues) => void
  onSubmit: () => void
  busy: boolean
  fieldErrors: Record<string, string>
}

export default function TripForm({ values, onChange, onSubmit, busy, fieldErrors }: Props) {
  const set = <K extends keyof TripFormValues>(key: K, value: TripFormValues[K]) => onChange({ ...values, [key]: value })

  const submit = (e: FormEvent) => {
    e.preventDefault()
    onSubmit()
  }

  return (
    <form className="trip-form" onSubmit={submit} noValidate>
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
      <div className="row">
        <div className="field">
          <label htmlFor="departure">Departure</label>
          <input
            id="departure"
            type="datetime-local"
            value={values.departure}
            aria-invalid={Boolean(fieldErrors.departure)}
            onChange={(e) => set('departure', e.target.value)}
          />
          {fieldErrors.departure && <div className="field-error">{fieldErrors.departure}</div>}
        </div>
        <div className="field load">
          <label htmlFor="load">Load (lb)</label>
          <input
            id="load"
            type="number"
            inputMode="numeric"
            min={1}
            max={MAX_LOAD_LB}
            step={500}
            value={values.loadLb}
            aria-invalid={Boolean(fieldErrors.load_lb)}
            onChange={(e) => set('loadLb', e.target.value)}
          />
          {fieldErrors.load_lb && <div className="field-error">{fieldErrors.load_lb}</div>}
        </div>
      </div>
      <fieldset className="field interval">
        <legend>Check the weather every</legend>
        <div className="segmented">
          {INTERVALS.map((mi) => (
            <label key={mi} className={values.intervalMi === mi ? 'on' : undefined}>
              <input
                type="radio"
                name="interval"
                value={mi}
                checked={values.intervalMi === mi}
                onChange={() => set('intervalMi', mi)}
              />
              {mi} mi
            </label>
          ))}
        </div>
      </fieldset>
      <button type="submit" className="primary" disabled={busy}>
        {busy ? 'Planning…' : 'Plan routes'}
      </button>
    </form>
  )
}
