import Chip from '@mui/material/Chip'
import { LEVELS } from '../levels'

/** A risk level as a small coloured chip, with text that keeps its contrast on each colour. */
export default function RiskChip({ level }: { level: number }) {
  const l = LEVELS[level]
  return <Chip size="small" label={l?.name ?? '?'} sx={{ bgcolor: l?.color, color: l?.text }} />
}
