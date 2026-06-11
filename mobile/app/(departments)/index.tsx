import React from 'react';
import { ScrollView, View } from 'react-native';
import { useRouter } from 'expo-router';
import type { Href } from 'expo-router';
import { Card, H1, Muted } from '../../src/components/ui';
import { DepartmentTile } from '../../src/components/department';
import { spacing, useTheme } from '../../src/theme';
import { tr } from '../../src/i18n/tr';
import { useAuthStore } from '../../src/state/authStore';
import { ROUTES } from '../../src/navigation/routes';
import { visibleHubTiles, type HubTile } from '../../src/utils/departmentScreens';

// Static metadata for each hub tile. `visibleHubTiles` decides which keys to
// render (and in what order) from the signed-in role, so visibility/order is
// covered by a single unit-tested helper.
const TILE_META: Record<HubTile, { testID: string; title: string; subtitle: string; route: Href }> = {
  spa: {
    testID: 'dept-tile-spa',
    title: tr.departments.spa.title,
    subtitle: tr.departments.spa.tileSubtitle,
    route: ROUTES.spa,
  },
  mice: {
    testID: 'dept-tile-mice',
    title: tr.departments.mice.title,
    subtitle: tr.departments.mice.tileSubtitle,
    route: ROUTES.mice,
  },
  cashier: {
    testID: 'dept-tile-cashier',
    title: tr.departments.cashier.title,
    subtitle: tr.departments.cashier.tileSubtitle,
    route: ROUTES.cashier,
  },
  accounting: {
    testID: 'dept-tile-accounting',
    title: tr.departments.accounting.title,
    subtitle: tr.departments.accounting.tileSubtitle,
    route: ROUTES.accounting,
  },
  maintenance: {
    testID: 'dept-tile-maintenance',
    title: tr.departments.maintenance.title,
    subtitle: tr.departments.maintenance.tileSubtitle,
    route: ROUTES.maintenance,
  },
  procurement: {
    testID: 'dept-tile-procurement',
    title: tr.departments.procurement.title,
    subtitle: tr.departments.procurement.tileSubtitle,
    route: ROUTES.procurement,
  },
  hr: {
    testID: 'dept-tile-hr',
    title: tr.departments.hr.title,
    subtitle: tr.departments.hr.tileSubtitle,
    route: ROUTES.hr,
  },
  revenue: {
    testID: 'dept-tile-revenue',
    title: tr.departments.revenue.title,
    subtitle: tr.departments.revenue.tileSubtitle,
    route: ROUTES.revenue,
  },
  pos: {
    testID: 'dept-tile-pos',
    title: tr.departments.pos.title,
    subtitle: tr.departments.pos.tileSubtitle,
    route: ROUTES.pos,
  },
};

// Departments hub. Each entry is shown ONLY when the signed-in user holds the
// matching backend entitlement (mirrors require_spa_ops / require_mice_ops).
// This gating is cosmetic — the backend still enforces every action.
export default function DepartmentsHub() {
  const c = useTheme();
  const router = useRouter();
  // Derive visible tiles from the RAW backend role — the store's per-department
  // flags are computed from the same predicates, so this is equivalent but keeps
  // the visibility logic in one unit-tested helper.
  const rawRole = useAuthStore((s) => s.user?.role);
  const tiles = visibleHubTiles(rawRole);

  return (
    <ScrollView
      style={{ flex: 1, backgroundColor: c.bg }}
      contentContainerStyle={{ padding: spacing.lg, gap: spacing.md, paddingBottom: spacing.xl }}
    >
      <View>
        <H1>{tr.departments.title}</H1>
        <Muted style={{ marginTop: spacing.xs }}>{tr.departments.subtitle}</Muted>
      </View>

      {tiles.map((key) => {
        const meta = TILE_META[key];
        return (
          <DepartmentTile
            key={key}
            testID={meta.testID}
            title={meta.title}
            subtitle={meta.subtitle}
            onPress={() => router.push(meta.route)}
          />
        );
      })}

      {tiles.length === 0 ? (
        <Card>
          <Muted>{tr.departments.none}</Muted>
        </Card>
      ) : null}
    </ScrollView>
  );
}
