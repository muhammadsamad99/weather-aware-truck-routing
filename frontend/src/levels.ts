import type { ExpressionSpecification } from 'maplibre-gl'
import type { LevelName } from './types'

/** Risk levels 0-4, as the API numbers them. */
export const LEVELS: { name: LevelName; color: string }[] = [
  { name: 'Low', color: '#2f9e5b' },
  { name: 'Moderate', color: '#e9b500' },
  { name: 'High', color: '#f07c19' },
  { name: 'Severe', color: '#d62f2f' },
  { name: 'No Travel', color: '#6b1fa8' },
]

export const levelColor = (level: number) => LEVELS[level]?.color ?? '#888'

/** A MapLibre expression giving each feature's colour from its numeric `level` property. */
export const levelColorExpression = [
  'match',
  ['get', 'level'],
  ...LEVELS.flatMap((l, i) => [i, l.color]),
  '#888',
] as unknown as ExpressionSpecification
