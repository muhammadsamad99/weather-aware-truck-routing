import { cleanup, render, screen } from '@testing-library/react'
import { afterEach, expect, it, vi } from 'vitest'
import App from './App'
import AppProviders from './AppProviders'

// A map that breaks while drawing: the app must contain it to the map area.
vi.mock('./components/MapView', () => ({
  default: function BrokenMap(): never {
    throw new Error('boom')
  },
}))

afterEach(() => {
  cleanup()
  vi.restoreAllMocks()
})

it('keeps the trip form when the map breaks while drawing', () => {
  vi.spyOn(console, 'error').mockImplementation(() => {})
  vi.spyOn(console, 'warn').mockImplementation(() => {})
  render(<App />, { wrapper: AppProviders })
  expect(screen.getByLabelText('Origin')).toBeTruthy()
  expect(screen.getByText('The map stopped working.')).toBeTruthy()
})
