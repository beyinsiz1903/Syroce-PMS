import { useColorScheme } from 'react-native';

export type ThemeColors = {
  bg: string;
  surface: string;
  surfaceAlt: string;
  border: string;
  text: string;
  textMuted: string;
  primary: string;
  primaryText: string;
  primarySoft: string;
  success: string;
  warning: string;
  danger: string;
  info: string;
  vip: string;
};

// Marka rengi lacivert (guven). Alert kirmizi/turuncu, success yesil, bg off-white.
const dark: ThemeColors = {
  bg: '#0b0f1a',
  surface: '#121826',
  surfaceAlt: '#1a2236',
  border: '#243049',
  text: '#f4f6fb',
  textMuted: '#9aa6bf',
  primary: '#3b6fe0',
  primaryText: '#ffffff',
  primarySoft: '#1b2747',
  success: '#22c55e',
  warning: '#fb923c',
  danger: '#f05252',
  info: '#38bdf8',
  vip: '#fbbf24',
};

const light: ThemeColors = {
  bg: '#f5f7fa',
  surface: '#ffffff',
  surfaceAlt: '#eef1f7',
  border: '#e2e7f0',
  text: '#0f172a',
  textMuted: '#5b6478',
  primary: '#1e3a8a',
  primaryText: '#ffffff',
  primarySoft: '#e6ecf8',
  success: '#15803d',
  warning: '#ea580c',
  danger: '#dc2626',
  info: '#0369a1',
  vip: '#a16207',
};

export const spacing = {
  xs: 4,
  sm: 8,
  md: 12,
  lg: 16,
  xl: 24,
  xxl: 32,
};

export const radius = {
  sm: 6,
  md: 10,
  lg: 16,
  xl: 24,
  pill: 999,
};

// Yumusak yukselti (scannability icin kartlari zeminden ayirir). Dark modda
// golge neredeyse gorunmez, bu yuzden orada sinir tasiyiciligi yapar.
export const cardShadow = {
  shadowColor: '#0f172a',
  shadowOffset: { width: 0, height: 2 },
  shadowOpacity: 0.06,
  shadowRadius: 8,
  elevation: 2,
};

export function useTheme(): ThemeColors {
  const scheme = useColorScheme();
  return scheme === 'light' ? light : dark;
}

export const roomStatusColor = (status: string | undefined, c: ThemeColors): string => {
  switch ((status || '').toLowerCase()) {
    case 'clean':
    case 'available':
    case 'inspected':
      return c.success;
    case 'dirty':
      return c.warning;
    case 'cleaning':
    case 'inspection':
      return c.info;
    case 'out_of_order':
    case 'maintenance':
      return c.danger;
    case 'occupied':
      return c.primary;
    default:
      return c.textMuted;
  }
};
