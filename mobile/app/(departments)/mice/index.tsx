import React, { useMemo, useState } from 'react';
import { Pressable, ScrollView, View } from 'react-native';
import { Redirect, useRouter } from 'expo-router';
import { useQuery } from '@tanstack/react-query';
import { Badge, Body, Card, H1, Muted } from '../../../src/components/ui';
import {
  DepartmentListState,
  SectionTitle,
} from '../../../src/components/department';
import { spacing, radius, useTheme } from '../../../src/theme';
import { tr } from '../../../src/i18n/tr';
import { useAuthStore } from '../../../src/state/authStore';
import { ROUTES } from '../../../src/navigation/routes';
import {
  listMiceEvents,
  listMiceSpaces,
  listMiceAccounts,
  listMiceOpportunities,
  type MiceEvent,
  type MiceAccount,
  type MiceOpportunity,
} from '../../../src/api/mice';
import { formatCurrency, formatDate } from '../../../src/utils/format';

type Tab = 'events' | 'accounts' | 'opportunities';

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

function stageTone(stage?: string):
  | 'default'
  | 'success'
  | 'warning'
  | 'danger'
  | 'info'
  | 'primary' {
  switch (stage) {
    case 'won':
      return 'success';
    case 'lost':
      return 'danger';
    case 'contract':
      return 'info';
    case 'proposal':
    case 'qualified':
      return 'warning';
    case 'lead':
      return 'primary';
    default:
      return 'default';
  }
}

function stageLabel(stage?: string): string {
  const map = tr.departments.mice.stages as Record<string, string>;
  return (stage && map[stage]) || stage || '—';
}

// Read-only MICE / Sales & Catering screen. Three tabs: events (with the
// function-space catalogue), CRM accounts (hesaplar) and opportunities/proposals
// (teklifler). All backend reads only require auth; the (departments) MICE
// entitlement decides whether we show the screen. Writes stay backend-gated.
export default function MiceListScreen() {
  const c = useTheme();
  const router = useRouter();
  const miceAccess = useAuthStore((s) => s.miceAccess);
  const [tab, setTab] = useState<Tab>('events');

  const eventsQ = useQuery({ queryKey: ['mice-events'], queryFn: () => listMiceEvents() });
  const spacesQ = useQuery({ queryKey: ['mice-spaces'], queryFn: listMiceSpaces });
  const accountsQ = useQuery({
    queryKey: ['mice-accounts'],
    queryFn: listMiceAccounts,
    enabled: tab === 'accounts',
  });
  const oppsQ = useQuery({
    queryKey: ['mice-opportunities'],
    queryFn: () => listMiceOpportunities({ limit: 100 }),
    enabled: tab === 'opportunities',
  });

  const accountName = useMemo(() => {
    const m = new Map<string, string>();
    (accountsQ.data || []).forEach((a) => m.set(a.id, a.name || ''));
    return m;
  }, [accountsQ.data]);

  if (!miceAccess) return <Redirect href={ROUTES.departments} />;

  const TabButton: React.FC<{ value: Tab; label: string }> = ({ value, label }) => {
    const active = tab === value;
    return (
      <Pressable
        onPress={() => setTab(value)}
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

  const renderAccount = (a: MiceAccount) => (
    <Card key={a.id} style={{ marginBottom: spacing.sm }}>
      <View
        style={{
          flexDirection: 'row',
          justifyContent: 'space-between',
          alignItems: 'flex-start',
        }}
      >
        <View style={{ flex: 1, paddingRight: spacing.sm }}>
          <Body style={{ fontWeight: '600' }}>{a.name || '—'}</Body>
          {a.industry ? <Muted>{a.industry}</Muted> : null}
        </View>
        {a.active === false ? (
          <Badge label={tr.departments.mice.inactive} tone="default" />
        ) : null}
      </View>
      <View style={{ marginTop: spacing.sm, gap: 2 }}>
        {a.tax_no ? (
          <Muted>
            {tr.departments.mice.taxNo}: {a.tax_no}
          </Muted>
        ) : null}
        {a.email ? <Muted>{a.email}</Muted> : null}
        {typeof a.credit_limit === 'number' && a.credit_limit > 0 ? (
          <Muted>
            {tr.departments.mice.creditLimit}: {formatCurrency(a.credit_limit)}
          </Muted>
        ) : null}
        {typeof a.payment_terms_days === 'number' && a.payment_terms_days > 0 ? (
          <Muted>
            {tr.departments.mice.paymentTerms}: {a.payment_terms_days}
          </Muted>
        ) : null}
      </View>
    </Card>
  );

  const renderOpportunity = (o: MiceOpportunity) => (
    <Card key={o.id} style={{ marginBottom: spacing.sm }}>
      <View
        style={{
          flexDirection: 'row',
          justifyContent: 'space-between',
          alignItems: 'flex-start',
        }}
      >
        <View style={{ flex: 1, paddingRight: spacing.sm }}>
          <Body style={{ fontWeight: '600' }}>{o.title || '—'}</Body>
          {o.account_id && accountName.get(o.account_id) ? (
            <Muted>
              {tr.departments.mice.account}: {accountName.get(o.account_id)}
            </Muted>
          ) : null}
        </View>
        <Badge label={stageLabel(o.stage)} tone={stageTone(o.stage)} />
      </View>
      <View style={{ marginTop: spacing.sm, gap: 2 }}>
        {typeof o.estimated_value === 'number' && o.estimated_value > 0 ? (
          <Muted>
            {tr.departments.mice.estimatedValue}:{' '}
            {formatCurrency(o.estimated_value, o.currency)}
          </Muted>
        ) : null}
        {typeof o.probability === 'number' ? (
          <Muted>
            {tr.departments.mice.probability}: %{o.probability}
          </Muted>
        ) : null}
        {o.expected_start ? (
          <Muted>
            {formatDate(o.expected_start)}
            {o.expected_end && o.expected_end !== o.expected_start
              ? ` – ${formatDate(o.expected_end)}`
              : ''}
          </Muted>
        ) : null}
      </View>
    </Card>
  );

  return (
    <ScrollView
      style={{ flex: 1, backgroundColor: c.bg }}
      contentContainerStyle={{ padding: spacing.lg, paddingBottom: spacing.xl }}
    >
      <H1>{tr.departments.mice.title}</H1>

      <View style={{ flexDirection: 'row', gap: spacing.sm, marginTop: spacing.md }}>
        <TabButton value="events" label={tr.departments.mice.tabEvents} />
        <TabButton value="accounts" label={tr.departments.mice.tabAccounts} />
        <TabButton value="opportunities" label={tr.departments.mice.tabOpportunities} />
      </View>

      {tab === 'events' ? (
        <>
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
        </>
      ) : null}

      {tab === 'accounts' ? (
        <>
          <SectionTitle title={tr.departments.mice.accounts} />
          {(() => {
            const state = (
              <DepartmentListState
                loading={accountsQ.isLoading}
                error={accountsQ.error}
                isEmpty={(accountsQ.data || []).length === 0}
                emptyText={tr.departments.mice.noAccounts}
              />
            );
            return state ?? <View>{(accountsQ.data || []).map(renderAccount)}</View>;
          })()}
        </>
      ) : null}

      {tab === 'opportunities' ? (
        <>
          <SectionTitle title={tr.departments.mice.opportunities} />
          {(() => {
            const state = (
              <DepartmentListState
                loading={oppsQ.isLoading}
                error={oppsQ.error}
                isEmpty={(oppsQ.data || []).length === 0}
                emptyText={tr.departments.mice.noOpportunities}
              />
            );
            return state ?? <View>{(oppsQ.data || []).map(renderOpportunity)}</View>;
          })()}
        </>
      ) : null}
    </ScrollView>
  );
}
