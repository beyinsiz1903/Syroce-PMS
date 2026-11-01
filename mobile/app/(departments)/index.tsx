import React from 'react';
import { ActivityIndicator, RefreshControl, ScrollView, View } from 'react-native';
import { Ionicons } from '@expo/vector-icons';
import { useRouter } from 'expo-router';
import type { Href } from 'expo-router';
import { useQuery } from '@tanstack/react-query';
import { Badge, Body, Button, Card, H1, H2, Muted, webCenter } from '../../src/components/ui';
import { DepartmentTile } from '../../src/components/department';
import { spacing, useTheme } from '../../src/theme';
import { tr } from '../../src/i18n/tr';
import { useAuthStore } from '../../src/state/authStore';
import { ROUTES } from '../../src/navigation/routes';
import {
  groupHubTiles,
  hubModuleState,
  visibleHubTiles,
  type HubTile,
} from '../../src/utils/departmentScreens';
import { getCurrentSubscription } from '../../src/api/subscription';
import { useOnline } from '../../src/hooks/useOnline';
import { errorStatus } from '../../src/utils/errors';
import { demoPreviewEnabled } from '../../src/utils/previewMode';

// Static metadata for each hub tile. `visibleHubTiles` decides which keys to
// render (and in what order) from the signed-in role, so visibility/order is
// covered by a single unit-tested helper.
const TILE_META: Record<HubTile, { testID: string; title: string; subtitle: string; route: Href; icon: keyof typeof Ionicons.glyphMap }> = {
  spa: {
    testID: 'dept-tile-spa',
    title: tr.departments.spa.title,
    subtitle: tr.departments.spa.tileSubtitle,
    route: ROUTES.spa,
    icon: 'flower-outline',
  },
  mice: {
    testID: 'dept-tile-mice',
    title: tr.departments.mice.title,
    subtitle: tr.departments.mice.tileSubtitle,
    route: ROUTES.mice,
    icon: 'people-outline',
  },
  cashier: {
    testID: 'dept-tile-cashier',
    title: tr.departments.cashier.title,
    subtitle: tr.departments.cashier.tileSubtitle,
    route: ROUTES.cashier,
    icon: 'wallet-outline',
  },
  accounting: {
    testID: 'dept-tile-accounting',
    title: tr.departments.accounting.title,
    subtitle: tr.departments.accounting.tileSubtitle,
    route: ROUTES.accounting,
    icon: 'calculator-outline',
  },
  maintenance: {
    testID: 'dept-tile-maintenance',
    title: tr.departments.maintenance.title,
    subtitle: tr.departments.maintenance.tileSubtitle,
    route: ROUTES.maintenance,
    icon: 'construct-outline',
  },
  procurement: {
    testID: 'dept-tile-procurement',
    title: tr.departments.procurement.title,
    subtitle: tr.departments.procurement.tileSubtitle,
    route: ROUTES.procurement,
    icon: 'cube-outline',
  },
  hr: {
    testID: 'dept-tile-hr',
    title: tr.departments.hr.title,
    subtitle: tr.departments.hr.tileSubtitle,
    route: ROUTES.hr,
    icon: 'person-outline',
  },
  revenue: {
    testID: 'dept-tile-revenue',
    title: tr.departments.revenue.title,
    subtitle: tr.departments.revenue.tileSubtitle,
    route: ROUTES.revenue,
    icon: 'trending-up-outline',
  },
  pos: {
    testID: 'dept-tile-pos',
    title: tr.departments.pos.title,
    subtitle: tr.departments.pos.tileSubtitle,
    route: ROUTES.pos,
    icon: 'restaurant-outline',
  },
};

// Departments hub. Each entry is shown ONLY when the signed-in user holds the
// matching backend entitlement (mirrors require_spa_ops / require_mice_ops).
// This gating is cosmetic — the backend still enforces every action.
export default function DepartmentsHub() {
  const c = useTheme();
  const router = useRouter();
  const user = useAuthStore((s) => s.user);
  const financeReports = useAuthStore((s) => s.financeReports);
  const maintenanceAccess = useAuthStore((s) => s.maintenanceAccess);
  const online = useOnline();
  const tiles = visibleHubTiles(user?.role, {
    user: user || undefined,
    financeReports,
    maintenanceAccess,
    pageAccess: user?.page_access,
    moduleScopes: user?.module_scopes,
  });
  const demoPreview = demoPreviewEnabled(__DEV__, process.env.EXPO_PUBLIC_PREVIEW_MODE, process.env.EXPO_PUBLIC_API_URL);
  const subscription = useQuery({
    queryKey: ['current-subscription', user?.tenant_id || user?.hotel_id],
    queryFn: getCurrentSubscription,
    staleTime: 5 * 60 * 1000,
    enabled: !demoPreview && tiles.length > 0,
    retry: (attempt, error) => errorStatus(error) !== 403 && attempt < 1,
  });

  // Do not let an all-access fixture user advertise modules that the local
  // read-only service does not implement. Live role/subscription gates below
  // remain unchanged; absence in this demo says nothing about live readiness.
  if (demoPreview) return (
    <ScrollView style={{ flex: 1, backgroundColor: c.bg }} contentContainerStyle={[{ padding: spacing.lg, gap: spacing.lg, paddingBottom: spacing.xl }, webCenter]} testID="demo-preview-scope">
      <Badge label="SALT OKUNUR DEMO" tone="warning" icon="information-circle-outline" />
      <H1>Önizleme kapsamı</H1>
      <Muted>Bu ortam günlük mobil PMS ekranlarını örnek verilerle gösterir. Kayıt, tahsilat veya durum değişiklikleri canlı sisteme gönderilmez.</Muted>
      <Card style={{ gap: spacing.md }}>
        <H2>İnceleyebileceğiniz ekranlar</H2>
        <Button title="Bugün · günlük operasyon" icon="today-outline" onPress={() => router.push(ROUTES.frontdesk)} fullWidth />
        <Button title="Takvim · rezervasyonlar" icon="calendar-outline" onPress={() => router.push(ROUTES.reservationCalendar)} variant="secondary" fullWidth />
        <Button title="Odalar · doluluk ve temizlik" icon="bed-outline" onPress={() => router.push(ROUTES.frontdeskRooms)} variant="secondary" fullWidth />
        <Button title="Örnek rezervasyon · ödemeler" icon="wallet-outline" onPress={() => router.push({ pathname: ROUTES.reservationDetail, params: { id: 'booking-ayse' } })} variant="secondary" fullWidth />
      </Card>
      <Card style={{ gap: spacing.md }}>
        <H2>Bu önizlemede yer almayanlar</H2>
        <Muted>Bu departmanların veri ve işlem akışları yerel demoya bağlı değil. Bu nedenle çalışır bağlantı olarak gösterilmiyor; canlı kurulumda ayrıca doğrulanmaları gerekir.</Muted>
        {tiles.map((key) => <View key={key} style={{ gap: spacing.xs }}><Body style={{ fontWeight: '600' }}>{TILE_META[key].title}</Body><Muted>Bu önizlemede yok</Muted></View>)}
      </Card>
    </ScrollView>
  );

  const snapshot = !online || subscription.isPending || subscription.isError ? undefined : subscription.data;
  const groups = groupHubTiles(tiles);
  const unknownAccess = tiles.some((tile) => hubModuleState(tile, snapshot) === 'unknown');
  const restricted = errorStatus(subscription.error) === 403;
  const checking = subscription.isPending && online;
  const reload = () => { void subscription.refetch(); };

  return (
    <ScrollView
      testID="departments-hub"
      style={{ flex: 1, backgroundColor: c.bg }}
      contentContainerStyle={[
        { padding: spacing.lg, gap: spacing.md, paddingBottom: spacing.xl },
        webCenter,
      ]}
      refreshControl={<RefreshControl refreshing={subscription.isFetching && !subscription.isPending} onRefresh={reload} tintColor={c.primary} />}
    >
      <View>
        <H1>{tr.departments.title}</H1>
        <Muted style={{ marginTop: spacing.xs }}>{tr.departments.subtitle}</Muted>
        <Muted style={{ marginTop: spacing.sm }}>{tr.departments.workspaceHint}</Muted>
      </View>

      {tiles.length > 0 && (checking || subscription.isError || !online || unknownAccess) ? (
        <Card testID="department-access-notice" style={{ gap: spacing.sm }}>
          <View style={{ flexDirection: 'row', alignItems: 'center', gap: spacing.sm }}>
            {checking ? <ActivityIndicator color={c.primary} /> : <Ionicons name="information-circle-outline" size={22} color={c.textMuted} />}
            <Body style={{ flex: 1, fontWeight: '600' }} accessibilityLiveRegion="polite">
              {!online ? tr.app.offline : checking ? tr.departments.accessLoading : restricted ? tr.departments.accessRestricted : tr.departments.accessUnavailable}
            </Body>
          </View>
          <Muted>{tr.departments.coreAccessHint}</Muted>
          {!checking ? <Button title={tr.app.retry} icon="refresh" variant="outline" onPress={reload} disabled={!online || subscription.isFetching} /> : null}
        </Card>
      ) : null}

      {groups.map((group) => (
        <View key={group.key} style={{ gap: spacing.sm }} testID={`department-group-${group.key}`}>
          <H2 accessibilityRole="header" style={{ fontSize: 17, marginTop: spacing.sm }}>{tr.departments.groups[group.key]}</H2>
          <Card padded={false}>
            {group.tiles.map((key, index) => {
              const meta = TILE_META[key];
              const state = hubModuleState(key, snapshot);
              return (
                <DepartmentTile
                  key={key}
                  testID={meta.testID}
                  title={meta.title}
                  subtitle={meta.subtitle}
                  icon={meta.icon}
                  grouped
                  last={index === group.tiles.length - 1}
                  disabled={state !== 'enabled'}
                  statusText={state === 'unknown' ? tr.departments.accessUnknown : state === 'disabled' ? tr.departments.accessDisabled : undefined}
                  onPress={() => router.push(meta.route)}
                />
              );
            })}
          </Card>
        </View>
      ))}

      {tiles.length === 0 ? (
        <Card>
          <Body style={{ fontWeight: '600' }}>{tr.departments.none}</Body>
          <Muted style={{ marginTop: spacing.sm }}>{tr.departments.noAccessHint}</Muted>
        </Card>
      ) : null}
    </ScrollView>
  );
}
