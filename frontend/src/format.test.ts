import { describe, expect, it } from 'vitest'
import { formatRiskMiles } from './format'

describe('miles at a risk level', () => {
  it('shows a stretch under half a mile as under one mile, not as none', () => {
    expect(formatRiskMiles(0)).toBe('0 mi')
    expect(formatRiskMiles(0.3)).toBe('<1 mi')
    expect(formatRiskMiles(0.5)).toBe('1 mi') // half a mile rounds up, as the reason text does
    expect(formatRiskMiles(12.5)).toBe('13 mi')
  })
})
