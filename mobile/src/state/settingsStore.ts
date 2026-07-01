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

// Tema tercihi sir DEGIL ve cikista silinmemeli -> AsyncStorage (SecureStore
// degil; SecureStore cikista tamamen silinir). 'system' = cihazin OS acik/koyu
// ayarini izle.
const THEME_MODE_KEY = 'theme_mode';
const VALID_THEME_MODES: ThemeMode[] = ['light', 'dark', 'system'];

export type SettingsState = {
  hydrated: boolean;
  biometricLock: boolean;
  themeMode: ThemeMode;
  hydrate: () => Promise<void>;
  setBiometricLock: (v: boolean) => Promise<void>;
  setThemeMode: (m: ThemeMode) => Promise<void>;
};

export const useSettingsStore = create<SettingsState>((set) => ({
  hydrated: false,
  biometricLock: false,
  // Varsayilan koyu: marka kimligi korunur. Acik/Sistem kullanicinin opt-in
  // secimidir (settingsStore -> useTheme uzerinden tum ekranlara yansir).
  themeMode: 'dark',

  async hydrate() {
    let biometricLock = false;
    let themeMode: ThemeMode = 'dark';
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
      // ignore — tema varsayilani koyu kalir
    }
    set({ biometricLock, themeMode, hydrated: true });
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
}));
