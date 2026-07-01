import React, { useCallback } from 'react';
import { Pressable, RefreshControl, ScrollView, Text, View } from 'react-native';
import { useQuery } from '@tanstack/react-query';
import { useRouter } from 'expo-router';
import type { Href } from 'expo-router';
import { Ionicons } from '@expo/vector-icons';
import { Badge, Body, Card, H1, H2, Muted, SkeletonCard } from '../../src/components/ui';
import { KpiCard, KpiRow } from '../../src/components/KpiCard';
import { OfflineBanner } from '../../src/components/OfflineBanner';
import { radius, spacing, useTheme } from '../../src/theme';
import { tr } from '../../src/i18n/tr';
import { useAuthStore } from '../../src/state/authStore';
import { ROUTES } from '../../src/navigation/routes';
import { isOffline } from '../../src/utils/errors';
import { FeedItem, getFeed, getToday } from '../../src/api/hub';

const TR_MONTHS = [
  'Ocak', 'Şubat', 'Mart', 'Nisan', 'Mayıs', 'Haziran',
  'Temmuz', 'Ağustos', 'Eylül', 'Ekim', 'Kasım', 'Aralık',
];
const TR_DAYS = ['Pazar', 'Pazartesi', 'Salı', 'Çarşamba', 'Perşembe', 'Cuma', 'Cumartesi'];

// Format an ISO 'YYYY-MM-DD' (or today) into Turkish "12 Haziran 2026, Cuma".
// Manual formatting keeps it Hermes/web-safe without relying on Intl locale data.
function formatTrDate(iso?: string): string {
  let d: Date;
  if (iso && /^\d{4}-\d{2}-\d{2}/.test(iso)) {
    const [y, m, day] = iso.slice(0, 10).split('-').map((n) => parseInt(n, 10));
    d = new Date(y, m - 1, day);
  } else {
    d = new Date();
  }
  if (Number.isNaN(d.getTime())) d = new Date();
  return `${d.getDate()} ${TR_MONTHS[d.getMonth()]} ${d.getFullYear()}, ${TR_DAYS[d.getDay()]}`;
}

function greeting(): string {
  const h = new Date().getHours();
  if (h < 12) return tr.hub.hubGreetingMorning;
  if (h < 18) return tr.hub.hubGreetingDay;
  return tr.hub.hubGreetingEvening;
}

function feedTone(priority: string): 'danger' | 'warning' | 'default' {
  if (priority === 'urgent') return 'danger';
  if (priority === 'high') return 'warning';
  return 'default';
}

type Shortcut = {
  key: string;
  label: string;
  route: Href;
  visible: boolean;
  icon: keyof typeof Ionicons.glyphMap;
};

function ShortcutTile({ item, onPress }: { item: Shortcut; onPress: () => void }) {
  const c = useTheme();
  return (
    <Pressable
      onPress={onPress}
      testID={`smoke-hub-shortcut-${item.key}`}
      accessibilityRole="button"
      accessibilityLabel={item.label}
      style={({ pressed }) => ({
        width: '48%',
        opacity: pressed ? 0.7 : 1,
      })}
    >
      <Card style={{ alignItems: 'center', gap: spacing.sm, paddingVertical: spacing.lg }}>
        <View
          style={{
            width: 44,
            height: 44,
            borderRadius: radius.pill,
            backgroundColor: c.primarySoft,
            alignItems: 'center',
            justifyContent: 'center',
          }}
        >
          <Ionicons name={item.icon} size={22} color={c.primary} />
        </View>
        <Text
          style={{ color: c.text, fontSize: 13, fontWeight: '600', textAlign: 'center' }}
          numberOfLines={2}
        >
          {item.label}
        </Text>
      </Card>
    </Pressable>
  );
}

export default function HubScreen() {
  const c = useTheme();
  const router = useRouter();
  const {
    user,
    role,
    allAccess,
    spaAccess,
    miceAccess,
    maintenanceAccess,
    procurementAccess,
    hrAccess,
    revenueAccess,
    posAccess,
    financeReports,
    approvalsAccess,
  } = useAuthStore();

  const today = useQuery({ queryKey: ['hub-today'], queryFn: getToday });
  const feed = useQuery({ queryKey: ['hub-feed'], queryFn: () => getFeed({ limit: 50 }) });

  const refreshing =
    (today.isFetching && !today.isLoading) || (feed.isFetching && !feed.isLoading);
  const onRefresh = useCallback(() => {
    today.refetch();
    feed.refetch();
  }, [today, feed]);

  const offline =
    (today.isError && isOffline(today.error)) || (feed.isError && isOffline(feed.error));
  const data = today.data;
  const displayName = user?.name || user?.username || user?.email || '—';
  const hotelName = data?.hotel_name ?? null;

  const canApprove = approvalsAccess || allAccess;
  const pendingApprovals = data?.pending_approvals ?? 0;

  // Permission-filtered department shortcuts. Mirrors the Profile module grid
  // (cosmetic affordance only — AuthGate admits the target and the backend
  // enforces every action inside; this list never grants access). The guest
  // app surface is offered to all-access roles only.
  const shortcuts: Shortcut[] = [
    {
      key: 'frontdesk',
      label: tr.hub.moduleFrontdesk,
      route: ROUTES.frontdesk,
      visible: allAccess || role === 'front_desk',
      icon: 'desktop-outline',
    },
    {
      key: 'housekeeping',
      label: tr.hub.moduleHousekeeping,
      route: ROUTES.housekeeping,
      visible: allAccess || role === 'housekeeping',
      icon: 'brush-outline',
    },
    {
      key: 'manager',
      label: tr.hub.moduleManager,
      route: ROUTES.gm,
      visible: allAccess || role === 'gm',
      icon: 'briefcase-outline',
    },
    {
      key: 'cashier',
      label: tr.hub.moduleCashier,
      route: ROUTES.cashier,
      visible: allAccess || financeReports,
      icon: 'cash-outline',
    },
    {
      key: 'accounting',
      label: tr.hub.moduleAccounting,
      route: ROUTES.accounting,
      visible: allAccess || financeReports,
      icon: 'calculator-outline',
    },
    {
      key: 'maintenance',
      label: tr.hub.moduleMaintenance,
      route: ROUTES.maintenance,
      visible: allAccess || maintenanceAccess,
      icon: 'construct-outline',
    },
    {
      key: 'spa',
      label: tr.hub.moduleSpa,
      route: ROUTES.spa,
      visible: allAccess || spaAccess,
      icon: 'flower-outline',
    },
    {
      key: 'mice',
      label: tr.hub.moduleMice,
      route: ROUTES.mice,
      visible: allAccess || miceAccess,
      icon: 'easel-outline',
    },
    {
      key: 'procurement',
      label: tr.hub.moduleProcurement,
      route: ROUTES.procurement,
      visible: allAccess || procurementAccess,
      icon: 'cart-outline',
    },
    {
      key: 'hr',
      label: tr.hub.moduleHr,
      route: ROUTES.hr,
      visible: allAccess || hrAccess,
      icon: 'people-outline',
    },
    {
      key: 'revenue',
      label: tr.hub.moduleRevenue,
      route: ROUTES.revenue,
      visible: allAccess || revenueAccess,
      icon: 'trending-up-outline',
    },
    {
      key: 'pos',
      label: tr.hub.modulePos,
      route: ROUTES.pos,
      visible: allAccess || posAccess,
      icon: 'fast-food-outline',
    },
    {
      key: 'guest',
      label: tr.hub.moduleGuestApp,
      route: ROUTES.guest,
      visible: allAccess,
      icon: 'phone-portrait-outline',
    },
  ];
  const visibleShortcuts = shortcuts.filter((s) => s.visible);

  const feedItems: FeedItem[] = feed.data?.items ?? [];
  const feedPreview = feedItems.slice(0, 4);

  return (
    <View style={{ flex: 1, backgroundColor: c.bg }} testID="smoke-home-hub">
      <ScrollView
        contentContainerStyle={{ padding: spacing.lg, paddingBottom: 120, gap: spacing.md }}
        refreshControl={
          <RefreshControl refreshing={refreshing} onRefresh={onRefresh} tintColor={c.primary} />
        }
      >
        <OfflineBanner visible={offline} />

        {/* Identity / kimlik alanı: selamlama + isim, rol, otel, tarih */}
        <View>
          <Muted>{greeting()}</Muted>
          <H1 numberOfLines={1}>{displayName}</H1>
          <View
            style={{
              flexDirection: 'row',
              alignItems: 'center',
              flexWrap: 'wrap',
              gap: spacing.sm,
              marginTop: spacing.xs,
            }}
          >
            {user?.role ? <Badge label={user.role} tone="primary" /> : null}
            {hotelName ? (
              <Muted numberOfLines={1} style={{ flexShrink: 1 }}>
                {hotelName}
              </Muted>
            ) : null}
          </View>
          <Muted style={{ marginTop: spacing.xs }}>{formatTrDate(data?.date)}</Muted>
        </View>

        {/* "Bugün" operasyon KPI'ları — yalnızca gerçek veri */}
        <H2 style={{ marginTop: spacing.sm }}>{tr.hub.hubTodayKpi}</H2>
        {today.isLoading ? (
          <>
            <KpiRow>
              <SkeletonCard />
              <SkeletonCard />
            </KpiRow>
            <KpiRow>
              <SkeletonCard />
              <SkeletonCard />
            </KpiRow>
          </>
        ) : today.isError ? (
          <Card>
            <Muted>{tr.hub.loadError}</Muted>
          </Card>
        ) : (
          <>
            <KpiRow>
              <KpiCard
                testID="hub-occupancy"
                icon="bed"
                label={tr.hub.occupancy}
                value={`%${data?.occupancy_pct ?? 0}`}
                tone={(data?.occupancy_pct ?? 0) > 0 ? 'info' : 'default'}
              />
              <KpiCard
                testID="hub-open-tasks"
                icon="list"
                label={tr.hub.pendingTasksKpi}
                value={String(data?.open_tasks ?? 0)}
                tone={(data?.open_tasks ?? 0) > 0 ? 'info' : 'default'}
              />
            </KpiRow>
            <KpiRow>
              <KpiCard
                testID="hub-checkins"
                icon="log-in"
                label={tr.hub.checkIns}
                value={String(data?.check_ins ?? 0)}
                tone={(data?.check_ins ?? 0) > 0 ? 'success' : 'default'}
              />
              <KpiCard
                testID="hub-checkouts"
                icon="log-out"
                label={tr.hub.checkOuts}
                value={String(data?.check_outs ?? 0)}
                tone={(data?.check_outs ?? 0) > 0 ? 'warning' : 'default'}
              />
            </KpiRow>
            <KpiRow>
              <KpiCard
                testID="hub-open-faults"
                icon="construct"
                label={tr.hub.openFaults}
                value={String(data?.open_faults ?? 0)}
                tone={(data?.open_faults ?? 0) > 0 ? 'danger' : 'default'}
              />
              <View style={{ flex: 1 }} />
            </KpiRow>
          </>
        )}

        {/* "Onaylarım" — onaycı roller için HUB'dan erişilebilir */}
        {canApprove ? (
          <Pressable
            testID="smoke-hub-approvals"
            accessibilityRole="button"
            accessibilityLabel={tr.hub.approvalsCta}
            onPress={() => router.push(ROUTES.homeApprovals)}
            style={({ pressed }) => ({ opacity: pressed ? 0.7 : 1 })}
          >
            <Card
              style={{
                flexDirection: 'row',
                alignItems: 'center',
                gap: spacing.md,
                borderLeftWidth: 3,
                borderLeftColor: c.primary,
              }}
            >
              <Ionicons name="checkmark-done-circle-outline" size={26} color={c.primary} />
              <View style={{ flex: 1 }}>
                <Body style={{ fontWeight: '600' }}>{tr.hub.approvalsCta}</Body>
                <Muted>{tr.hub.approvalsCtaHint}</Muted>
              </View>
              {pendingApprovals > 0 ? (
                <Badge label={String(pendingApprovals)} tone="warning" />
              ) : null}
              <Ionicons name="chevron-forward" size={18} color={c.textMuted} />
            </Card>
          </Pressable>
        ) : null}

        {/* Akıllı bildirim akışı (önizleme) */}
        <View
          style={{
            flexDirection: 'row',
            alignItems: 'center',
            justifyContent: 'space-between',
            marginTop: spacing.sm,
          }}
        >
          <H2>{tr.hub.hubFeedTitle}</H2>
          <Pressable
            testID="smoke-hub-feed-all"
            accessibilityRole="button"
            accessibilityLabel={tr.hub.hubFeedSeeAll}
            onPress={() => router.push(ROUTES.homeNotifications)}
            hitSlop={8}
          >
            <Text style={{ color: c.primary, fontSize: 13, fontWeight: '600' }}>
              {tr.hub.hubFeedSeeAll}
            </Text>
          </Pressable>
        </View>
        <View testID="smoke-hub-feed">
          {feed.isLoading ? (
            <SkeletonCard />
          ) : feed.isError ? (
            <Card>
              <Muted>{tr.hub.loadError}</Muted>
            </Card>
          ) : feedPreview.length === 0 ? (
            <Card>
              <Muted>{tr.hub.hubFeedEmpty}</Muted>
            </Card>
          ) : (
            feedPreview.map((item) => (
              <Pressable
                key={`${item.source}-${item.id}`}
                onPress={() => router.push(ROUTES.homeNotifications)}
                style={({ pressed }) => ({ opacity: pressed ? 0.7 : 1 })}
              >
                <Card
                  style={{
                    marginBottom: spacing.sm,
                    borderLeftWidth: item.read ? 1 : 3,
                    borderLeftColor: item.read ? c.border : c.primary,
                  }}
                >
                  <View
                    style={{
                      flexDirection: 'row',
                      justifyContent: 'space-between',
                      gap: spacing.sm,
                    }}
                  >
                    <Body style={{ flex: 1, fontWeight: item.read ? '400' : '600' }}>
                      {item.title || '—'}
                    </Body>
                    {item.priority && item.priority !== 'normal' ? (
                      <Badge label={item.priority} tone={feedTone(item.priority)} />
                    ) : null}
                  </View>
                  {item.message ? (
                    <Muted style={{ marginTop: spacing.xs }} numberOfLines={2}>
                      {item.message}
                    </Muted>
                  ) : null}
                </Card>
              </Pressable>
            ))
          )}
        </View>

        {/* İzin filtreli departman kısayolları */}
        <H2 style={{ marginTop: spacing.sm }}>{tr.hub.shortcutsTitle}</H2>
        {visibleShortcuts.length === 0 ? (
          <Card>
            <Muted testID="smoke-hub-no-shortcuts">{tr.hub.noModules}</Muted>
          </Card>
        ) : (
          <View
            testID="smoke-hub-shortcuts"
            style={{
              flexDirection: 'row',
              flexWrap: 'wrap',
              justifyContent: 'space-between',
              gap: spacing.md,
            }}
          >
            {visibleShortcuts.map((s) => (
              <ShortcutTile key={s.key} item={s} onPress={() => router.push(s.route)} />
            ))}
          </View>
        )}
      </ScrollView>
    </View>
  );
}
