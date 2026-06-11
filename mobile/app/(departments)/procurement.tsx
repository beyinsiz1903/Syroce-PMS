import React, { useState } from 'react';
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
  PROCUREMENT_TABS,
  screenRedirectsToHub,
  type ProcurementTab,
} from '../../src/utils/departmentScreens';
import {
  listPurchaseRequests,
  listPurchaseOrders,
  type PurchaseRequest,
  type PurchaseOrder,
} from '../../src/api/procurement';
import { formatCurrency, formatDate } from '../../src/utils/format';

type Tab = ProcurementTab;

function statusTone(status?: string):
  | 'default'
  | 'success'
  | 'warning'
  | 'danger'
  | 'info'
  | 'primary' {
  switch (status) {
    case 'approved':
    case 'received':
      return 'success';
    case 'rejected':
    case 'cancelled':
      return 'danger';
    case 'submitted':
    case 'sent':
    case 'partially_received':
      return 'warning';
    case 'converted':
      return 'info';
    default:
      return 'default';
  }
}

function prStatusLabel(status?: string): string {
  const map = tr.departments.procurement.prStatuses as Record<string, string>;
  return (status && map[status]) || status || '—';
}

function poStatusLabel(status?: string): string {
  const map = tr.departments.procurement.poStatuses as Record<string, string>;
  return (status && map[status]) || status || '—';
}

// Read-only Procurement screen. Two tabs: purchase requests (talepler) and
// purchase orders (siparişler). Backend GET reads only require auth; the
// (departments) procurement entitlement decides whether we show the screen.
// PR/PO approvals flow through the unified approvals backbone; writes stay
// backend-gated by require_procurement.
export default function ProcurementScreen() {
  const c = useTheme();
  const rawRole = useAuthStore((s) => s.user?.role);
  const procurementAccess = !screenRedirectsToHub('procurement', rawRole);
  const [tab, setTab] = useState<Tab>('requests');

  const prQ = useQuery({
    queryKey: ['proc-prs'],
    queryFn: () => listPurchaseRequests(),
    enabled: procurementAccess && tab === 'requests',
  });
  const poQ = useQuery({
    queryKey: ['proc-pos'],
    queryFn: () => listPurchaseOrders(),
    enabled: procurementAccess && tab === 'orders',
  });

  if (screenRedirectsToHub('procurement', rawRole)) {
    return <Redirect href={ROUTES.departments} />;
  }

  const tabLabels: Record<Tab, string> = {
    requests: tr.departments.procurement.tabRequests,
    orders: tr.departments.procurement.tabOrders,
  };

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

  const renderRequest = (pr: PurchaseRequest) => (
    <Card key={pr.id} style={{ marginBottom: spacing.sm }}>
      <View
        style={{
          flexDirection: 'row',
          justifyContent: 'space-between',
          alignItems: 'flex-start',
        }}
      >
        <View style={{ flex: 1, paddingRight: spacing.sm }}>
          <Body style={{ fontWeight: '600' }}>{pr.pr_no || '—'}</Body>
          {pr.department ? (
            <Muted>
              {tr.departments.procurement.department}: {pr.department}
            </Muted>
          ) : null}
        </View>
        <Badge label={prStatusLabel(pr.status)} tone={statusTone(pr.status)} />
      </View>
      <View style={{ marginTop: spacing.sm, gap: 2 }}>
        {pr.requester ? (
          <Muted>
            {tr.departments.procurement.requester}: {pr.requester}
          </Muted>
        ) : null}
        {pr.needed_by ? (
          <Muted>
            {tr.departments.procurement.neededBy}: {formatDate(pr.needed_by)}
          </Muted>
        ) : null}
        <Muted>
          {tr.departments.procurement.lines}: {(pr.lines || []).length}
        </Muted>
        {typeof pr.lines_total === 'number' ? (
          <Muted>
            {tr.departments.procurement.total}: {formatCurrency(pr.lines_total)}
          </Muted>
        ) : null}
      </View>
    </Card>
  );

  const renderOrder = (po: PurchaseOrder) => (
    <Card key={po.id} style={{ marginBottom: spacing.sm }}>
      <View
        style={{
          flexDirection: 'row',
          justifyContent: 'space-between',
          alignItems: 'flex-start',
        }}
      >
        <View style={{ flex: 1, paddingRight: spacing.sm }}>
          <Body style={{ fontWeight: '600' }}>{po.po_no || '—'}</Body>
          {po.supplier_name ? (
            <Muted>
              {tr.departments.procurement.supplier}: {po.supplier_name}
            </Muted>
          ) : null}
        </View>
        <Badge label={poStatusLabel(po.status)} tone={statusTone(po.status)} />
      </View>
      <View style={{ marginTop: spacing.sm, gap: 2 }}>
        {po.expected_delivery ? (
          <Muted>
            {tr.departments.procurement.expectedDelivery}: {formatDate(po.expected_delivery)}
          </Muted>
        ) : null}
        <Muted>
          {tr.departments.procurement.lines}: {(po.lines || []).length}
        </Muted>
        {typeof po.grand_total === 'number' ? (
          <Muted>
            {tr.departments.procurement.total}:{' '}
            {formatCurrency(po.grand_total, po.currency)}
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
      <H1>{tr.departments.procurement.title}</H1>

      <View style={{ flexDirection: 'row', gap: spacing.sm, marginTop: spacing.md }}>
        {PROCUREMENT_TABS.map((value) => (
          <TabButton key={value} value={value} label={tabLabels[value]} />
        ))}
      </View>

      {tab === 'requests' ? (
        <>
          <SectionTitle title={tr.departments.procurement.requests} />
          {(() => {
            const state = (
              <DepartmentListState
                loading={prQ.isLoading}
                error={prQ.error}
                isEmpty={(prQ.data || []).length === 0}
                emptyText={tr.departments.procurement.noRequests}
              />
            );
            return state ?? <View>{(prQ.data || []).map(renderRequest)}</View>;
          })()}
        </>
      ) : null}

      {tab === 'orders' ? (
        <>
          <SectionTitle title={tr.departments.procurement.orders} />
          {(() => {
            const state = (
              <DepartmentListState
                loading={poQ.isLoading}
                error={poQ.error}
                isEmpty={(poQ.data || []).length === 0}
                emptyText={tr.departments.procurement.noOrders}
              />
            );
            return state ?? <View>{(poQ.data || []).map(renderOrder)}</View>;
          })()}
        </>
      ) : null}
    </ScrollView>
  );
}
