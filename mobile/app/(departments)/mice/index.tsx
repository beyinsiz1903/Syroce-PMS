import React, { useMemo, useState } from 'react';
import { Pressable, ScrollView, View } from 'react-native';
import { Redirect, useRouter } from 'expo-router';
import { useMutation, useQuery, useQueryClient } from '@tanstack/react-query';
import {
  ActionSheet,
  Badge,
  Body,
  Button,
  Card,
  EmptyState,
  FadeInView,
  H1,
  H2,
  ListRow,
  Muted,
  haptic,
  webCenter,
} from '../../../src/components/ui';
import {
  DepartmentListState,
  SectionTitle,
} from '../../../src/components/department';
import { spacing, radius, useTheme, ThemeColors } from '../../../src/theme';
import { tr } from '../../../src/i18n/tr';
import { useAuthStore } from '../../../src/state/authStore';
import { ROUTES } from '../../../src/navigation/routes';
import { errorMessage } from '../../../src/utils/errors';
import {
  listMiceEvents,
  listMiceSpaces,
  listMiceAccounts,
  listMiceOpportunities,
  listGroupReservations,
  listGroupBlocks,
  listCorporateContracts,
  getSalesPipeline,
  transitionOpportunity,
  OPP_STAGES,
  type OppStage,
  type MiceEvent,
  type MiceAccount,
  type MiceOpportunity,
  type GroupReservation,
  type GroupBlock,
  type CorporateContract,
} from '../../../src/api/mice';
import { formatCurrency, formatDate } from '../../../src/utils/format';

type Tab = 'pipeline' | 'events' | 'opportunities' | 'accounts' | 'groups';

type Tone = 'default' | 'success' | 'warning' | 'danger' | 'info' | 'primary';

// Maps a Badge tone to its theme colour so cards can echo their status with a
// left accent stripe (the Card `accent` prop) — status at-a-glance, premium.
function toneColor(tone: Tone, c: ThemeColors): string {
  switch (tone) {
    case 'success':
      return c.success;
    case 'warning':
      return c.warning;
    case 'danger':
      return c.danger;
    case 'info':
      return c.info;
    case 'primary':
      return c.primary;
    default:
      return c.textMuted;
  }
}

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

function stageTone(stage?: string): Tone {
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

// MICE / Sales & Catering screen. Five tabs: a sales pipeline (kanban) of
// opportunities, events (with the function-space catalogue), CRM accounts
// (müşteriler), the opportunity list (teklifler) and groups / corporate
// contracts (kontratlar). All reads require auth only; the kanban stage move is
// the one write here and stays backend-gated by require_op("manage_sales") —
// a caller without the permission gets a 403 surfaced inline (no fake success).
export default function MiceListScreen() {
  const c = useTheme();
  const router = useRouter();
  const qc = useQueryClient();
  const miceAccess = useAuthStore((s) => s.miceAccess);
  const [tab, setTab] = useState<Tab>('pipeline');
  const M = tr.departments.mice;

  const eventsQ = useQuery({
    queryKey: ['mice-events'],
    queryFn: () => listMiceEvents(),
    enabled: tab === 'events',
  });
  const spacesQ = useQuery({
    queryKey: ['mice-spaces'],
    queryFn: listMiceSpaces,
    enabled: tab === 'events',
  });
  const accountsQ = useQuery({
    queryKey: ['mice-accounts'],
    queryFn: listMiceAccounts,
    enabled: tab === 'accounts' || tab === 'pipeline',
  });
  const oppsQ = useQuery({
    queryKey: ['mice-opportunities'],
    queryFn: () => listMiceOpportunities({ limit: 200 }),
    enabled: tab === 'opportunities' || tab === 'pipeline',
  });
  const pipelineQ = useQuery({
    queryKey: ['mice-pipeline'],
    queryFn: getSalesPipeline,
    enabled: tab === 'pipeline',
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

  // ── Pipeline stage-move sheet ──────────────────────────────────────────────
  // Tapping an opportunity card opens this sheet listing every target stage but
  // the current one. The backend re-validates and enforces manage_sales; any
  // 403/4xx is surfaced inline. On success the queries refetch and the card
  // visibly moves columns — that move IS the success signal (no toast faking).
  const [activeOpp, setActiveOpp] = useState<MiceOpportunity | null>(null);
  const [stageError, setStageError] = useState<string | null>(null);

  const transitionMut = useMutation({
    mutationFn: (vars: { id: string; to: OppStage }) =>
      transitionOpportunity(vars.id, vars.to),
    onSuccess: () => {
      qc.invalidateQueries({ queryKey: ['mice-opportunities'] });
      qc.invalidateQueries({ queryKey: ['mice-pipeline'] });
      setActiveOpp(null);
      setStageError(null);
      haptic.success();
    },
    onError: (e: unknown) => {
      haptic.error();
      setStageError(errorMessage(e, M.stageUpdateError));
    },
  });

  const openStageSheet = (o: MiceOpportunity) => {
    setStageError(null);
    setActiveOpp(o);
  };

  const submitStage = (to: OppStage) => {
    if (!activeOpp) return;
    setStageError(null);
    transitionMut.mutate({ id: activeOpp.id, to });
  };

  if (!miceAccess) return <Redirect href={ROUTES.departments} />;

  const TabButton: React.FC<{ value: Tab; label: string }> = ({ value, label }) => {
    const active = tab === value;
    return (
      <Pressable
        testID={`mice-tab-${value}`}
        onPress={() => {
          haptic.tap();
          setTab(value);
        }}
        accessibilityRole="button"
        accessibilityState={{ selected: active }}
        style={{
          paddingVertical: spacing.sm,
          paddingHorizontal: spacing.lg,
          borderRadius: radius.pill,
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

  // ── Pipeline (kanban) renderers ────────────────────────────────────────────
  const StatTile: React.FC<{ label: string; value: string; tint?: string }> = ({
    label,
    value,
    tint,
  }) => (
    <View
      style={{
        flexGrow: 1,
        flexBasis: '47%',
        backgroundColor: c.surfaceAlt,
        borderRadius: radius.lg,
        borderWidth: 1,
        borderColor: c.border,
        padding: spacing.md,
      }}
    >
      <Muted style={{ fontSize: 12 }}>{label}</Muted>
      <Body style={{ fontWeight: '800', fontSize: 18, marginTop: 2, color: tint ?? c.text }}>
        {value}
      </Body>
    </View>
  );

  const renderKanbanCard = (o: MiceOpportunity) => (
    <Pressable
      key={o.id}
      testID={`mice-opp-card-${o.id}`}
      onPress={() => openStageSheet(o)}
      accessibilityRole="button"
      accessibilityLabel={`${o.title || ''} — ${M.moveStage}`}
    >
      {({ pressed }) => (
        <Card
          accent={toneColor(stageTone(o.stage), c)}
          style={{ marginBottom: spacing.sm, opacity: pressed ? 0.85 : 1 }}
        >
          <Body style={{ fontWeight: '700' }} numberOfLines={2}>
            {o.title || '—'}
          </Body>
          {o.account_id && accountName.get(o.account_id) ? (
            <Muted numberOfLines={1}>{accountName.get(o.account_id)}</Muted>
          ) : null}
          <View style={{ marginTop: spacing.sm, gap: 2 }}>
            {typeof o.estimated_value === 'number' && o.estimated_value > 0 ? (
              <Body style={{ fontWeight: '700' }}>
                {formatCurrency(o.estimated_value, o.currency)}
              </Body>
            ) : null}
            {typeof o.probability === 'number' ? (
              <Muted>
                {M.probability}: %{o.probability}
              </Muted>
            ) : null}
          </View>
          <View style={{ marginTop: spacing.sm, flexDirection: 'row', alignItems: 'center', gap: 4 }}>
            <Badge label={M.moveStage} tone="primary" icon="swap-horizontal-outline" />
          </View>
        </Card>
      )}
    </Pressable>
  );

  const renderPipeline = (): React.ReactNode => {
    if (oppsQ.isLoading || oppsQ.error) {
      return (
        <DepartmentListState
          loading={oppsQ.isLoading}
          error={oppsQ.error}
          isEmpty={false}
        />
      );
    }
    const opps = oppsQ.data || [];
    const p = pipelineQ.data;

    if (opps.length === 0) {
      return (
        <EmptyState
          icon="trending-up-outline"
          title={M.noPipeline}
          message={M.noPipelineMsg}
        />
      );
    }

    const summaryByStage = new Map(
      (p?.stages || []).map((s) => [s.stage, s] as const),
    );

    return (
      <FadeInView>
        {/* KPI strip */}
        <View
          style={{
            flexDirection: 'row',
            flexWrap: 'wrap',
            gap: spacing.sm,
            marginBottom: spacing.md,
          }}
        >
          <StatTile
            label={M.openValue}
            value={formatCurrency(p?.open_value ?? 0)}
          />
          <StatTile
            label={M.weightedValue}
            value={formatCurrency(p?.weighted_open_value ?? 0)}
            tint={c.info}
          />
          <StatTile
            label={M.wonValue}
            value={formatCurrency(p?.won_value ?? 0)}
            tint={c.success}
          />
          <StatTile
            label={M.winRate}
            value={`%${p?.win_rate_pct ?? 0}`}
          />
        </View>

        {/* Kanban board: horizontal scroll of stage columns (web-safe — the
            outer page scrolls vertically, this scrolls horizontally). */}
        <ScrollView
          horizontal
          showsHorizontalScrollIndicator={false}
          contentContainerStyle={{ gap: spacing.md, paddingBottom: spacing.sm }}
          testID="mice-kanban"
        >
          {OPP_STAGES.map((stage) => {
            const colOpps = opps.filter((o) => (o.stage || 'lead') === stage);
            const s = summaryByStage.get(stage);
            const count = s?.count ?? colOpps.length;
            const value = s?.total_value ?? 0;
            const tint = toneColor(stageTone(stage), c);
            return (
              <View
                key={stage}
                testID={`mice-kanban-col-${stage}`}
                style={{ width: 280 }}
              >
                <View
                  style={{
                    flexDirection: 'row',
                    alignItems: 'center',
                    justifyContent: 'space-between',
                    paddingHorizontal: spacing.xs,
                    paddingBottom: spacing.sm,
                  }}
                >
                  <View style={{ flexDirection: 'row', alignItems: 'center', gap: spacing.sm }}>
                    <View
                      style={{
                        width: 8,
                        height: 8,
                        borderRadius: radius.pill,
                        backgroundColor: tint,
                      }}
                    />
                    <H2 style={{ fontSize: 16 }}>{stageLabel(stage)}</H2>
                    <Badge label={String(count)} tone={stageTone(stage)} />
                  </View>
                </View>
                {value > 0 ? (
                  <Muted style={{ paddingHorizontal: spacing.xs, marginBottom: spacing.sm }}>
                    {formatCurrency(value)}
                  </Muted>
                ) : null}
                {colOpps.length === 0 ? (
                  <View
                    style={{
                      borderRadius: radius.lg,
                      borderWidth: 1,
                      borderStyle: 'dashed',
                      borderColor: c.border,
                      paddingVertical: spacing.lg,
                      alignItems: 'center',
                    }}
                  >
                    <Muted>{tr.app.empty}</Muted>
                  </View>
                ) : (
                  colOpps.map(renderKanbanCard)
                )}
              </View>
            );
          })}
        </ScrollView>
      </FadeInView>
    );
  };

  // ── List renderers (premium cards with status accent) ──────────────────────
  const renderEvent = (e: MiceEvent) => (
    <Pressable
      key={e.id}
      testID={`mice-event-${e.id}`}
      onPress={() => router.push(`${ROUTES.mice}/${e.id}`)}
      accessibilityRole="button"
    >
      {({ pressed }) => (
        <Card
          accent={toneColor(eventTone(e.status), c)}
          style={{ marginBottom: spacing.sm, opacity: pressed ? 0.85 : 1 }}
        >
          <View
            style={{
              flexDirection: 'row',
              justifyContent: 'space-between',
              alignItems: 'flex-start',
            }}
          >
            <View style={{ flex: 1, paddingRight: spacing.sm }}>
              <Body style={{ fontWeight: '700' }}>{e.name || '—'}</Body>
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
                {M.pax}: {e.expected_pax}
              </Muted>
            ) : null}
            {typeof e.totals?.grand_total === 'number' ? (
              <Body style={{ fontWeight: '700', marginTop: 2 }}>
                {formatCurrency(e.totals.grand_total, e.totals.currency)}
              </Body>
            ) : null}
          </View>
        </Card>
      )}
    </Pressable>
  );

  const renderAccount = (a: MiceAccount) => (
    <Card
      key={a.id}
      testID={`mice-account-${a.id}`}
      accent={a.active === false ? c.textMuted : c.primary}
      style={{ marginBottom: spacing.sm }}
    >
      <View
        style={{
          flexDirection: 'row',
          justifyContent: 'space-between',
          alignItems: 'flex-start',
        }}
      >
        <View style={{ flex: 1, paddingRight: spacing.sm }}>
          <Body style={{ fontWeight: '700' }}>{a.name || '—'}</Body>
          {a.industry ? <Muted>{a.industry}</Muted> : null}
        </View>
        {a.active === false ? (
          <Badge label={M.inactive} tone="default" />
        ) : null}
      </View>
      <View style={{ marginTop: spacing.sm, gap: 2 }}>
        {a.tax_no ? (
          <Muted>
            {M.taxNo}: {a.tax_no}
          </Muted>
        ) : null}
        {a.email ? <Muted>{a.email}</Muted> : null}
        {typeof a.credit_limit === 'number' && a.credit_limit > 0 ? (
          <Muted>
            {M.creditLimit}: {formatCurrency(a.credit_limit)}
          </Muted>
        ) : null}
        {typeof a.payment_terms_days === 'number' && a.payment_terms_days > 0 ? (
          <Muted>
            {M.paymentTerms}: {a.payment_terms_days}
          </Muted>
        ) : null}
      </View>
    </Card>
  );

  const renderOpportunity = (o: MiceOpportunity) => (
    <Pressable
      key={o.id}
      testID={`mice-opp-list-${o.id}`}
      onPress={() => openStageSheet(o)}
      accessibilityRole="button"
      accessibilityLabel={`${o.title || ''} — ${M.moveStage}`}
    >
      {({ pressed }) => (
        <Card
          accent={toneColor(stageTone(o.stage), c)}
          style={{ marginBottom: spacing.sm, opacity: pressed ? 0.85 : 1 }}
        >
          <View
            style={{
              flexDirection: 'row',
              justifyContent: 'space-between',
              alignItems: 'flex-start',
            }}
          >
            <View style={{ flex: 1, paddingRight: spacing.sm }}>
              <Body style={{ fontWeight: '700' }}>{o.title || '—'}</Body>
              {o.account_id && accountName.get(o.account_id) ? (
                <Muted>
                  {M.account}: {accountName.get(o.account_id)}
                </Muted>
              ) : null}
            </View>
            <Badge label={stageLabel(o.stage)} tone={stageTone(o.stage)} />
          </View>
          <View style={{ marginTop: spacing.sm, gap: 2 }}>
            {typeof o.estimated_value === 'number' && o.estimated_value > 0 ? (
              <Body style={{ fontWeight: '700' }}>
                {formatCurrency(o.estimated_value, o.currency)}
              </Body>
            ) : null}
            {typeof o.probability === 'number' ? (
              <Muted>
                {M.probability}: %{o.probability}
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
          <View style={{ marginTop: spacing.sm }}>
            <Badge label={M.moveStage} tone="primary" icon="swap-horizontal-outline" />
          </View>
        </Card>
      )}
    </Pressable>
  );

  const renderGroup = (g: GroupReservation) => (
    <Card
      key={g.id}
      testID={`mice-group-${g.id}`}
      accent={toneColor(groupTone(g.status), c)}
      style={{ marginBottom: spacing.sm }}
    >
      <View
        style={{
          flexDirection: 'row',
          justifyContent: 'space-between',
          alignItems: 'flex-start',
        }}
      >
        <View style={{ flex: 1, paddingRight: spacing.sm }}>
          <Body style={{ fontWeight: '700' }}>{g.group_name || '—'}</Body>
          {g.contact_person ? (
            <Muted>
              {M.contact}: {g.contact_person}
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
            {M.rooms}: {g.rooms_assigned ?? 0}/{g.total_rooms}{' '}
            ({M.roomsAssigned})
          </Muted>
        ) : null}
      </View>
    </Card>
  );

  const renderBlock = (b: GroupBlock) => (
    <Card
      key={b.id}
      testID={`mice-block-${b.id}`}
      accent={toneColor(groupTone(b.status), c)}
      style={{ marginBottom: spacing.sm }}
    >
      <View
        style={{
          flexDirection: 'row',
          justifyContent: 'space-between',
          alignItems: 'flex-start',
        }}
      >
        <View style={{ flex: 1, paddingRight: spacing.sm }}>
          <Body style={{ fontWeight: '700' }}>{b.group_name || '—'}</Body>
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
            {M.rooms}: {b.rooms_picked_up ?? 0}/{b.total_rooms}{' '}
            ({M.roomsPickedUp})
          </Muted>
        ) : null}
        {b.room_type ? (
          <Muted>
            {M.roomType}: {b.room_type}
          </Muted>
        ) : null}
        {typeof b.group_rate === 'number' && b.group_rate > 0 ? (
          <Muted>
            {M.groupRate}: {formatCurrency(b.group_rate)}
          </Muted>
        ) : null}
      </View>
    </Card>
  );

  const renderContract = (k: CorporateContract) => (
    <Card
      key={k.id}
      testID={`mice-contract-${k.id}`}
      accent={toneColor(contractTone(k.status), c)}
      style={{ marginBottom: spacing.sm }}
    >
      <View
        style={{
          flexDirection: 'row',
          justifyContent: 'space-between',
          alignItems: 'flex-start',
        }}
      >
        <View style={{ flex: 1, paddingRight: spacing.sm }}>
          <Body style={{ fontWeight: '700' }}>{k.company_name || '—'}</Body>
          {k.contact_person ? (
            <Muted>
              {M.contact}: {k.contact_person}
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
            {M.roomNights}: {k.room_nights_used ?? 0}/
            {k.room_nights_committed}
          </Muted>
        ) : null}
        {typeof k.discount_percentage === 'number' && k.discount_percentage > 0 ? (
          <Muted>
            {M.discount}: %{k.discount_percentage}
          </Muted>
        ) : null}
        {typeof k.contracted_rate === 'number' && k.contracted_rate > 0 ? (
          <Muted>
            {M.contractRate}: {formatCurrency(k.contracted_rate)}
          </Muted>
        ) : null}
        {typeof k.days_until_expiry === 'number' && k.days_until_expiry > 0 ? (
          <Muted>
            {M.expiresIn}: {k.days_until_expiry} {M.days}
          </Muted>
        ) : null}
      </View>
    </Card>
  );

  const renderSpace = (s: import('../../../src/api/mice').MiceSpace) => (
    <Card
      key={s.id}
      testID={`mice-space-${s.id}`}
      accent={s.active === false ? c.textMuted : c.success}
      style={{ marginBottom: spacing.sm }}
    >
      <View
        style={{
          flexDirection: 'row',
          justifyContent: 'space-between',
          alignItems: 'flex-start',
        }}
      >
        <View style={{ flex: 1, paddingRight: spacing.sm }}>
          <Body style={{ fontWeight: '700' }}>{s.name}</Body>
          {s.location ? (
            <Muted>
              {M.location}: {s.location}
            </Muted>
          ) : null}
        </View>
        <Badge
          label={s.active === false ? M.unavailable : M.available}
          tone={s.active === false ? 'default' : 'success'}
        />
      </View>
      <View style={{ marginTop: spacing.xs, gap: 2 }}>
        {typeof s.area_m2 === 'number' ? (
          <Muted>
            {M.area}: {s.area_m2} m²
          </Muted>
        ) : null}
        {typeof s.capacity_theatre === 'number' ? (
          <Muted>
            {M.capacity}: {s.capacity_theatre}
          </Muted>
        ) : null}
        {typeof s.daily_rate === 'number' ? (
          <Muted>
            {M.dailyRate}: {formatCurrency(s.daily_rate, s.currency)}
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

  const stageOptions = activeOpp
    ? OPP_STAGES.filter((s) => s !== (activeOpp.stage || 'lead'))
    : [];

  return (
    <ScrollView
      style={{ flex: 1, backgroundColor: c.bg }}
      contentContainerStyle={[{ padding: spacing.lg, paddingBottom: spacing.xl }, webCenter]}
    >
      <H1>{M.title}</H1>

      <ScrollView
        horizontal
        showsHorizontalScrollIndicator={false}
        contentContainerStyle={{ gap: spacing.sm, marginTop: spacing.md, paddingRight: spacing.lg }}
      >
        <TabButton value="pipeline" label={M.tabPipeline} />
        <TabButton value="events" label={M.tabEvents} />
        <TabButton value="opportunities" label={M.tabOpportunities} />
        <TabButton value="accounts" label={M.tabCustomers} />
        <TabButton value="groups" label={M.tabContracts} />
      </ScrollView>

      <View style={{ marginTop: spacing.md }}>
        {tab === 'pipeline' ? (
          <>
            <SectionTitle title={M.pipeline} />
            {renderPipeline()}
          </>
        ) : null}

        {tab === 'events' ? (
          <>
            <SectionTitle title={M.events} />
            {listBlock(eventsQ, 'calendar-outline', M.noEvents, renderEvent)}

            <SectionTitle title={M.spaces} />
            {listBlock(spacesQ, 'business-outline', M.noSpaces, renderSpace)}
          </>
        ) : null}

        {tab === 'accounts' ? (
          <>
            <SectionTitle title={M.accounts} />
            {listBlock(accountsQ, 'people-outline', M.noAccounts, renderAccount)}
          </>
        ) : null}

        {tab === 'opportunities' ? (
          <>
            <SectionTitle title={M.opportunities} />
            {listBlock(
              oppsQ,
              'briefcase-outline',
              M.noOpportunities,
              renderOpportunity,
            )}
          </>
        ) : null}

        {tab === 'groups' ? (
          <>
            <SectionTitle title={M.groupReservations} />
            {listBlock(groupsQ, 'people-circle-outline', M.noGroups, renderGroup)}

            <SectionTitle title={M.groupBlocks} />
            {listBlock(blocksQ, 'grid-outline', M.noBlocks, renderBlock)}

            <SectionTitle title={M.corporateContracts} />
            {listBlock(
              contractsQ,
              'document-text-outline',
              M.noContracts,
              renderContract,
            )}
          </>
        ) : null}
      </View>

      {/* ── Stage-move sheet (kanban + opportunity list) ──────────────────── */}
      <ActionSheet
        visible={activeOpp !== null}
        onClose={() => setActiveOpp(null)}
        title={activeOpp?.title || M.changeStage}
        testID="mice-stage-sheet"
      >
        {activeOpp ? (
          <>
            <View style={{ flexDirection: 'row', alignItems: 'center', gap: spacing.sm }}>
              <Muted>{M.currentStage}:</Muted>
              <Badge label={stageLabel(activeOpp.stage)} tone={stageTone(activeOpp.stage)} />
            </View>

            {stageError ? (
              <Body style={{ color: c.danger, marginTop: spacing.sm }} testID="mice-stage-error">
                {stageError}
              </Body>
            ) : null}

            <Muted style={{ marginTop: spacing.md }}>{M.changeStage}</Muted>
            {stageOptions.length === 0 ? (
              <Body style={{ marginTop: spacing.sm }}>{M.noStageOptions}</Body>
            ) : (
              <Card padded={false} style={{ marginTop: spacing.sm }}>
                {stageOptions.map((s, i) => (
                  <ListRow
                    key={s}
                    testID={`mice-stage-opt-${s}`}
                    icon="flag-outline"
                    iconColor={toneColor(stageTone(s), c)}
                    label={stageLabel(s)}
                    onPress={() => submitStage(s)}
                    showChevron={!transitionMut.isPending}
                    last={i === stageOptions.length - 1}
                  />
                ))}
              </Card>
            )}

            <View style={{ marginTop: spacing.lg }}>
              <Button
                title={tr.app.cancel}
                variant="secondary"
                onPress={() => setActiveOpp(null)}
                fullWidth
              />
            </View>
          </>
        ) : null}
      </ActionSheet>
    </ScrollView>
  );
}
