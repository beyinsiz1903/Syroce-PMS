import React, { useCallback, useEffect, useRef, useState } from 'react';
import { ActivityIndicator, AppState, AppStateStatus, Pressable, Text, View } from 'react-native';
import { spacing, useTheme } from '../theme';
import { useSettingsStore } from '../state/settingsStore';
import { useAuthStore } from '../state/authStore';
import { authenticateBiometric, getBiometricCapability } from '../biometrics/lock';

/**
 * Renders an opaque "locked" overlay over the app when:
 *   - The user has enabled biometric lock in settings, AND
 *   - The user is signed in, AND
 *   - The app has just resumed from background (or first launch).
 *
 * The overlay clears when biometric auth succeeds. If biometrics are
 * unavailable on the device the gate clears automatically — we don't want
 * to brick the app for someone whose phone has no Face ID enrolled.
 *
 * Lock-on-background timing: we lock immediately when AppState flips to
 * `inactive` / `background` and require a fresh prompt on `active`. A short
 * 5-second grace window keeps quick app switches (e.g. opening Camera for
 * an ID scan) from feeling annoying.
 */
const RELOCK_GRACE_MS = 5_000;

export const BiometricLockGate: React.FC<{ children: React.ReactNode }> = ({ children }) => {
  const c = useTheme();
  const enabled = useSettingsStore((s) => s.biometricLock);
  const settingsHydrated = useSettingsStore((s) => s.hydrated);
  const user = useAuthStore((s) => s.user);

  const [locked, setLocked] = useState(false);
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const lastBackgroundedAt = useRef<number | null>(null);
  const initialised = useRef(false);

  const tryUnlock = useCallback(async () => {
    setBusy(true);
    setError(null);
    const cap = await getBiometricCapability();
    if (!cap.available) {
      // No biometrics enrolled / no hardware → don't trap the user out of
      // their own app. Clear the lock and let them in.
      setLocked(false);
      setBusy(false);
      return;
    }
    const ok = await authenticateBiometric('Syroce PMS kilidi açılıyor');
    if (ok) {
      setLocked(false);
      lastBackgroundedAt.current = null;
    } else {
      setError('Doğrulama başarısız, tekrar deneyin');
    }
    setBusy(false);
  }, []);

  // Lock when the app first mounts with biometric pref ON (and a user
  // is signed in). Without this, opening a fresh app from a cold start
  // would skip the prompt.
  useEffect(() => {
    if (!settingsHydrated) return;
    if (!user) {
      setLocked(false);
      initialised.current = true;
      return;
    }
    if (!enabled) {
      setLocked(false);
      initialised.current = true;
      return;
    }
    if (!initialised.current) {
      initialised.current = true;
      setLocked(true);
      // Defer prompt one tick so the overlay is visible first.
      setTimeout(() => {
        tryUnlock();
      }, 100);
    }
  }, [settingsHydrated, enabled, user, tryUnlock]);

  // Re-lock on background → foreground transitions.
  useEffect(() => {
    if (!enabled || !user) return;
    const sub = AppState.addEventListener('change', (next: AppStateStatus) => {
      if (next === 'background' || next === 'inactive') {
        lastBackgroundedAt.current = Date.now();
      } else if (next === 'active') {
        const t = lastBackgroundedAt.current;
        if (t && Date.now() - t > RELOCK_GRACE_MS) {
          setLocked(true);
          setTimeout(() => {
            tryUnlock();
          }, 100);
        }
      }
    });
    return () => sub.remove();
  }, [enabled, user, tryUnlock]);

  return (
    <View style={{ flex: 1 }}>
      {children}
      {locked ? (
        <View
          testID="smoke-biometric-lock"
          accessibilityLabel="Doğrulama gerekli"
          style={{
            position: 'absolute',
            top: 0,
            left: 0,
            right: 0,
            bottom: 0,
            backgroundColor: c.bg,
            alignItems: 'center',
            justifyContent: 'center',
            padding: spacing.xl,
            gap: spacing.lg,
          }}
        >
          <Text style={{ color: c.text, fontSize: 22, fontWeight: '700' }}>
            Syroce PMS kilitli
          </Text>
          <Text style={{ color: c.text, fontSize: 16, fontWeight: '600' }}>
            Doğrulama gerekli
          </Text>
          <Text style={{ color: c.textMuted, textAlign: 'center' }}>
            Devam etmek için biyometrik doğrulamayı tamamlayın.
          </Text>
          {busy ? (
            <ActivityIndicator color={c.primary} />
          ) : (
            <Pressable
              onPress={tryUnlock}
              accessibilityRole="button"
              accessibilityLabel="Kilidi aç"
              style={{
                backgroundColor: c.primary,
                paddingHorizontal: spacing.xl,
                paddingVertical: spacing.md,
                borderRadius: 8,
              }}
            >
              <Text style={{ color: c.primaryText, fontWeight: '700' }}>Kilidi aç</Text>
            </Pressable>
          )}
          {error ? (
            <Text style={{ color: c.danger, textAlign: 'center' }}>{error}</Text>
          ) : null}
        </View>
      ) : null}
    </View>
  );
};
