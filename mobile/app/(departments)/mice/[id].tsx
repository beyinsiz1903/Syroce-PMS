import React, { useMemo } from 'react';
import { ScrollView, View } from 'react-native';
import { Redirect, useLocalSearchParams } from 'expo-router';
import { useQuery } from '@tanstack/react-query';
import {
  Badge,
  Body,
  Card,
  DetailHeader,
  DetailRow,
  Muted,
  SkeletonCard,
} from '../../../src/components/ui';
import { SectionTitle } from '../../../src/components/department';
import { spacing, useTheme } from '../../../src/theme';
import { tr } from '../../../src/i18n/tr';
import { useAuthStore } from '../../../src/state/authStore';
import { ROUTES } from '../../../src/navigation/routes';
import { getMiceEvent, listMiceSpaces } from '../../../src/api/mice';
import { formatCurrency, formatDate } from '../../../src/utils/format';

type Tone = 'default' | 'success' | 'warning' | 'danger' | 'info' | 'primary';

function eventTone(status?: string): Tone {
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

// Read-only MICE event detail. Loads the single event plus the space catalogue
// to resolve booked-space names. Premium detail language: masthead with status
// badge, label/value rows, accented section cards.
export default function MiceDetailScreen() {
  const c = useTheme();
  const miceAccess = useAuthStore((s) => s.miceAccess);
  const M = tr.departments.mice;
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
          <DetailHeader
            title={e.name || M.eventDetail}
            subtitle={e.client_name || undefined}
            badges={<Badge label={statusLabel(e.status)} tone={eventTone(e.status)} />}
            testID="mice-event-header"
          />

          <Card accent={c.primary}>
            <DetailRow label={M.client} value={e.client_name} />
            <DetailRow label={M.organizer} value={e.organizer_user} />
            <DetailRow label={M.type} value={e.event_type} />
            <DetailRow
              label={M.dates}
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
            <DetailRow
              label={M.pax}
              value={typeof e.expected_pax === 'number' ? String(e.expected_pax) : undefined}
            />
            <DetailRow
              label={M.total}
              value={
                typeof e.totals?.grand_total === 'number'
                  ? formatCurrency(e.totals.grand_total, e.totals.currency)
                  : undefined
              }
            />
          </Card>

          <SectionTitle title={M.bookedSpaces} />
          {(e.space_bookings || []).length === 0 ? (
            <Card>
              <Muted>{M.noSpaces}</Muted>
            </Card>
          ) : (
            (e.space_bookings || []).map((b, i) => (
              <Card
                key={`${b.space_id}-${i}`}
                accent={c.info}
                style={{ marginBottom: spacing.sm }}
              >
                <Body style={{ fontWeight: '700' }}>
                  {(b.space_id && spaceName.get(b.space_id)) || b.space_id || '—'}
                </Body>
                {b.setup_style ? <Muted>{b.setup_style}</Muted> : null}
                {typeof b.expected_pax === 'number' ? (
                  <Muted>
                    {M.pax}: {b.expected_pax}
                  </Muted>
                ) : null}
              </Card>
            ))
          )}

          <SectionTitle title={M.resources} />
          {(e.resources || []).length === 0 ? (
            <Card>
              <Muted>{M.noResources}</Muted>
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
                    <Body style={{ fontWeight: '700' }}>{r.name || '—'}</Body>
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
              <SectionTitle title={M.notes} />
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
