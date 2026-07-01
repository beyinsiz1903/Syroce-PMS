import React, { useEffect, useState } from 'react';
import { Alert, ScrollView, Switch } from 'react-native';
import { useRouter } from 'expo-router';
import type { Href } from 'expo-router';
import { Ionicons } from '@expo/vector-icons';
import { Button, Card, H1, H2, ListGroup, ListRow, Muted } from '../../src/components/ui';
import { RoleSwitcher } from '../../src/components/RoleSwitcher';
import ThemeModeSelector from '../../src/components/ThemeModeSelector';
import { spacing, useTheme } from '../../src/theme';
import { tr } from '../../src/i18n/tr';
import { useAuthStore } from '../../src/state/authStore';
import { ROUTES } from '../../src/navigation/routes';
import { useSettingsStore } from '../../src/state/settingsStore';
import { getApiUrl } from '../../src/api/client';
import { authenticateBiometric, getBiometricCapability } from '../../src/biometrics/lock';
import { getLastPushStatus, type PushRegistrationStatus } from '../../src/notifications/push';

type Shortcut = {
  key: string;
  label: string;
  route: Href;
  visible: boolean;
  icon: keyof typeof Ionicons.glyphMap;
};

// GM "More" surfaces the management areas a manager (or all-access user) may
// reach, in the same Settings-style ListRow list the rest of the app uses.
// Each entry is gated by the same entitlement flags the profile hub uses;
// AuthGate admits the targets and the backend enforces every action inside —
// this list only reveals entry points, it never grants access.
export default function GMMoreScreen() {
  const c = useTheme();
  const router = useRouter();
  const { user, logout } = useAuthStore();
  const allAccess = useAuthStore((s) => s.allAccess);
  const financeReports = useAuthStore((s) => s.financeReports);
  const spaAccess = useAuthStore((s) => s.spaAccess);
  const miceAccess = useAuthStore((s) => s.miceAccess);
  const maintenanceAccess = useAuthStore((s) => s.maintenanceAccess);
  const procurementAccess = useAuthStore((s) => s.procurementAccess);
  const hrAccess = useAuthStore((s) => s.hrAccess);
  const revenueAccess = useAuthStore((s) => s.revenueAccess);
  const posAccess = useAuthStore((s) => s.posAccess);
  const deptAccess = useAuthStore((s) => s.deptAccess);

  const biometricLock = useSettingsStore((s) => s.biometricLock);
  const setBiometricLock = useSettingsStore((s) => s.setBiometricLock);

  const [bioAvailable, setBioAvailable] = useState<boolean>(false);
  const [bioLabel, setBioLabel] = useState<string>('Biyometrik');
  const [pushStatus, setPushStatus] = useState<PushRegistrationStatus>(getLastPushStatus());

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

  // Poll the push registration outcome so the indicator updates without a
  // screen reload — registerForPush() runs asynchronously in AuthGate after
  // sign-in. Stops polling once we have a definitive result.
  useEffect(() => {
    if (pushStatus !== 'unknown') return;
    const t = setInterval(() => {
      const next = getLastPushStatus();
      if (next !== 'unknown') {
        setPushStatus(next);
        clearInterval(t);
      }
    }, 500);
    return () => clearInterval(t);
  }, [pushStatus]);

  const onLogout = () => {
    Alert.alert(tr.more.logout, '', [
      { text: tr.app.cancel, style: 'cancel' },
      { text: tr.more.logout, style: 'destructive', onPress: () => logout() },
    ]);
  };

  const onToggleBiometric = async (next: boolean) => {
    if (!next) {
      await setBiometricLock(false);
      return;
    }
    if (!bioAvailable) {
      Alert.alert(tr.more.biometricLock, tr.more.biometricUnavailable);
      return;
    }
    const ok = await authenticateBiometric(`${tr.more.biometricLock}: ${bioLabel}`);
    if (ok) await setBiometricLock(true);
  };

  const shortcuts: Shortcut[] = [
    {
      key: 'departments',
      label: tr.manager.shortcutDepartments,
      route: ROUTES.departments,
      visible: deptAccess,
      icon: 'grid-outline',
    },
    {
      key: 'accounting',
      label: tr.hub.moduleAccounting,
      route: ROUTES.accounting,
      visible: allAccess || financeReports,
      icon: 'calculator-outline',
    },
    {
      key: 'cashier',
      label: tr.hub.moduleCashier,
      route: ROUTES.cashier,
      visible: allAccess || financeReports,
      icon: 'cash-outline',
    },
    {
      key: 'revenue',
      label: tr.manager.shortcutRevenue,
      route: ROUTES.revenue,
      visible: allAccess || revenueAccess,
      icon: 'trending-up-outline',
    },
    {
      key: 'hr',
      label: tr.manager.shortcutHr,
      route: ROUTES.hr,
      visible: allAccess || hrAccess,
      icon: 'people-outline',
    },
    {
      key: 'procurement',
      label: tr.manager.shortcutProcurement,
      route: ROUTES.procurement,
      visible: allAccess || procurementAccess,
      icon: 'cart-outline',
    },
    {
      key: 'mice',
      label: tr.hub.moduleMice,
      route: ROUTES.mice,
      visible: allAccess || miceAccess,
      icon: 'easel-outline',
    },
    {
      key: 'spa',
      label: tr.hub.moduleSpa,
      route: ROUTES.spa,
      visible: allAccess || spaAccess,
      icon: 'flower-outline',
    },
    {
      key: 'pos',
      label: tr.manager.shortcutPos,
      route: ROUTES.pos,
      visible: allAccess || posAccess,
      icon: 'card-outline',
    },
    {
      key: 'maintenance',
      label: tr.hub.moduleMaintenance,
      route: ROUTES.maintenance,
      visible: allAccess || maintenanceAccess,
      icon: 'construct-outline',
    },
  ];
  const visibleShortcuts = shortcuts.filter((s) => s.visible);

  const pushLabel =
    pushStatus === 'registered'
      ? tr.more.pushOn
      : pushStatus === 'denied'
      ? tr.more.pushDenied
      : pushStatus === 'error'
      ? tr.more.pushError
      : pushStatus === 'unavailable'
      ? tr.more.pushOff
      : tr.more.pushPending;

  return (
    <ScrollView
      style={{ flex: 1, backgroundColor: c.bg }}
      contentContainerStyle={{ padding: spacing.lg, gap: spacing.md, paddingBottom: 120 }}
    >
      <H1>{tr.manager.moreTitle}</H1>

      {/* ── Profile ── */}
      <Card>
        <H2 numberOfLines={1}>{user?.name || user?.username || user?.email || '—'}</H2>
        {user?.email ? <Muted>{user.email}</Muted> : null}
        <Muted>Rol: {user?.role || '—'}</Muted>
        {user?.hotel_id ? <Muted>Otel ID: {user.hotel_id}</Muted> : null}
      </Card>

      <RoleSwitcher />

      <ThemeModeSelector />

      {/* ── Management shortcuts ── */}
      {visibleShortcuts.length === 0 ? (
        <Card>
          <Muted>{tr.manager.noShortcuts}</Muted>
        </Card>
      ) : (
        <ListGroup title={tr.manager.shortcutsTitle} testID="gm-more-shortcuts">
          {visibleShortcuts.map((s, i) => (
            <ListRow
              key={s.key}
              testID={`gm-more-${s.key}`}
              icon={s.icon}
              label={s.label}
              onPress={() => router.push(s.route)}
              last={i === visibleShortcuts.length - 1}
            />
          ))}
        </ListGroup>
      )}

      {/* ── Settings ── */}
      <ListGroup title={tr.manager.settingsTitle}>
        <ListRow
          testID="smoke-biometric-toggle"
          icon="finger-print-outline"
          label={tr.more.biometricLock}
          sublabel={
            bioAvailable
              ? `${tr.more.biometricLockHint} (${bioLabel})`
              : tr.more.biometricUnavailable
          }
          showChevron={false}
          right={
            <Switch
              value={biometricLock}
              disabled={!bioAvailable && !biometricLock}
              onValueChange={onToggleBiometric}
              accessibilityLabel={tr.more.biometricLock}
              trackColor={{ true: c.primary, false: c.border }}
            />
          }
        />
        <ListRow
          testID="smoke-push-status"
          icon="notifications-outline"
          label={tr.more.pushStatus}
          value={pushLabel}
          showChevron={false}
        />
        <ListRow
          icon="server-outline"
          label={tr.more.apiUrl}
          value={getApiUrl()}
          showChevron={false}
          last
        />
      </ListGroup>

      <Button title={tr.more.logout} variant="danger" onPress={onLogout} fullWidth />
    </ScrollView>
  );
}
