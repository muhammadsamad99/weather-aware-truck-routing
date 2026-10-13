import { useEffect, useId, useRef, useState } from 'react'
import { searchPlaces } from '../api'
import type { Place, PlaceInputValue } from '../types'

const DEBOUNCE_MS = 400
const MIN_CHARS = 3

interface Props {
  label: string
  value: PlaceInputValue
  onChange: (value: PlaceInputValue) => void
  error?: string
  placeholder?: string
}

/** A text box with place suggestions. Typing clears any picked place; picking one keeps its coordinates. */
export default function PlaceInput({ label, value, onChange, error, placeholder }: Props) {
  const id = useId()
  const [suggestions, setSuggestions] = useState<Place[]>([])
  const [open, setOpen] = useState(false)
  const [active, setActive] = useState(-1)
  const [lookupFailed, setLookupFailed] = useState(false)
  const blurTimer = useRef<number>(undefined)

  const query = value.place ? '' : value.text.trim()

  useEffect(() => {
    if (query.length < MIN_CHARS) {
      setSuggestions([])
      setLookupFailed(false)
      return
    }
    const controller = new AbortController()
    const timer = window.setTimeout(() => {
      searchPlaces(query, controller.signal)
        .then((places) => {
          setSuggestions(places)
          setActive(-1)
          setLookupFailed(false)
        })
        .catch((err) => {
          if (err.name !== 'AbortError') setLookupFailed(true)
        })
    }, DEBOUNCE_MS)
    return () => {
      window.clearTimeout(timer)
      controller.abort()
    }
  }, [query])

  const pick = (place: Place) => {
    onChange({ text: place.label, place })
    setOpen(false)
    setSuggestions([])
  }

  const onKeyDown = (e: React.KeyboardEvent<HTMLInputElement>) => {
    if (!open || suggestions.length === 0) return
    if (e.key === 'ArrowDown') {
      e.preventDefault()
      setActive((a) => (a + 1) % suggestions.length)
    } else if (e.key === 'ArrowUp') {
      e.preventDefault()
      setActive((a) => (a <= 0 ? suggestions.length - 1 : a - 1))
    } else if (e.key === 'Enter' && active >= 0) {
      e.preventDefault()
      pick(suggestions[active])
    } else if (e.key === 'Escape') {
      setOpen(false)
    }
  }

  const listId = `${id}-list`
  const errorId = `${id}-error`
  const showList = open && suggestions.length > 0
  return (
    <div className="field place-input">
      <label htmlFor={id}>{label}</label>
      <input
        id={id}
        type="text"
        autoComplete="off"
        placeholder={placeholder}
        value={value.text}
        aria-invalid={Boolean(error)}
        aria-describedby={error ? errorId : undefined}
        role="combobox"
        aria-expanded={showList}
        aria-controls={showList ? listId : undefined}
        aria-autocomplete="list"
        aria-activedescendant={showList && active >= 0 ? `${listId}-${active}` : undefined}
        onChange={(e) => {
          onChange({ text: e.target.value, place: null })
          setOpen(true)
        }}
        onFocus={() => setOpen(true)}
        onBlur={() => {
          blurTimer.current = window.setTimeout(() => setOpen(false), 150)
        }}
        onKeyDown={onKeyDown}
      />
      {showList && (
        <ul className="suggestions" id={listId} role="listbox">
          {suggestions.map((s, i) => (
            <li
              key={`${s.label}-${s.lat}-${s.lon}`}
              id={`${listId}-${i}`}
              role="option"
              aria-selected={i === active}
              className={i === active ? 'active' : undefined}
              onMouseDown={(e) => {
                e.preventDefault() // keep focus, so the blur timer does not close the list first
                window.clearTimeout(blurTimer.current)
                pick(s)
              }}
            >
              {s.label}
            </li>
          ))}
        </ul>
      )}
      {value.place && <div className="hint">{value.place.lat.toFixed(4)}, {value.place.lon.toFixed(4)}</div>}
      {!value.place && lookupFailed && <div className="hint">Suggestions are unavailable; the place will be looked up when you plan.</div>}
      {error && (
        <div className="field-error" id={errorId}>
          {error}
        </div>
      )}
    </div>
  )
}
