import { create } from 'zustand';
import AsyncStorage from '@react-native-async-storage/async-storage';
import * as SecureStore from '../storage/secureStore';
import { BIOMETRIC_PREF_STORAGE_KEY } from '../api/client';

/**
 * Persistent user preferences for the mobile app (V3).
 *
 * Storage
 * -------
 * Persisted to SecureStore (encrypted on iOS Keychain / Android EncryptedSharedPrefs).
 * V3 spec: the entire SecureStore is wiped on logout — including the
 * biometric-lock preference — so a returning user re-confirms the
 * setting after their next sign-in. `clearAllAuthStorage` in
 * `src/api/client.ts` is the single source of truth for that wipe; this
 * store simply re-hydrates from disk on app boot via `hydrate()`.
 */
export type ThemeMode = 'light' | 'dark' | 'system';
export type TextScale = 'standard' | 'large' | 'extra_large';
export type AppLocale = 'tr' | 'en';

// Tema tercihi sir DEGIL ve cikista silinmemeli -> AsyncStorage (SecureStore
// degil; SecureStore cikista tamamen silinir). 'system' = cihazin OS acik/koyu
// ayarini izle.
const THEME_MODE_KEY = 'theme_mode';
const TEXT_SCALE_KEY = 'text_scale';
const APP_LOCALE_KEY = 'app_locale';
const VALID_THEME_MODES: ThemeMode[] = ['light', 'dark', 'system'];
const VALID_TEXT_SCALES: TextScale[] = ['standard', 'large', 'extra_large'];
const VALID_APP_LOCALES: AppLocale[] = ['tr', 'en'];

export type SettingsState = {
  hydrated: boolean;
  biometricLock: boolean;
  themeMode: ThemeMode;
  textScale: TextScale;
  locale: AppLocale;
  hydrate: () => Promise<void>;
  setBiometricLock: (v: boolean) => Promise<void>;
  setThemeMode: (m: ThemeMode) => Promise<void>;
  setTextScale: (m: TextScale) => Promise<void>;
  setLocale: (locale: AppLocale) => Promise<void>;
};

export const useSettingsStore = create<SettingsState>((set) => ({
  hydrated: false,
  biometricLock: false,
  // New installs use the day-shift palette; never overwrite a saved choice.
  themeMode: 'light',
  textScale: 'standard',
  locale: 'tr',

  async hydrate() {
    let biometricLock = false;
    let themeMode: ThemeMode = 'light';
    let textScale: TextScale = 'standard';
    let locale: AppLocale = 'tr';
    try {
      const raw = await SecureStore.getItemAsync(BIOMETRIC_PREF_STORAGE_KEY);
      biometricLock = raw === '1';
    } catch {
      // ignore — biyometri varsayilani kapali kalir
    }
    try {
      const raw = await AsyncStorage.getItem(THEME_MODE_KEY);
      if (raw && VALID_THEME_MODES.includes(raw as ThemeMode)) {
        themeMode = raw as ThemeMode;
      }
    } catch {
      // Storage unavailable: keep the readable day-shift default.
    }
    try {
      const raw = await AsyncStorage.getItem(TEXT_SCALE_KEY);
      if (raw && VALID_TEXT_SCALES.includes(raw as TextScale)) textScale = raw as TextScale;
    } catch {
      // ignore — accessibility default remains standard
    }
    try {
      const raw = await AsyncStorage.getItem(APP_LOCALE_KEY);
      if (raw && VALID_APP_LOCALES.includes(raw as AppLocale)) locale = raw as AppLocale;
    } catch {
      // Turkish remains the safe default
    }
    set({ biometricLock, themeMode, textScale, locale, hydrated: true });
  },

  async setBiometricLock(v: boolean) {
    try {
      if (v) {
        await SecureStore.setItemAsync(BIOMETRIC_PREF_STORAGE_KEY, '1');
      } else {
        await SecureStore.deleteItemAsync(BIOMETRIC_PREF_STORAGE_KEY);
      }
    } catch {
      // ignore — we still flip the in-memory flag below
    }
    set({ biometricLock: v });
  },

  async setThemeMode(m: ThemeMode) {
    try {
      await AsyncStorage.setItem(THEME_MODE_KEY, m);
    } catch {
      // ignore — yine de bellek-ici uygula
    }
    set({ themeMode: m });
  },

  async setTextScale(m: TextScale) {
    try { await AsyncStorage.setItem(TEXT_SCALE_KEY, m); } catch { /* memory still updates */ }
    set({ textScale: m });
  },

  async setLocale(locale: AppLocale) {
    try { await AsyncStorage.setItem(APP_LOCALE_KEY, locale); } catch { /* memory still updates */ }
    set({ locale });
  },
}));
