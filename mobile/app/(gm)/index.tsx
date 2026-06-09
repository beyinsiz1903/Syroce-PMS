import React from 'react';
import { ScrollView } from 'react-native';
import { Body, Card, H1, H2, Muted } from '../../src/components/ui';
import { spacing, useTheme } from '../../src/theme';
import { useAuthStore } from '../../src/state/authStore';
import { RoleSwitcher } from '../../src/components/RoleSwitcher';

export default function GMOverview() {
  const c = useTheme();
  const { user } = useAuthStore();
  return (
    <ScrollView contentContainerStyle={{ padding: spacing.lg, gap: spacing.md, backgroundColor: c.bg, flexGrow: 1 }}>
      <H1>Yönetici Paneli</H1>
      <Muted>Hoş geldiniz, {user?.name || user?.email}</Muted>
      <RoleSwitcher />
      <Card>
        <H2>MVP placeholder</H2>
        <Body style={{ marginTop: spacing.sm }}>
          Yönetici dashboard (KPI'lar, doluluk, gelir, alarmlar) sonraki sürümde tam dolumla
          birlikte gelecek. MVP'de yalnızca rol tabanlı yönlendirme aktif.
        </Body>
      </Card>
    </ScrollView>
  );
}
