import { useColorScheme } from 'react-native';
import { useSettingsStore } from '../state/settingsStore';

export type ThemeColors = {
  bg: string;
  surface: string;
  surfaceAlt: string;
  surfaceGlass: string;
  glassHighlight: string;
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

// Koyu premium kimlik (2030 / Apple seviyesi operasyon merkezi). Bu palet
// uygulamanin VARSAYILAN kimligidir: zemin neredeyse siyah-lacivert, kartlar
// uzerine katmanlanan acik yuzeyler, primary canli mavi, durum renkleri net.
// surfaceGlass + glassHighlight cam efekti hissini (saydam yuzey + ust isik
// cizgisi) blur kutuphanesi gerektirmeden tasir.
export const darkTheme: ThemeColors = {
  bg: '#060B17',
  surface: '#101827',
  surfaceAlt: '#172033',
  surfaceGlass: 'rgba(23,32,51,0.72)',
  glassHighlight: 'rgba(255,255,255,0.10)',
  border: 'rgba(255,255,255,0.08)',
  text: '#FFFFFF',
  textMuted: '#94A3B8',
  primary: '#2563EB',
  primaryText: '#FFFFFF',
  primarySoft: '#16223D',
  success: '#10B981',
  warning: '#F59E0B',
  danger: '#EF4444',
  info: '#38BDF8',
  vip: '#FBBF24',
};

// Acik tema — Light/System tema secimi ile aktif (koyu premium kimlik hala
// varsayilan: themeMode default 'dark'). useResolvedScheme() === 'light' iken
// useTheme() bu paleti dondurur; secici (ThemeModeSelector) ile opt-in.
export const lightTheme: ThemeColors = {
  bg: '#f5f7fa',
  surface: '#ffffff',
  surfaceAlt: '#eef1f7',
  surfaceGlass: 'rgba(255,255,255,0.72)',
  glassHighlight: 'rgba(255,255,255,0.65)',
  border: '#e2e7f0',
  text: '#0f172a',
  textMuted: '#5b6478',
  primary: '#2563EB',
  primaryText: '#ffffff',
  primarySoft: '#e6ecf8',
  success: '#0f9d6b',
  warning: '#d97706',
  danger: '#dc2626',
  info: '#0369a1',
  vip: '#a16207',
};

// 8px tabanli bosluk olcegi (premium nefes alani icin).
export const spacing = {
  xs: 4,
  sm: 8,
  md: 12,
  lg: 16,
  xl: 24,
  xxl: 32,
};

// Premium yuvarlama: kartlar 20-24px (Apple Wallet hissi), buton/alanlar 12px.
export const radius = {
  sm: 8,
  md: 12,
  lg: 20,
  xl: 24,
  pill: 999,
};

// Premium yumusak golge: koyu zeminde kartlari yukseltir, derinlik/katman
// hissi verir. Web'de RN bunu box-shadow'a cevirir, native'de elevation.
export const cardShadow = {
  shadowColor: '#000000',
  shadowOffset: { width: 0, height: 12 },
  shadowOpacity: 0.35,
  shadowRadius: 24,
  elevation: 10,
};

// Hareket katmani: tek kaynaktan sure/easing. Skeleton shimmer, basari
// animasyonu ve yumusak gecisler bu degerleri kullanir (web-guvenli).
export const motion = {
  fast: 150,
  base: 240,
  slow: 420,
};

// Cozulmus tema semasi: kullanici tercihini (settingsStore.themeMode) okur;
// 'system' ise cihazin OS acik/koyu ayarini (useColorScheme) izler. Tek
// dogruluk kaynagi burasi -> useTheme()'i cagiran tum ekranlar tercih degisince
// otomatik yeniden render olur (zustand secici + RN Appearance aboneligi).
export function useResolvedScheme(): 'light' | 'dark' {
  const mode = useSettingsStore((s) => s.themeMode);
  const system = useColorScheme();
  if (mode === 'system') return system === 'light' ? 'light' : 'dark';
  return mode;
}

export function useTheme(): ThemeColors {
  return useResolvedScheme() === 'light' ? lightTheme : darkTheme;
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
