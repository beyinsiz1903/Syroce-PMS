import React, { useMemo, useState } from 'react';
import { Pressable, ScrollView, View } from 'react-native';
import { Redirect, useRouter } from 'expo-router';
import { useQuery } from '@tanstack/react-query';
import { Badge, Body, Card, EmptyState, H1, Muted } from '../../../src/components/ui';
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
  listGroupReservations,
  listGroupBlocks,
  listCorporateContracts,
  type MiceEvent,
  type MiceAccount,
  type MiceOpportunity,
  type GroupReservation,
  type GroupBlock,
  type CorporateContract,
} from '../../../src/api/mice';
import { formatCurrency, formatDate } from '../../../src/utils/format';

type Tab = 'events' | 'accounts' | 'opportunities' | 'groups';

type Tone = 'default' | 'success' | 'warning' | 'danger' | 'info' | 'primary';

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

function groupTone(status?: string): Tone {
  switch (status) {
    case 'confirmed':
    case 'active':
    case 'completed':
      return 'success';
    case 'cancelled':
      return 'danger';
    case 'tentative':
    case 'pending':
      return 'warning';
    case 'released':
      return 'info';
    default:
      return 'default';
  }
}

function groupStatusLabel(status?: string): string {
  const map = tr.departments.mice.groupStatuses as Record<string, string>;
  return (status && map[status]) || status || '—';
}

function contractTone(status?: string): Tone {
  switch (status) {
    case 'active':
      return 'success';
    case 'expiring_soon':
    case 'expiring':
      return 'warning';
    case 'expired':
      return 'danger';
    default:
      return 'default';
  }
}

function contractStatusLabel(status?: string): string {
  const map = tr.departments.mice.contractStatuses as Record<string, string>;
  return (status && map[status]) || status || '—';
}

// Read-only MICE / Sales & Catering screen. Four tabs: events (with the
// function-space catalogue + availability), CRM accounts (hesaplar),
// opportunities/proposals (teklifler) and groups (grup/blok rezervasyonları +
// kurumsal sözleşme durumu). All backend reads only require auth; the
// (departments) MICE entitlement decides whether we show the screen. Writes
// stay backend-gated.
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
  const groupsQ = useQuery({
    queryKey: ['mice-group-reservations'],
    queryFn: listGroupReservations,
    enabled: tab === 'groups',
  });
  const blocksQ = useQuery({
    queryKey: ['mice-group-blocks'],
    queryFn: () => listGroupBlocks(),
    enabled: tab === 'groups',
  });
  const contractsQ = useQuery({
    queryKey: ['mice-corporate-contracts'],
    queryFn: () => listCorporateContracts(),
    enabled: tab === 'groups',
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

  const renderGroup = (g: GroupReservation) => (
    <Card key={g.id} style={{ marginBottom: spacing.sm }}>
      <View
        style={{
          flexDirection: 'row',
          justifyContent: 'space-between',
          alignItems: 'flex-start',
        }}
      >
        <View style={{ flex: 1, paddingRight: spacing.sm }}>
          <Body style={{ fontWeight: '600' }}>{g.group_name || '—'}</Body>
          {g.contact_person ? (
            <Muted>
              {tr.departments.mice.contact}: {g.contact_person}
            </Muted>
          ) : null}
        </View>
        <Badge label={groupStatusLabel(g.status)} tone={groupTone(g.status)} />
      </View>
      <View style={{ marginTop: spacing.sm, gap: 2 }}>
        {g.check_in_date ? (
          <Muted>
            {formatDate(g.check_in_date)}
            {g.check_out_date && g.check_out_date !== g.check_in_date
              ? ` – ${formatDate(g.check_out_date)}`
              : ''}
          </Muted>
        ) : null}
        {typeof g.total_rooms === 'number' ? (
          <Muted>
            {tr.departments.mice.rooms}: {g.rooms_assigned ?? 0}/{g.total_rooms}{' '}
            ({tr.departments.mice.roomsAssigned})
          </Muted>
        ) : null}
      </View>
    </Card>
  );

  const renderBlock = (b: GroupBlock) => (
    <Card key={b.id} style={{ marginBottom: spacing.sm }}>
      <View
        style={{
          flexDirection: 'row',
          justifyContent: 'space-between',
          alignItems: 'flex-start',
        }}
      >
        <View style={{ flex: 1, paddingRight: spacing.sm }}>
          <Body style={{ fontWeight: '600' }}>{b.group_name || '—'}</Body>
          {b.organization ? <Muted>{b.organization}</Muted> : null}
        </View>
        <Badge label={groupStatusLabel(b.status)} tone={groupTone(b.status)} />
      </View>
      <View style={{ marginTop: spacing.sm, gap: 2 }}>
        {b.check_in ? (
          <Muted>
            {formatDate(b.check_in)}
            {b.check_out && b.check_out !== b.check_in
              ? ` – ${formatDate(b.check_out)}`
              : ''}
          </Muted>
        ) : null}
        {typeof b.total_rooms === 'number' ? (
          <Muted>
            {tr.departments.mice.rooms}: {b.rooms_picked_up ?? 0}/{b.total_rooms}{' '}
            ({tr.departments.mice.roomsPickedUp})
          </Muted>
        ) : null}
        {b.room_type ? (
          <Muted>
            {tr.departments.mice.roomType}: {b.room_type}
          </Muted>
        ) : null}
        {typeof b.group_rate === 'number' && b.group_rate > 0 ? (
          <Muted>
            {tr.departments.mice.groupRate}: {formatCurrency(b.group_rate)}
          </Muted>
        ) : null}
      </View>
    </Card>
  );

  const renderContract = (k: CorporateContract) => (
    <Card key={k.id} style={{ marginBottom: spacing.sm }}>
      <View
        style={{
          flexDirection: 'row',
          justifyContent: 'space-between',
          alignItems: 'flex-start',
        }}
      >
        <View style={{ flex: 1, paddingRight: spacing.sm }}>
          <Body style={{ fontWeight: '600' }}>{k.company_name || '—'}</Body>
          {k.contact_person ? (
            <Muted>
              {tr.departments.mice.contact}: {k.contact_person}
            </Muted>
          ) : null}
        </View>
        <Badge label={contractStatusLabel(k.status)} tone={contractTone(k.status)} />
      </View>
      <View style={{ marginTop: spacing.sm, gap: 2 }}>
        {k.start_date ? (
          <Muted>
            {formatDate(k.start_date)}
            {k.end_date ? ` – ${formatDate(k.end_date)}` : ''}
          </Muted>
        ) : null}
        {typeof k.room_nights_committed === 'number' ? (
          <Muted>
            {tr.departments.mice.roomNights}: {k.room_nights_used ?? 0}/
            {k.room_nights_committed}
          </Muted>
        ) : null}
        {typeof k.discount_percentage === 'number' && k.discount_percentage > 0 ? (
          <Muted>
            {tr.departments.mice.discount}: %{k.discount_percentage}
          </Muted>
        ) : null}
        {typeof k.contracted_rate === 'number' && k.contracted_rate > 0 ? (
          <Muted>
            {tr.departments.mice.contractRate}: {formatCurrency(k.contracted_rate)}
          </Muted>
        ) : null}
        {typeof k.days_until_expiry === 'number' && k.days_until_expiry > 0 ? (
          <Muted>
            {tr.departments.mice.expiresIn}: {k.days_until_expiry}{' '}
            {tr.departments.mice.days}
          </Muted>
        ) : null}
      </View>
    </Card>
  );

  const renderSpace = (s: import('../../../src/api/mice').MiceSpace) => (
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
        <Badge
          label={
            s.active === false
              ? tr.departments.mice.unavailable
              : tr.departments.mice.available
          }
          tone={s.active === false ? 'default' : 'success'}
        />
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
        {typeof s.daily_rate === 'number' ? (
          <Muted>
            {tr.departments.mice.dailyRate}: {formatCurrency(s.daily_rate, s.currency)}
          </Muted>
        ) : null}
      </View>
    </Card>
  );

  // Renders loading skeletons / error card (DepartmentListState) but uses the
  // richer EmptyState card for the empty branch, per the design system.
  function listBlock<T>(
    q: { isLoading: boolean; error: unknown; data?: T[] },
    emptyIcon: React.ComponentProps<typeof EmptyState>['icon'],
    emptyTitle: string,
    render: (item: T) => React.ReactNode,
  ): React.ReactNode {
    if (q.isLoading || q.error) {
      return (
        <DepartmentListState loading={q.isLoading} error={q.error} isEmpty={false} />
      );
    }
    const data = q.data || [];
    if (data.length === 0) return <EmptyState icon={emptyIcon} title={emptyTitle} />;
    return <View>{data.map(render)}</View>;
  }

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
        <TabButton value="groups" label={tr.departments.mice.tabGroups} />
      </View>

      {tab === 'events' ? (
        <>
          <SectionTitle title={tr.departments.mice.events} />
          {listBlock(
            eventsQ,
            'calendar-outline',
            tr.departments.mice.noEvents,
            renderEvent,
          )}

          <SectionTitle title={tr.departments.mice.spaces} />
          {listBlock(
            spacesQ,
            'business-outline',
            tr.departments.mice.noSpaces,
            renderSpace,
          )}
        </>
      ) : null}

      {tab === 'accounts' ? (
        <>
          <SectionTitle title={tr.departments.mice.accounts} />
          {listBlock(
            accountsQ,
            'people-outline',
            tr.departments.mice.noAccounts,
            renderAccount,
          )}
        </>
      ) : null}

      {tab === 'opportunities' ? (
        <>
          <SectionTitle title={tr.departments.mice.opportunities} />
          {listBlock(
            oppsQ,
            'briefcase-outline',
            tr.departments.mice.noOpportunities,
            renderOpportunity,
          )}
        </>
      ) : null}

      {tab === 'groups' ? (
        <>
          <SectionTitle title={tr.departments.mice.groupReservations} />
          {listBlock(
            groupsQ,
            'people-circle-outline',
            tr.departments.mice.noGroups,
            renderGroup,
          )}

          <SectionTitle title={tr.departments.mice.groupBlocks} />
          {listBlock(
            blocksQ,
            'grid-outline',
            tr.departments.mice.noBlocks,
            renderBlock,
          )}

          <SectionTitle title={tr.departments.mice.corporateContracts} />
          {listBlock(
            contractsQ,
            'document-text-outline',
            tr.departments.mice.noContracts,
            renderContract,
          )}
        </>
      ) : null}
    </ScrollView>
  );
}
