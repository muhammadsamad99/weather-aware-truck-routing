import Autocomplete from '@mui/material/Autocomplete'
import TextField from '@mui/material/TextField'
import { useEffect, useState } from 'react'
import { searchPlaces } from '../api'
import type { Place, PlaceInputValue } from '../types'

const DEBOUNCE_MS = 400
const MIN_CHARS = 3
const LOOKUP_FAILED =
  "Suggestions aren't available right now. You can still type a place and plan, or enter coordinates, " +
  'for example 28.54, -81.38.'

interface Props {
  label: string
  value: PlaceInputValue
  onChange: (value: PlaceInputValue) => void
  error?: string
  placeholder?: string
}

/**
 * A place box with suggestions. Typing clears any picked place (the text is looked up when planning);
 * picking a suggestion keeps its coordinates.
 */
export default function PlaceInput({ label, value, onChange, error, placeholder }: Props) {
  const [suggestions, setSuggestions] = useState<Place[]>([])
  const [searching, setSearching] = useState(false)
  const [lookupFailed, setLookupFailed] = useState(false)
  // Suggestions are only for what the person typed: text set from outside (the example) isn't looked up.
  const [typed, setTyped] = useState('')

  const query = !value.place && value.text === typed ? typed.trim() : ''

  useEffect(() => {
    if (query.length < MIN_CHARS) {
      setSuggestions([])
      setSearching(false)
      setLookupFailed(false)
      return
    }
    const controller = new AbortController()
    setSearching(true)
    const timer = window.setTimeout(() => {
      searchPlaces(query, controller.signal)
        .then((places) => {
          setSuggestions(places)
          setLookupFailed(false)
        })
        .catch((err) => {
          if (err.name !== 'AbortError') setLookupFailed(true)
        })
        .finally(() => {
          if (!controller.signal.aborted) setSearching(false)
        })
    }, DEBOUNCE_MS)
    return () => {
      window.clearTimeout(timer)
      controller.abort()
    }
  }, [query])

  const hint = value.place
    ? `${value.place.lat.toFixed(4)}, ${value.place.lon.toFixed(4)}`
    : lookupFailed
      ? LOOKUP_FAILED
      : undefined

  return (
    <Autocomplete<Place, false, false, true>
      freeSolo
      options={suggestions}
      value={value.place}
      inputValue={value.text}
      filterOptions={(options) => options} // the server already matched them
      loading={searching}
      loadingText="Looking up places…"
      getOptionLabel={(o) => (typeof o === 'string' ? o : o.label)}
      getOptionKey={(o) => (typeof o === 'string' ? o : `${o.label}|${o.lat},${o.lon}`)}
      isOptionEqualToValue={(a, b) => a.lat === b.lat && a.lon === b.lon}
      // Picking a suggestion also reports an input change (reason 'selectOption', just before onChange);
      // only typing and clearing drop the picked place.
      onInputChange={(_, text, reason) => {
        if (reason === 'input' || reason === 'clear') {
          setTyped(reason === 'input' ? text : '')
          onChange({ text, place: null })
        }
      }}
      onChange={(_, picked) => {
        if (picked && typeof picked !== 'string') onChange({ text: picked.label, place: picked })
        else if (picked === null) onChange({ text: '', place: null })
      }}
      renderInput={(params) => (
        <TextField
          {...params}
          label={label}
          placeholder={placeholder}
          error={Boolean(error)}
          helperText={error || hint}
        />
      )}
    />
  )
}
