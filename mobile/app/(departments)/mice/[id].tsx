import React, { useMemo } from 'react';
import { ScrollView, View } from 'react-native';
import { Redirect, useLocalSearchParams } from 'expo-router';
import { useQuery } from '@tanstack/react-query';
import { Badge, Body, Card, H1, Muted, SkeletonCard } from '../../../src/components/ui';
import { DepartmentListState, SectionTitle } from '../../../src/components/department';
import { spacing, useTheme } from '../../../src/theme';
import { tr } from '../../../src/i18n/tr';
import { useAuthStore } from '../../../src/state/authStore';
import { ROUTES } from '../../../src/navigation/routes';
import { getMiceEvent, listMiceSpaces } from '../../../src/api/mice';
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

const Row: React.FC<{ label: string; value?: string | number | null }> = ({
  label,
  value,
}) => {
  if (value === undefined || value === null || value === '') return null;
  return (
    <View
      style={{ flexDirection: 'row', justifyContent: 'space-between', paddingVertical: 2 }}
    >
      <Muted>{label}</Muted>
      <Body style={{ flexShrink: 1, textAlign: 'right', paddingLeft: spacing.md }}>
        {String(value)}
      </Body>
    </View>
  );
};

// Read-only MICE event detail. Loads the single event plus the space catalogue
// to resolve booked-space names.
export default function MiceDetailScreen() {
  const c = useTheme();
  const miceAccess = useAuthStore((s) => s.miceAccess);
  const { id } = useLocalSearchParams<{ id: string }>();
  const eventId = Array.isArray(id) ? id[0] : id;

  const eventQ = useQuery({
    queryKey: ['mice-event', eventId],
    queryFn: () => getMiceEvent(eventId as string),
    enabled: !!eventId,
  });
  const spacesQ = useQuery({ queryKey: ['mice-spaces'], queryFn: listMiceSpaces });

  const spaceName = useMemo(() => {
    const m = new Map<string, string>();
    (spacesQ.data || []).forEach((s) => m.set(s.id, s.name));
    return m;
  }, [spacesQ.data]);

  if (!miceAccess) return <Redirect href={ROUTES.departments} />;

  const e = eventQ.data;

  return (
    <ScrollView
      style={{ flex: 1, backgroundColor: c.bg }}
      contentContainerStyle={{ padding: spacing.lg, paddingBottom: spacing.xl }}
    >
      {eventQ.isLoading ? (
        <SkeletonCard />
      ) : eventQ.error || !e ? (
        <Card>
          <Body>{tr.departments.loadError}</Body>
        </Card>
      ) : (
        <>
          <View
            style={{
              flexDirection: 'row',
              justifyContent: 'space-between',
              alignItems: 'flex-start',
              gap: spacing.sm,
            }}
          >
            <H1 style={{ flex: 1 }}>{e.name || tr.departments.mice.eventDetail}</H1>
            <Badge label={statusLabel(e.status)} tone={eventTone(e.status)} />
          </View>

          <Card style={{ marginTop: spacing.md }}>
            <Row label={tr.departments.mice.client} value={e.client_name} />
            <Row label={tr.departments.mice.organizer} value={e.organizer_user} />
            <Row label={tr.departments.mice.type} value={e.event_type} />
            <Row
              label={tr.departments.mice.dates}
              value={
                e.start_date
                  ? `${formatDate(e.start_date)}${
                      e.end_date && e.end_date !== e.start_date
                        ? ` – ${formatDate(e.end_date)}`
                        : ''
                    }`
                  : undefined
              }
            />
            <Row label={tr.departments.mice.pax} value={e.expected_pax} />
            <Row
              label={tr.departments.mice.total}
              value={
                typeof e.totals?.grand_total === 'number'
                  ? formatCurrency(e.totals.grand_total, e.totals.currency)
                  : undefined
              }
            />
          </Card>

          <SectionTitle title={tr.departments.mice.bookedSpaces} />
          {(e.space_bookings || []).length === 0 ? (
            <Card>
              <Muted>{tr.departments.mice.noSpaces}</Muted>
            </Card>
          ) : (
            (e.space_bookings || []).map((b, i) => (
              <Card key={`${b.space_id}-${i}`} style={{ marginBottom: spacing.sm }}>
                <Body style={{ fontWeight: '600' }}>
                  {(b.space_id && spaceName.get(b.space_id)) || b.space_id || '—'}
                </Body>
                {b.setup_style ? <Muted>{b.setup_style}</Muted> : null}
                {typeof b.expected_pax === 'number' ? (
                  <Muted>
                    {tr.departments.mice.pax}: {b.expected_pax}
                  </Muted>
                ) : null}
              </Card>
            ))
          )}

          <SectionTitle title={tr.departments.mice.resources} />
          {(e.resources || []).length === 0 ? (
            <Card>
              <Muted>{tr.departments.mice.noResources}</Muted>
            </Card>
          ) : (
            (e.resources || []).map((r, i) => (
              <Card key={`${r.name}-${i}`} style={{ marginBottom: spacing.sm }}>
                <View
                  style={{
                    flexDirection: 'row',
                    justifyContent: 'space-between',
                    alignItems: 'flex-start',
                  }}
                >
                  <View style={{ flex: 1, paddingRight: spacing.sm }}>
                    <Body style={{ fontWeight: '600' }}>{r.name || '—'}</Body>
                    {r.type ? <Muted>{r.type}</Muted> : null}
                  </View>
                  {typeof r.quantity === 'number' ? (
                    <Muted>
                      {r.quantity}
                      {r.unit ? ` ${r.unit}` : ''}
                    </Muted>
                  ) : null}
                </View>
              </Card>
            ))
          )}

          {e.notes ? (
            <>
              <SectionTitle title={tr.departments.mice.notes} />
              <Card>
                <Body>{e.notes}</Body>
              </Card>
            </>
          ) : null}
        </>
      )}
    </ScrollView>
  );
}
