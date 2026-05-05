import { create } from 'zustand';
import * as SecureStore from 'expo-secure-store';
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
export type SettingsState = {
  hydrated: boolean;
  biometricLock: boolean;
  hydrate: () => Promise<void>;
  setBiometricLock: (v: boolean) => Promise<void>;
};

export const useSettingsStore = create<SettingsState>((set) => ({
  hydrated: false,
  biometricLock: false,

  async hydrate() {
    try {
      const raw = await SecureStore.getItemAsync(BIOMETRIC_PREF_STORAGE_KEY);
      set({ biometricLock: raw === '1', hydrated: true });
    } catch {
      set({ biometricLock: false, hydrated: true });
    }
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
}));
