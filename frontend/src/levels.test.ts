import { getContrastRatio } from '@mui/material/styles'
import { describe, expect, it } from 'vitest'
import { LEVELS } from './levels'

describe('risk level colours', () => {
  it('every level label reads at WCAG AA (4.5:1) on its own colour', () => {
    for (const l of LEVELS) expect(getContrastRatio(l.color, l.text), l.name).toBeGreaterThanOrEqual(4.5)
  })
})
