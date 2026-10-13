import { createTheme } from '@mui/material/styles'

/** Colours used outside MUI components too (MapLibre layers, map markers). */
export const brand = {
  primary: '#1d4ed8',
  otherRoute: '#7b8698',
  origin: '#0f766e',
  ink: '#18212f',
  muted: '#5b6676',
  line: '#dde3ea',
  soft: '#f4f6f9',
  mapBackground: '#eef1f4',
}

export const theme = createTheme({
  cssVariables: true,
  palette: {
    primary: { main: brand.primary },
    text: { primary: brand.ink, secondary: brand.muted },
    divider: brand.line,
    error: { main: '#b42318' },
    contrastThreshold: 4.5,
  },
  typography: {
    fontFamily: "system-ui, -apple-system, 'Segoe UI', Roboto, 'Helvetica Neue', Arial, sans-serif",
    h1: { fontSize: '1.25rem', fontWeight: 700, lineHeight: 1.3 },
    h2: { fontSize: '1rem', fontWeight: 600 },
    body1: { fontSize: '0.9375rem' },
    body2: { fontSize: '0.875rem' },
    caption: { fontSize: '0.75rem' },
    button: { textTransform: 'none', fontWeight: 600 },
  },
  shape: { borderRadius: 8 },
  components: {
    MuiTextField: { defaultProps: { size: 'small', fullWidth: true } },
    MuiButton: { defaultProps: { disableElevation: true } },
    MuiStack: { defaultProps: { useFlexGap: true } },
    MuiAccordion: {
      defaultProps: { disableGutters: true, elevation: 0 },
      styleOverrides: { root: { border: `1px solid ${brand.line}`, borderRadius: 8, '&::before': { display: 'none' } } },
    },
    MuiAccordionSummary: { styleOverrides: { root: { minHeight: 44 } } },
    MuiTableCell: {
      styleOverrides: {
        sizeSmall: { padding: '6px 8px' },
        head: { fontWeight: 600, backgroundColor: brand.soft, color: brand.muted },
      },
    },
    MuiChip: { styleOverrides: { sizeSmall: { height: 20, fontWeight: 600 } } },
  },
})
