import React from 'react';
import { ScrollView, View } from 'react-native';
import { useRouter } from 'expo-router';
import { Card, H1, Muted } from '../../src/components/ui';
import { DepartmentTile } from '../../src/components/department';
import { spacing, useTheme } from '../../src/theme';
import { tr } from '../../src/i18n/tr';
import { useAuthStore } from '../../src/state/authStore';
import { ROUTES } from '../../src/navigation/routes';

// Departments hub. Each entry is shown ONLY when the signed-in user holds the
// matching backend entitlement (mirrors require_spa_ops / require_mice_ops).
// This gating is cosmetic — the backend still enforces every action.
export default function DepartmentsHub() {
  const c = useTheme();
  const router = useRouter();
  const spaAccess = useAuthStore((s) => s.spaAccess);
  const miceAccess = useAuthStore((s) => s.miceAccess);
  const accountingAccess = useAuthStore((s) => s.financeReports);
  const maintenanceAccess = useAuthStore((s) => s.maintenanceAccess);

  const anyAccess = spaAccess || miceAccess || accountingAccess || maintenanceAccess;

  return (
    <ScrollView
      style={{ flex: 1, backgroundColor: c.bg }}
      contentContainerStyle={{ padding: spacing.lg, gap: spacing.md, paddingBottom: spacing.xl }}
    >
      <View>
        <H1>{tr.departments.title}</H1>
        <Muted style={{ marginTop: spacing.xs }}>{tr.departments.subtitle}</Muted>
      </View>

      {spaAccess ? (
        <DepartmentTile
          testID="dept-tile-spa"
          title={tr.departments.spa.title}
          subtitle={tr.departments.spa.tileSubtitle}
          onPress={() => router.push(ROUTES.spa)}
        />
      ) : null}

      {miceAccess ? (
        <DepartmentTile
          testID="dept-tile-mice"
          title={tr.departments.mice.title}
          subtitle={tr.departments.mice.tileSubtitle}
          onPress={() => router.push(ROUTES.mice)}
        />
      ) : null}

      {accountingAccess ? (
        <DepartmentTile
          testID="dept-tile-accounting"
          title={tr.departments.accounting.title}
          subtitle={tr.departments.accounting.tileSubtitle}
          onPress={() => router.push(ROUTES.accounting)}
        />
      ) : null}

      {maintenanceAccess ? (
        <DepartmentTile
          testID="dept-tile-maintenance"
          title={tr.departments.maintenance.title}
          subtitle={tr.departments.maintenance.tileSubtitle}
          onPress={() => router.push(ROUTES.maintenance)}
        />
      ) : null}

      {!anyAccess ? (
        <Card>
          <Muted>{tr.departments.none}</Muted>
        </Card>
      ) : null}
    </ScrollView>
  );
}
