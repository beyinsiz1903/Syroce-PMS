import React from 'react';
import { Pressable, ScrollView, View } from 'react-native';
import { Redirect, useRouter } from 'expo-router';
import { useQuery } from '@tanstack/react-query';
import { Badge, Body, Card, H1, Muted } from '../../../src/components/ui';
import {
  DepartmentListState,
  SectionTitle,
} from '../../../src/components/department';
import { spacing, useTheme } from '../../../src/theme';
import { tr } from '../../../src/i18n/tr';
import { useAuthStore } from '../../../src/state/authStore';
import { ROUTES } from '../../../src/navigation/routes';
import { listMiceEvents, listMiceSpaces, type MiceEvent } from '../../../src/api/mice';
import { formatCurrency, formatDate } from '../../../src/utils/format';

function eventTone(status?: string):
  | 'default'
  | 'success'
  | 'warning'
  | 'danger'
  | 'info'
  | 'primary' {
  switch (status) {
    case 'confirmed':
    case 'definite':
      return 'success';
    case 'completed':
      return 'info';
    case 'cancelled':
      return 'danger';
    case 'tentative':
      return 'warning';
    case 'lead':
      return 'primary';
    default:
      return 'default';
  }
}

function statusLabel(status?: string): string {
  const map = tr.departments.mice.statuses as Record<string, string>;
  return (status && map[status]) || status || '—';
}

// Read-only MICE / Events list with the function-space catalogue. Tapping an
// event opens its detail screen.
export default function MiceListScreen() {
  const c = useTheme();
  const router = useRouter();
  const miceAccess = useAuthStore((s) => s.miceAccess);

  const eventsQ = useQuery({ queryKey: ['mice-events'], queryFn: () => listMiceEvents() });
  const spacesQ = useQuery({ queryKey: ['mice-spaces'], queryFn: listMiceSpaces });

  if (!miceAccess) return <Redirect href={ROUTES.departments} />;

  const renderEvent = (e: MiceEvent) => (
    <Pressable
      key={e.id}
      onPress={() => router.push(`${ROUTES.mice}/${e.id}`)}
      accessibilityRole="button"
    >
      {({ pressed }) => (
        <Card style={{ marginBottom: spacing.sm, opacity: pressed ? 0.85 : 1 }}>
          <View
            style={{
              flexDirection: 'row',
              justifyContent: 'space-between',
              alignItems: 'flex-start',
            }}
          >
            <View style={{ flex: 1, paddingRight: spacing.sm }}>
              <Body style={{ fontWeight: '600' }}>{e.name || '—'}</Body>
              {e.client_name ? <Muted>{e.client_name}</Muted> : null}
            </View>
            <Badge label={statusLabel(e.status)} tone={eventTone(e.status)} />
          </View>
          <View style={{ marginTop: spacing.sm, gap: 2 }}>
            <Muted>
              {formatDate(e.start_date)}
              {e.end_date && e.end_date !== e.start_date ? ` – ${formatDate(e.end_date)}` : ''}
            </Muted>
            {typeof e.expected_pax === 'number' ? (
              <Muted>
                {tr.departments.mice.pax}: {e.expected_pax}
              </Muted>
            ) : null}
            {typeof e.totals?.grand_total === 'number' ? (
              <Muted>
                {tr.departments.mice.total}:{' '}
                {formatCurrency(e.totals.grand_total, e.totals.currency)}
              </Muted>
            ) : null}
          </View>
        </Card>
      )}
    </Pressable>
  );

  return (
    <ScrollView
      style={{ flex: 1, backgroundColor: c.bg }}
      contentContainerStyle={{ padding: spacing.lg, paddingBottom: spacing.xl }}
    >
      <H1>{tr.departments.mice.title}</H1>

      <SectionTitle title={tr.departments.mice.events} />
      {(() => {
        const state = (
          <DepartmentListState
            loading={eventsQ.isLoading}
            error={eventsQ.error}
            isEmpty={(eventsQ.data || []).length === 0}
            emptyText={tr.departments.mice.noEvents}
          />
        );
        return state ?? <View>{(eventsQ.data || []).map(renderEvent)}</View>;
      })()}

      <SectionTitle title={tr.departments.mice.spaces} />
      {(() => {
        const state = (
          <DepartmentListState
            loading={spacesQ.isLoading}
            error={spacesQ.error}
            isEmpty={(spacesQ.data || []).length === 0}
            emptyText={tr.departments.mice.noSpaces}
          />
        );
        return (
          state ?? (
            <View>
              {(spacesQ.data || []).map((s) => (
                <Card key={s.id} style={{ marginBottom: spacing.sm }}>
                  <View
                    style={{
                      flexDirection: 'row',
                      justifyContent: 'space-between',
                      alignItems: 'flex-start',
                    }}
                  >
                    <View style={{ flex: 1, paddingRight: spacing.sm }}>
                      <Body style={{ fontWeight: '600' }}>{s.name}</Body>
                      {s.location ? (
                        <Muted>
                          {tr.departments.mice.location}: {s.location}
                        </Muted>
                      ) : null}
                    </View>
                    {typeof s.daily_rate === 'number' ? (
                      <Body>{formatCurrency(s.daily_rate, s.currency)}</Body>
                    ) : null}
                  </View>
                  <View style={{ marginTop: spacing.xs, gap: 2 }}>
                    {typeof s.area_m2 === 'number' ? (
                      <Muted>
                        {tr.departments.mice.area}: {s.area_m2} m²
                      </Muted>
                    ) : null}
                    {typeof s.capacity_theatre === 'number' ? (
                      <Muted>
                        {tr.departments.mice.capacity}: {s.capacity_theatre}
                      </Muted>
                    ) : null}
                  </View>
                </Card>
              ))}
            </View>
          )
        );
      })()}
    </ScrollView>
  );
}
