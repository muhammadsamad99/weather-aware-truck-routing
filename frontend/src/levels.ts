import type { ExpressionSpecification } from 'maplibre-gl'
import type { LevelName } from './types'

/**
 * Risk levels 0-4, as the API numbers them: the fill colour, and the text colour that reads on it at
 * WCAG AA (4.5:1). White text fails on Low, Moderate and High, so those take dark text.
 */
export const LEVELS: { name: LevelName; color: string; text: string }[] = [
  { name: 'Low', color: '#2f9e5b', text: '#18212f' },
  { name: 'Moderate', color: '#e9b500', text: '#18212f' },
  { name: 'High', color: '#f07c19', text: '#18212f' },
  { name: 'Severe', color: '#d62f2f', text: '#ffffff' },
  { name: 'No Travel', color: '#6b1fa8', text: '#ffffff' },
]

export const levelColor = (level: number) => LEVELS[level]?.color ?? '#888'
export const levelText = (level: number) => LEVELS[level]?.text ?? '#18212f'

/** A MapLibre expression giving each feature's colour from its numeric `level` property. */
export const levelColorExpression = [
  'match',
  ['get', 'level'],
  ...LEVELS.flatMap((l, i) => [i, l.color]),
  '#888',
] as unknown as ExpressionSpecification
