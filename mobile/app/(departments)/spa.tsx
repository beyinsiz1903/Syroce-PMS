import React, { useMemo, useState } from 'react';
import { Pressable, ScrollView, View } from 'react-native';
import { Redirect } from 'expo-router';
import { useQuery } from '@tanstack/react-query';
import { Badge, Body, Card, H1, Muted } from '../../src/components/ui';
import {
  DepartmentListState,
  SectionTitle,
} from '../../src/components/department';
import { spacing, radius, useTheme } from '../../src/theme';
import { tr } from '../../src/i18n/tr';
import { useAuthStore } from '../../src/state/authStore';
import { ROUTES } from '../../src/navigation/routes';
import {
  listSpaAppointments,
  listSpaServices,
  listSpaTherapists,
  type SpaAppointment,
} from '../../src/api/spa';
import { formatCurrency, formatDate, formatTime } from '../../src/utils/format';

type Range = 'today' | 'week';

function isoDate(d: Date): string {
  return d.toISOString().slice(0, 10);
}

function rangeParams(range: Range): { date_from: string; date_to: string } {
  const now = new Date();
  const from = isoDate(now);
  const to = new Date(now);
  if (range === 'week') to.setDate(to.getDate() + 6);
  return { date_from: from, date_to: isoDate(to) };
}

function appointmentTone(status?: string):
  | 'default'
  | 'success'
  | 'warning'
  | 'danger'
  | 'info' {
  switch (status) {
    case 'completed':
      return 'success';
    case 'in_progress':
      return 'info';
    case 'no_show':
    case 'cancelled':
      return 'danger';
    case 'scheduled':
      return 'warning';
    default:
      return 'default';
  }
}

function statusLabel(status?: string): string {
  const map = tr.departments.spa.statuses as Record<string, string>;
  return (status && map[status]) || status || '—';
}

// Read-only Spa & Wellness screen: appointments (today / 7-day), service
// catalogue and therapists. Backend reads are open to any authenticated user;
// the (departments) entitlement just decides whether we show this screen.
export default function SpaScreen() {
  const c = useTheme();
  const spaAccess = useAuthStore((s) => s.spaAccess);
  const [range, setRange] = useState<Range>('today');

  const params = useMemo(() => rangeParams(range), [range]);

  const apptsQ = useQuery({
    queryKey: ['spa-appointments', params.date_from, params.date_to],
    queryFn: () => listSpaAppointments(params),
  });
  const servicesQ = useQuery({ queryKey: ['spa-services'], queryFn: listSpaServices });
  const therapistsQ = useQuery({ queryKey: ['spa-therapists'], queryFn: listSpaTherapists });

  const therapistName = useMemo(() => {
    const m = new Map<string, string>();
    (therapistsQ.data || []).forEach((t) => m.set(t.id, t.name));
    return m;
  }, [therapistsQ.data]);

  // Hard guard: a user who somehow lands here without spa entitlement is sent
  // to the hub. This is cosmetic only — the backend still enforces every write.
  if (!spaAccess) return <Redirect href={ROUTES.departments} />;

  const RangeTab: React.FC<{ value: Range; label: string }> = ({ value, label }) => {
    const active = range === value;
    return (
      <Pressable
        onPress={() => setRange(value)}
        accessibilityRole="button"
        style={{
          flex: 1,
          paddingVertical: spacing.sm,
          borderRadius: radius.md,
          alignItems: 'center',
          backgroundColor: active ? c.primary : c.surfaceAlt,
          borderWidth: 1,
          borderColor: active ? c.primary : c.border,
        }}
      >
        <Body style={{ color: active ? c.primaryText : c.text, fontWeight: '600' }}>
          {label}
        </Body>
      </Pressable>
    );
  };

  const renderAppointment = (a: SpaAppointment) => (
    <Card key={a.id} style={{ marginBottom: spacing.sm }}>
      <View
        style={{
          flexDirection: 'row',
          justifyContent: 'space-between',
          alignItems: 'flex-start',
        }}
      >
        <View style={{ flex: 1, paddingRight: spacing.sm }}>
          <Body style={{ fontWeight: '600' }}>{a.service_name || '—'}</Body>
          {a.guest_name ? <Muted>{a.guest_name}</Muted> : null}
        </View>
        <Badge label={statusLabel(a.status)} tone={appointmentTone(a.status)} />
      </View>
      <View style={{ marginTop: spacing.sm, gap: 2 }}>
        <Muted>
          {formatDate(a.starts_at)} · {formatTime(a.starts_at)}
          {a.ends_at ? ` – ${formatTime(a.ends_at)}` : ''}
        </Muted>
        <Muted>
          {tr.departments.spa.withTherapist}:{' '}
          {(a.therapist_id && therapistName.get(a.therapist_id)) ||
            tr.departments.spa.unassigned}
        </Muted>
        {typeof a.price === 'number' ? (
          <Muted>{formatCurrency(a.price, a.currency)}</Muted>
        ) : null}
      </View>
    </Card>
  );

  return (
    <ScrollView
      style={{ flex: 1, backgroundColor: c.bg }}
      contentContainerStyle={{ padding: spacing.lg, paddingBottom: spacing.xl }}
    >
      <H1>{tr.departments.spa.title}</H1>

      <SectionTitle title={tr.departments.spa.appointments} />
      <View style={{ flexDirection: 'row', gap: spacing.sm, marginBottom: spacing.md }}>
        <RangeTab value="today" label={tr.departments.spa.today} />
        <RangeTab value="week" label={tr.departments.spa.week} />
      </View>
      {(() => {
        const state = (
          <DepartmentListState
            loading={apptsQ.isLoading}
            error={apptsQ.error}
            isEmpty={(apptsQ.data || []).length === 0}
            emptyText={tr.departments.spa.noAppointments}
          />
        );
        return state ?? <View>{(apptsQ.data || []).map(renderAppointment)}</View>;
      })()}

      <SectionTitle title={tr.departments.spa.services} />
      {(() => {
        const state = (
          <DepartmentListState
            loading={servicesQ.isLoading}
            error={servicesQ.error}
            isEmpty={(servicesQ.data || []).length === 0}
            emptyText={tr.departments.spa.noServices}
          />
        );
        return (
          state ?? (
            <View>
              {(servicesQ.data || []).map((s) => (
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
                      {s.category ? <Muted>{s.category}</Muted> : null}
                    </View>
                    {typeof s.price === 'number' ? (
                      <Body>{formatCurrency(s.price, s.currency)}</Body>
                    ) : null}
                  </View>
                  {typeof s.duration_minutes === 'number' ? (
                    <Muted style={{ marginTop: spacing.xs }}>
                      {s.duration_minutes} {tr.departments.spa.minutes}
                    </Muted>
                  ) : null}
                </Card>
              ))}
            </View>
          )
        );
      })()}

      <SectionTitle title={tr.departments.spa.therapists} />
      {(() => {
        const state = (
          <DepartmentListState
            loading={therapistsQ.isLoading}
            error={therapistsQ.error}
            isEmpty={(therapistsQ.data || []).length === 0}
            emptyText={tr.departments.spa.noTherapists}
          />
        );
        return (
          state ?? (
            <View>
              {(therapistsQ.data || []).map((t) => (
                <Card key={t.id} style={{ marginBottom: spacing.sm }}>
                  <Body style={{ fontWeight: '600' }}>{t.name}</Body>
                  {t.specialties && t.specialties.length > 0 ? (
                    <Muted style={{ marginTop: spacing.xs }}>
                      {tr.departments.spa.specialties}: {t.specialties.join(', ')}
                    </Muted>
                  ) : null}
                  {t.work_start && t.work_end ? (
                    <Muted style={{ marginTop: 2 }}>
                      {tr.departments.spa.workingHours}: {t.work_start} – {t.work_end}
                    </Muted>
                  ) : null}
                </Card>
              ))}
            </View>
          )
        );
      })()}
    </ScrollView>
  );
}
