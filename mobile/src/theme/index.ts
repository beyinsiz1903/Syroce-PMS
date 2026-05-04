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
  success: string;
  warning: string;
  danger: string;
  info: string;
  vip: string;
};

const dark: ThemeColors = {
  bg: '#0b0f1a',
  surface: '#121826',
  surfaceAlt: '#1a2236',
  border: '#243049',
  text: '#f4f6fb',
  textMuted: '#9aa6bf',
  primary: '#3b82f6',
  primaryText: '#ffffff',
  success: '#16a34a',
  warning: '#f59e0b',
  danger: '#ef4444',
  info: '#0ea5e9',
  vip: '#a855f7',
};

const light: ThemeColors = {
  bg: '#f7f8fb',
  surface: '#ffffff',
  surfaceAlt: '#eef1f7',
  border: '#dde2ec',
  text: '#0f172a',
  textMuted: '#5b6478',
  primary: '#2563eb',
  primaryText: '#ffffff',
  success: '#15803d',
  warning: '#b45309',
  danger: '#b91c1c',
  info: '#0369a1',
  vip: '#7c3aed',
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
  lg: 14,
  xl: 20,
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
