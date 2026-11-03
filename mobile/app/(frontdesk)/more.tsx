import React, { useEffect, useState } from 'react';
import { Alert, ScrollView, Switch, View } from 'react-native';
import { useRouter } from 'expo-router';
import { Body, Button, Card, H1, H2, Muted, webCenter } from '../../src/components/ui';
import { RoleSwitcher } from '../../src/components/RoleSwitcher';
import ThemeModeSelector from '../../src/components/ThemeModeSelector';
import { NightScreen } from '../../src/components/NightScreen';
import { spacing, useTheme } from '../../src/theme';
import { tr } from '../../src/i18n/tr';
import { useAuthStore } from '../../src/state/authStore';
import { ROUTES } from '../../src/navigation/routes';
import { mobileTargetAllowed } from '../../src/navigation/routeAccess';
import { useSettingsStore } from '../../src/state/settingsStore';
import { getApiUrl } from '../../src/api/client';
import {
  authenticateBiometric,
  getBiometricCapability,
} from '../../src/biometrics/lock';
import { PushPreferences } from '../../src/components/PushPreferences';
import { demoPreviewEnabled } from '../../src/utils/previewMode';
import { LegalSupportLinks } from '../../src/components/LegalSupportLinks';

export default function MoreScreen() {
  const c = useTheme();
  const router = useRouter();
  const demoPreview = demoPreviewEnabled(__DEV__, process.env.EXPO_PUBLIC_PREVIEW_MODE, process.env.EXPO_PUBLIC_API_URL);
  const { user, logout } = useAuthStore();
  const deptAccess = useAuthStore((s) => s.deptAccess);
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
      contentContainerStyle={[{ padding: spacing.lg, gap: spacing.md, paddingBottom: spacing.xl }, webCenter]}
    >
      <H1>{tr.more.profile}</H1>
      <Card>
        <H2>{user?.name || user?.username || user?.email || '—'}</H2>
        <Muted>{user?.email}</Muted>
        <Muted>Rol: {user?.role || '—'}</Muted>
        {user?.hotel_id ? <Muted>Otel ID: {user.hotel_id}</Muted> : null}
      </Card>

      {!demoPreview ? <RoleSwitcher /> : (
        <Card accent={c.warning}><Muted>Salt okunur tasarım önizlemesi. Bu demo günlük PMS ekranlarını kapsar; diğer rol deneyimleri burada doğrulanmaz.</Muted></Card>
      )}

      {[ROUTES.frontdeskKbs, ROUTES.reservations, ROUTES.availability, ROUTES.frontdeskGuests, ROUTES.frontdeskReports].some(route => mobileTargetAllowed(user, route)) && <Card style={{ gap: spacing.sm }}>
        <H2>Operasyon kısayolları</H2>
        <Muted>Günlük sekmelerin dışında kalan araçlar.</Muted>
        {mobileTargetAllowed(user, ROUTES.frontdeskKbs) && <Button title="KBS bildirimleri" icon="shield-checkmark-outline" variant="secondary" onPress={() => router.push(ROUTES.frontdeskKbs)} testID="more-kbs" fullWidth />}
        {mobileTargetAllowed(user, ROUTES.reservations) && <Button
          title={tr.tabs.bookings}
          icon="reader-outline"
          variant="secondary"
          onPress={() => router.push(ROUTES.reservations)}
          testID="more-reservations"
          fullWidth
        />}
        {mobileTargetAllowed(user, ROUTES.availability) && <Button
          title={tr.availability.title}
          icon="calendar-outline"
          variant="secondary"
          onPress={() => router.push(ROUTES.availability)}
          fullWidth
        />}
        {mobileTargetAllowed(user, ROUTES.frontdeskGuests) && <Button
          title={tr.tabs.guests}
          icon="people-outline"
          variant="secondary"
          onPress={() => router.push(ROUTES.frontdeskGuests)}
          fullWidth
        />}
          {mobileTargetAllowed(user, ROUTES.frontdeskReports) && <Button
            title={tr.manager.reportsTitle}
            icon="bar-chart-outline"
            variant="secondary"
            onPress={() => router.push(ROUTES.frontdeskReports)}
            testID="more-reports"
            fullWidth
          />}
      </Card>}

      <ThemeModeSelector />

      <NightScreen inline />

      {deptAccess ? (
        <Card>
          <H2>{tr.departments.title}</H2>
          <Muted style={{ marginBottom: spacing.md }}>{tr.departments.subtitle}</Muted>
          <Button
            testID="more-departments"
            title={tr.departments.open}
            variant="secondary"
            onPress={() => router.push(ROUTES.departments)}
            fullWidth
          />
        </Card>
      ) : null}

      <Card>
        <View style={{ flexDirection: 'row', alignItems: 'center', justifyContent: 'space-between', gap: spacing.sm }}>
          <View style={{ flex: 1, paddingRight: spacing.sm }}>
            <H2>{tr.more.biometricLock}</H2>
            <Muted>
              {bioAvailable ? `${tr.more.biometricLockHint} (${bioLabel})` : tr.more.biometricUnavailable}
            </Muted>
          </View>
          <Switch
            testID="smoke-biometric-toggle"
            value={biometricLock}
            disabled={!bioAvailable && !biometricLock}
            onValueChange={onToggleBiometric}
            accessibilityLabel={tr.more.biometricLock}
            trackColor={{ true: c.primary, false: c.border }}
          />
        </View>
      </Card>

      <PushPreferences />

      <Card>
        <Muted>{tr.more.apiUrl}</Muted>
        <Body>{getApiUrl()}</Body>
      </Card>

      <LegalSupportLinks />
      <Button title={tr.more.logout} variant="danger" onPress={onLogout} fullWidth />
    </ScrollView>
  );
}
