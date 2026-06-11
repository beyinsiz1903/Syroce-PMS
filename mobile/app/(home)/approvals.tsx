import React, { useCallback, useState } from 'react';
import { RefreshControl, ScrollView, View } from 'react-native';
import { useMutation, useQuery, useQueryClient } from '@tanstack/react-query';
import { Badge, Body, Button, Card, EmptyState, Field, H1, H2, Muted, SkeletonCard } from '../../src/components/ui';
import { OfflineBanner } from '../../src/components/OfflineBanner';
import { spacing, useTheme } from '../../src/theme';
import { tr } from '../../src/i18n/tr';
import { errorMessage, isOffline } from '../../src/utils/errors';
import { haptic } from '../../src/hooks/useHaptic';
import { formatCurrency } from '../../src/utils/format';
import { ApprovalAction, ApprovalItem, actOnApproval, getApprovals } from '../../src/api/hub';

function priorityTone(priority: string): 'danger' | 'warning' | 'default' {
  if (priority === 'urgent') return 'danger';
  if (priority === 'high') return 'warning';
  return 'default';
}

function priorityLabel(priority: string): string {
  if (priority === 'urgent') return tr.hub.priorityUrgent;
  if (priority === 'high') return tr.hub.priorityHigh;
  return tr.hub.priorityNormal;
}

function ApprovalRow({ item }: { item: ApprovalItem }) {
  const c = useTheme();
  const qc = useQueryClient();
  const [rejecting, setRejecting] = useState(false);
  const [confirming, setConfirming] = useState(false);
  const [reason, setReason] = useState('');
  const [reasonError, setReasonError] = useState(false);

  const mutation = useMutation({
    mutationFn: (vars: { action: ApprovalAction; reason?: string }) =>
      actOnApproval(item, vars.action, vars.reason),
    onSuccess: () => {
      haptic.success();
      setRejecting(false);
      setConfirming(false);
      setReason('');
      setReasonError(false);
      qc.invalidateQueries({ queryKey: ['hub-approvals'] });
      qc.invalidateQueries({ queryKey: ['hub-today'] });
    },
    onError: () => {
      haptic.error();
    },
  });

  // Inline two-step confirm (NOT Alert.alert — a no-op on Expo Web, which left
  // approve/reject silently broken there). Tapping "Onayla" reveals an inline
  // confirm row; tapping it again fires the mutation. Every action stays a
  // tap-button, so the flow is fully usable + e2e-reachable on web and native.
  const onApprovePress = () => {
    haptic.tap();
    if (mutation.isError) mutation.reset();
    setRejecting(false);
    setConfirming((v) => !v);
  };

  const onApproveConfirm = () => {
    mutation.mutate({ action: 'approve' });
  };

  const onRejectPress = () => {
    haptic.tap();
    if (mutation.isError) mutation.reset();
    setReasonError(false);
    setConfirming(false);
    setRejecting((v) => !v);
  };

  const onRejectConfirm = () => {
    const trimmed = reason.trim();
    if (!trimmed) {
      setReasonError(true);
      return;
    }
    mutation.mutate({ action: 'reject', reason: trimmed });
  };

  const deptApproved = item.kind === 'leave' && item.status === 'dept_approved';
  const consentPending =
    item.kind === 'shift_swap' && item.target_consent_status !== 'approved';

  return (
    <Card style={{ marginBottom: spacing.sm }}>
      <View style={{ flexDirection: 'row', justifyContent: 'space-between', gap: spacing.sm }}>
        <Body style={{ flex: 1, fontWeight: '700' }}>{item.title}</Body>
        {item.priority && item.priority !== 'normal' ? (
          <Badge label={priorityLabel(item.priority)} tone={priorityTone(item.priority)} />
        ) : null}
      </View>
      {item.requested_by ? (
        <Muted style={{ marginTop: spacing.xs }}>
          {tr.hub.requestedBy}:{' '}
          <Body style={{ fontWeight: '700' }}>{item.requested_by}</Body>
        </Muted>
      ) : null}
      {typeof item.amount === 'number' ? (
        <Muted style={{ marginTop: spacing.xs }}>
          {tr.hub.amountLabel}:{' '}
          <Body style={{ fontWeight: '700' }}>{formatCurrency(item.amount)}</Body>
        </Muted>
      ) : null}
      {deptApproved ? (
        <View style={{ marginTop: spacing.xs }}>
          <Badge label={tr.hub.deptApprovedBadge} tone="info" />
        </View>
      ) : null}
      {consentPending ? (
        <Muted style={{ marginTop: spacing.xs }}>{tr.hub.consentPending}</Muted>
      ) : null}

      {mutation.isError ? (
        <Muted style={{ marginTop: spacing.xs, color: c.danger }}>
          {errorMessage(mutation.error, tr.errors.generic)}
        </Muted>
      ) : null}

      {rejecting ? (
        <View style={{ marginTop: spacing.sm, gap: spacing.sm }}>
          <Field
            label={tr.hub.rejectReasonLabel}
            placeholder={tr.hub.rejectReasonPlaceholder}
            value={reason}
            onChangeText={(t) => {
              setReason(t);
              if (reasonError) setReasonError(false);
            }}
            multiline
            editable={!mutation.isPending}
          />
          {reasonError ? (
            <Muted style={{ color: c.danger }}>{tr.hub.rejectReasonRequired}</Muted>
          ) : null}
          <View style={{ flexDirection: 'row', gap: spacing.sm }}>
            <Button
              title={tr.app.cancel}
              variant="secondary"
              onPress={() => {
                setRejecting(false);
                setReason('');
                setReasonError(false);
              }}
              disabled={mutation.isPending}
              style={{ flex: 1 }}
            />
            <Button
              title={tr.hub.reject}
              variant="danger"
              icon="close-circle"
              onPress={onRejectConfirm}
              loading={mutation.isPending}
              style={{ flex: 1 }}
            />
          </View>
        </View>
      ) : confirming ? (
        <View style={{ marginTop: spacing.sm, gap: spacing.sm }}>
          <Muted>{tr.hub.approveConfirmTitle}</Muted>
          <View style={{ flexDirection: 'row', gap: spacing.sm }}>
            <Button
              title={tr.app.cancel}
              variant="secondary"
              onPress={() => setConfirming(false)}
              disabled={mutation.isPending}
              style={{ flex: 1 }}
            />
            <Button
              title={tr.hub.approve}
              variant="success"
              icon="checkmark-circle"
              onPress={onApproveConfirm}
              loading={mutation.isPending}
              style={{ flex: 1 }}
            />
          </View>
        </View>
      ) : (
        <View style={{ flexDirection: 'row', gap: spacing.sm, marginTop: spacing.sm }}>
          <Button
            title={tr.hub.reject}
            variant="outline"
            icon="close-circle"
            onPress={onRejectPress}
            disabled={mutation.isPending}
            style={{ flex: 1 }}
          />
          <Button
            title={tr.hub.approve}
            variant="success"
            icon="checkmark-circle"
            onPress={onApprovePress}
            disabled={mutation.isPending}
            style={{ flex: 1 }}
          />
        </View>
      )}
    </Card>
  );
}

export default function ApprovalsScreen() {
  const c = useTheme();
  const approvals = useQuery({ queryKey: ['hub-approvals'], queryFn: getApprovals });

  const refreshing = approvals.isFetching && !approvals.isLoading;
  const onRefresh = useCallback(() => {
    approvals.refetch();
  }, [approvals]);

  const offline = approvals.isError && isOffline(approvals.error);
  const categories = approvals.data?.categories ?? [];

  return (
    <View style={{ flex: 1, backgroundColor: c.bg }} testID="smoke-home-approvals">
      <ScrollView
        contentContainerStyle={{ padding: spacing.lg, paddingBottom: 120, gap: spacing.md }}
        refreshControl={
          <RefreshControl refreshing={refreshing} onRefresh={onRefresh} tintColor={c.primary} />
        }
      >
        <OfflineBanner visible={offline} />
        <H1>{tr.hub.approvalsTitle}</H1>

        {approvals.isLoading ? (
          <>
            <SkeletonCard />
            <SkeletonCard />
          </>
        ) : approvals.isError ? (
          <Card>
            <Muted>{tr.hub.loadError}</Muted>
          </Card>
        ) : categories.length === 0 ? (
          <EmptyState icon="checkmark-done-circle-outline" title={tr.hub.approvalsEmpty} />
        ) : (
          categories.map((cat) => (
            <View key={cat.key} style={{ gap: spacing.sm }}>
              <H2>
                {cat.label} ({cat.count})
              </H2>
              {cat.items.length === 0 ? (
                <Card>
                  <Muted>{tr.hub.approvalsEmpty}</Muted>
                </Card>
              ) : (
                cat.items.map((item) => <ApprovalRow key={`${cat.key}-${item.id}`} item={item} />)
              )}
            </View>
          ))
        )}
      </ScrollView>
    </View>
  );
}
