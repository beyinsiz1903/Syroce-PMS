import React, { useCallback, useState } from 'react';
import { Alert, RefreshControl, ScrollView, View } from 'react-native';
import { useMutation, useQuery, useQueryClient } from '@tanstack/react-query';
import { Badge, Body, Button, Card, Field, H1, H2, Muted, SkeletonCard } from '../../src/components/ui';
import { OfflineBanner } from '../../src/components/OfflineBanner';
import { spacing, useTheme } from '../../src/theme';
import { tr } from '../../src/i18n/tr';
import { errorMessage, isOffline } from '../../src/utils/errors';
import { haptic } from '../../src/hooks/useHaptic';
import { ApprovalAction, ApprovalItem, actOnApproval, getApprovals } from '../../src/api/hub';

function priorityTone(priority: string): 'danger' | 'warning' | 'default' {
  if (priority === 'urgent') return 'danger';
  if (priority === 'high') return 'warning';
  return 'default';
}

function ApprovalRow({ item }: { item: ApprovalItem }) {
  const qc = useQueryClient();
  const [rejecting, setRejecting] = useState(false);
  const [reason, setReason] = useState('');

  const mutation = useMutation({
    mutationFn: (vars: { action: ApprovalAction; reason?: string }) =>
      actOnApproval(item, vars.action, vars.reason),
    onSuccess: (_data, vars) => {
      haptic.success();
      Alert.alert(tr.app.success, vars.action === 'approve' ? tr.hub.approved : tr.hub.rejected);
      setRejecting(false);
      setReason('');
      qc.invalidateQueries({ queryKey: ['hub-approvals'] });
      qc.invalidateQueries({ queryKey: ['hub-today'] });
    },
    onError: (e) => {
      haptic.error();
      Alert.alert(tr.app.error, errorMessage(e, tr.errors.generic));
    },
  });

  const onApprove = () => {
    haptic.tap();
    Alert.alert(tr.hub.approveConfirmTitle, item.title, [
      { text: tr.app.cancel, style: 'cancel' },
      { text: tr.hub.approve, onPress: () => mutation.mutate({ action: 'approve' }) },
    ]);
  };

  const onRejectPress = () => {
    haptic.tap();
    setRejecting((v) => !v);
  };

  const onRejectConfirm = () => {
    const trimmed = reason.trim();
    if (!trimmed) {
      Alert.alert(tr.app.error, tr.hub.rejectReasonRequired);
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
        <Body style={{ flex: 1, fontWeight: '600' }}>{item.title}</Body>
        {item.priority && item.priority !== 'normal' ? (
          <Badge label={item.priority} tone={priorityTone(item.priority)} />
        ) : null}
      </View>
      {item.requested_by ? (
        <Muted style={{ marginTop: spacing.xs }}>
          {tr.hub.requestedBy}: {item.requested_by}
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

      {rejecting ? (
        <View style={{ marginTop: spacing.sm, gap: spacing.sm }}>
          <Field
            label={tr.hub.rejectReasonLabel}
            placeholder={tr.hub.rejectReasonPlaceholder}
            value={reason}
            onChangeText={setReason}
            multiline
            editable={!mutation.isPending}
          />
          <View style={{ flexDirection: 'row', gap: spacing.sm }}>
            <Button
              title={tr.app.cancel}
              variant="secondary"
              onPress={() => {
                setRejecting(false);
                setReason('');
              }}
              disabled={mutation.isPending}
              style={{ flex: 1 }}
            />
            <Button
              title={tr.hub.reject}
              variant="danger"
              onPress={onRejectConfirm}
              loading={mutation.isPending}
              style={{ flex: 1 }}
            />
          </View>
        </View>
      ) : (
        <View style={{ flexDirection: 'row', gap: spacing.sm, marginTop: spacing.sm }}>
          <Button
            title={tr.hub.reject}
            variant="ghost"
            onPress={onRejectPress}
            disabled={mutation.isPending}
            style={{ flex: 1 }}
          />
          <Button
            title={tr.hub.approve}
            variant="primary"
            onPress={onApprove}
            loading={mutation.isPending}
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
          <Card>
            <Muted>{tr.hub.approvalsEmpty}</Muted>
          </Card>
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
