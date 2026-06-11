import React, { useCallback, useState } from 'react';
import { ActivityIndicator, Pressable, RefreshControl, ScrollView, Text, View } from 'react-native';
import { Ionicons } from '@expo/vector-icons';
import { useMutation, useQuery, useQueryClient } from '@tanstack/react-query';
import { Badge, Body, Card, EmptyState, Field, H1, H2, Muted, SkeletonCard } from '../../src/components/ui';
import { OfflineBanner } from '../../src/components/OfflineBanner';
import { radius, spacing, useTheme } from '../../src/theme';
import { tr } from '../../src/i18n/tr';
import { errorMessage, isOffline } from '../../src/utils/errors';
import { haptic } from '../../src/hooks/useHaptic';
import { formatCurrency } from '../../src/utils/format';
import { ApprovalAction, ApprovalItem, actOnApproval, getApprovals } from '../../src/api/hub';

type IoniconName = keyof typeof Ionicons.glyphMap;

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

// Basparmak-bolgesi aksiyonu: boslukSUZ %50/%50 segmentli cubugun tek yarisi.
// Buyuk (52px) dokunma hedefi + ikon + etiket. `loading` icin spinner.
function ActionHalf({
  label,
  icon,
  onPress,
  bg,
  fg,
  loading,
  disabled,
  testID,
}: {
  label: string;
  icon: IoniconName;
  onPress: () => void;
  bg: string;
  fg: string;
  loading?: boolean;
  disabled?: boolean;
  testID?: string;
}) {
  return (
    <Pressable
      testID={testID}
      onPress={onPress}
      disabled={disabled || loading}
      accessibilityRole="button"
      accessibilityLabel={label}
      style={({ pressed }) => ({
        flex: 1,
        minHeight: 52,
        flexDirection: 'row',
        alignItems: 'center',
        justifyContent: 'center',
        gap: spacing.xs,
        backgroundColor: bg,
        opacity: disabled ? 0.5 : pressed ? 0.85 : 1,
      })}
    >
      {loading ? (
        <ActivityIndicator color={fg} />
      ) : (
        <>
          <Ionicons name={icon} size={18} color={fg} />
          <Text style={{ color: fg, fontSize: 16, fontWeight: '700' }}>{label}</Text>
        </>
      )}
    </Pressable>
  );
}

// Iki yariyi araya 1px ayracla, dis kenarlari yuvarlatilmis tek bir segment
// kontrolu olarak bir araya getirir (yarilar arasinda hic bosluk yok).
function SegBar({ left, right }: { left: React.ReactNode; right: React.ReactNode }) {
  const c = useTheme();
  return (
    <View
      style={{
        flexDirection: 'row',
        borderRadius: radius.md,
        overflow: 'hidden',
        borderWidth: 1,
        borderColor: c.border,
      }}
    >
      {left}
      <View style={{ width: 1, backgroundColor: c.border }} />
      {right}
    </View>
  );
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
          <SegBar
            left={
              <ActionHalf
                label={tr.app.cancel}
                icon="arrow-undo"
                onPress={() => {
                  setRejecting(false);
                  setReason('');
                  setReasonError(false);
                }}
                bg={c.surfaceAlt}
                fg={c.text}
                disabled={mutation.isPending}
              />
            }
            right={
              <ActionHalf
                testID="approval-reject-confirm"
                label={tr.hub.reject}
                icon="close-circle"
                onPress={onRejectConfirm}
                bg={c.danger}
                fg="#ffffff"
                loading={mutation.isPending}
              />
            }
          />
        </View>
      ) : confirming ? (
        <View style={{ marginTop: spacing.sm, gap: spacing.sm }}>
          <Muted>{tr.hub.approveConfirmTitle}</Muted>
          <SegBar
            left={
              <ActionHalf
                label={tr.app.cancel}
                icon="arrow-undo"
                onPress={() => setConfirming(false)}
                bg={c.surfaceAlt}
                fg={c.text}
                disabled={mutation.isPending}
              />
            }
            right={
              <ActionHalf
                testID="approval-approve-confirm"
                label={tr.hub.approve}
                icon="checkmark-circle"
                onPress={onApproveConfirm}
                bg={c.success}
                fg="#ffffff"
                loading={mutation.isPending}
              />
            }
          />
        </View>
      ) : (
        <View style={{ marginTop: spacing.sm }}>
          <SegBar
            left={
              <ActionHalf
                testID="approval-reject"
                label={tr.hub.reject}
                icon="close-circle"
                onPress={onRejectPress}
                bg={c.danger + '14'}
                fg={c.danger}
                disabled={mutation.isPending}
              />
            }
            right={
              <ActionHalf
                testID="approval-approve"
                label={tr.hub.approve}
                icon="checkmark-circle"
                onPress={onApprovePress}
                bg={c.success}
                fg="#ffffff"
                disabled={mutation.isPending}
              />
            }
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
