import React, { useEffect, useState } from 'react';
import { Alert, ScrollView, Switch, View } from 'react-native';
import { Body, Button, Card, H1, H2, Muted } from '../../src/components/ui';
import { spacing, useTheme } from '../../src/theme';
import { tr } from '../../src/i18n/tr';
import { useAuthStore } from '../../src/state/authStore';
import { useSettingsStore } from '../../src/state/settingsStore';
import { getApiUrl } from '../../src/api/client';
import {
  authenticateBiometric,
  getBiometricCapability,
} from '../../src/biometrics/lock';

export default function MoreScreen() {
  const c = useTheme();
  const { user, logout } = useAuthStore();
  const biometricLock = useSettingsStore((s) => s.biometricLock);
  const setBiometricLock = useSettingsStore((s) => s.setBiometricLock);

  const [bioAvailable, setBioAvailable] = useState<boolean>(false);
  const [bioLabel, setBioLabel] = useState<string>('Biyometrik');

  useEffect(() => {
    let cancelled = false;
    (async () => {
      const cap = await getBiometricCapability();
      if (cancelled) return;
      setBioAvailable(cap.available);
      setBioLabel(cap.label);
    })();
    return () => {
      cancelled = true;
    };
  }, []);

  const onLogout = () => {
    Alert.alert(tr.more.logout, '', [
      { text: tr.app.cancel, style: 'cancel' },
      { text: tr.more.logout, style: 'destructive', onPress: () => logout() },
    ]);
  };

  const onToggleBiometric = async (next: boolean) => {
    if (!next) {
      // Turning OFF doesn't need re-authentication; we just clear the pref.
      await setBiometricLock(false);
      return;
    }
    if (!bioAvailable) {
      Alert.alert(tr.more.biometricLock, tr.more.biometricUnavailable);
      return;
    }
    // Require a successful biometric prompt before enabling so the user
    // can't accidentally lock themselves out of an account they can't
    // verify on this device.
    const ok = await authenticateBiometric(`${tr.more.biometricLock}: ${bioLabel}`);
    if (ok) await setBiometricLock(true);
  };

  return (
    <ScrollView
      style={{ flex: 1, backgroundColor: c.bg }}
      contentContainerStyle={{ padding: spacing.lg, gap: spacing.md, paddingBottom: spacing.xl }}
    >
      <H1>{tr.more.profile}</H1>
      <Card>
        <H2>{user?.name || user?.username || user?.email || '—'}</H2>
        <Muted>{user?.email}</Muted>
        <Muted>Rol: {user?.role || '—'}</Muted>
        {user?.hotel_id ? <Muted>Otel ID: {user.hotel_id}</Muted> : null}
      </Card>

      <Card>
        <View style={{ flexDirection: 'row', alignItems: 'center', justifyContent: 'space-between', gap: spacing.sm }}>
          <View style={{ flex: 1, paddingRight: spacing.sm }}>
            <H2>{tr.more.biometricLock}</H2>
            <Muted>
              {bioAvailable ? `${tr.more.biometricLockHint} (${bioLabel})` : tr.more.biometricUnavailable}
            </Muted>
          </View>
          <Switch
            value={biometricLock}
            disabled={!bioAvailable && !biometricLock}
            onValueChange={onToggleBiometric}
            accessibilityLabel={tr.more.biometricLock}
            trackColor={{ true: c.primary, false: c.border }}
          />
        </View>
      </Card>

      <Card>
        <Muted>{tr.more.apiUrl}</Muted>
        <Body>{getApiUrl()}</Body>
      </Card>

      <Button title={tr.more.logout} variant="danger" onPress={onLogout} fullWidth />
    </ScrollView>
  );
}
