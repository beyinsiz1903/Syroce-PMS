import React, { useState } from 'react';
import { Alert, Pressable, ScrollView, View } from 'react-native';
import { Redirect } from 'expo-router';
import { useQuery, useQueryClient } from '@tanstack/react-query';
import {
  ActionSheet,
  Badge,
  Body,
  Button,
  Card,
  EmptyState,
  Field,
  FormActions,
  H1,
  Muted,
  SectionTitle,
  SegmentedActions,
  ActionButton,
  SkeletonCard,
} from '../../src/components/ui';
import { spacing, radius, useTheme } from '../../src/theme';
import { tr } from '../../src/i18n/tr';
import { haptic } from '../../src/hooks/useHaptic';
import { useAuthStore } from '../../src/state/authStore';
import { ROUTES } from '../../src/navigation/routes';
import {
  createWorkOrder,
  listMaintenanceTasks,
  listWorkOrders,
  submitTechnicianTask,
  updateWorkOrderStatus,
  type MaintenanceTask,
  type WorkOrder,
} from '../../src/api/maintenance';
import { MaintenanceKanban } from '../../src/components/MaintenanceKanban';
import { errorMessage, isOffline } from '../../src/utils/errors';

const ISSUE_TYPES = [
  'plumbing',
  'hvac',
  'electrical',
  'furniture',
  'housekeeping_damage',
  'other',
] as const;
const PRIORITIES = ['low', 'normal', 'high', 'urgent'] as const;

function issueTypeLabel(t?: string): string {
  const map = tr.departments.maintenance.issueTypes as Record<string, string>;
  return (t && map[t]) || t || '—';
}

function priorityLabel(p?: string): string {
  const map = tr.departments.maintenance.priorities as Record<string, string>;
  return (p && map[p]) || p || '—';
}

function statusLabel(s?: string): string {
  const map = tr.departments.maintenance.statuses as Record<string, string>;
  return (s && map[s]) || s || '—';
}

function statusTone(s?: string): 'default' | 'success' | 'info' | 'warning' {
  switch (s) {
    case 'completed':
      return 'success';
    case 'in_progress':
    case 'started':
      return 'info';
    case 'needs_parts':
      return 'warning';
    default:
      return 'default';
  }
}

// Maintenance department screen: work-order list (status filter + color-coded
// cards) + create-work-order action sheet + single-tap technician task updates.
// The create + submit actions are gated by the backend require_module
// ("housekeeping"); the mobile `maintenanceAccess` entitlement mirrors that role
// set. Cosmetic only — the backend still enforces every write.
export default function MaintenanceScreen() {
  const c = useTheme();
  const qc = useQueryClient();
  const maintenanceAccess = useAuthStore((s) => s.maintenanceAccess);

  // Accent colour gives the field technician an at-a-glance read of the
  // assigned-task card's left edge — progress state.
  const statusAccent: Record<string, string> = {
    completed: c.success,
    in_progress: c.info,
    started: c.info,
    needs_parts: c.warning,
    open: c.primary,
  };

  // Create-work-order sheet + form state.
  const [createOpen, setCreateOpen] = useState(false);
  const [issueType, setIssueType] = useState<string>('');
  const [priority, setPriority] = useState<string>('normal');
  const [roomNumber, setRoomNumber] = useState('');
  const [description, setDescription] = useState('');
  const [creating, setCreating] = useState(false);
  const [createError, setCreateError] = useState<string | null>(null);

  // Technician-task update sheet state (one task at a time).
  const [activeTask, setActiveTask] = useState<MaintenanceTask | null>(null);
  const [taskNotes, setTaskNotes] = useState('');
  const [taskTime, setTaskTime] = useState('');
  const [submitting, setSubmitting] = useState(false);

  // The kanban needs every fault regardless of status so each column can fill,
  // so we fetch the full list (the board buckets client-side by status).
  const workOrdersQ = useQuery({
    queryKey: ['maint-work-orders'],
    queryFn: () => listWorkOrders(),
    enabled: maintenanceAccess,
  });
  const tasksQ = useQuery({
    queryKey: ['maint-tasks'],
    queryFn: listMaintenanceTasks,
    enabled: maintenanceAccess,
  });

  // Hard guard — a user without maintenance entitlement is sent to the hub.
  if (!maintenanceAccess) return <Redirect href={ROUTES.departments} />;

  const resetCreateForm = () => {
    setIssueType('');
    setPriority('normal');
    setRoomNumber('');
    setDescription('');
    setCreateError(null);
  };

  const openCreate = () => {
    resetCreateForm();
    setCreateOpen(true);
  };

  const onCreate = async () => {
    if (!issueType) {
      setCreateError(tr.departments.maintenance.issueTypeRequired);
      haptic.warning();
      return;
    }
    setCreating(true);
    setCreateError(null);
    try {
      await createWorkOrder({
        issue_type: issueType,
        priority,
        description: description || undefined,
        room_number: roomNumber || undefined,
        source: 'other',
      });
      haptic.success();
      setCreateOpen(false);
      resetCreateForm();
      qc.invalidateQueries({ queryKey: ['maint-work-orders'] });
      Alert.alert(tr.app.success, tr.departments.maintenance.created);
    } catch (e: unknown) {
      setCreateError(errorMessage(e, tr.errors.generic));
      haptic.error();
    } finally {
      setCreating(false);
    }
  };

  const openTask = (t: MaintenanceTask) => {
    setActiveTask(t);
    setTaskNotes('');
    setTaskTime('');
  };

  const onSubmitTask = async (status: 'started' | 'completed' | 'needs_parts') => {
    if (!activeTask) return;
    setSubmitting(true);
    try {
      await submitTechnicianTask({
        task_id: activeTask.id,
        status,
        notes: taskNotes || undefined,
        time_spent_minutes: taskTime ? parseInt(taskTime, 10) || undefined : undefined,
      });
      haptic.success();
      setActiveTask(null);
      setTaskNotes('');
      setTaskTime('');
      qc.invalidateQueries({ queryKey: ['maint-tasks'] });
      Alert.alert(tr.app.success, tr.departments.maintenance.taskUpdated);
    } catch (e: unknown) {
      Alert.alert(tr.app.error, errorMessage(e, tr.errors.generic));
      haptic.error();
    } finally {
      setSubmitting(false);
    }
  };

  // Single-select chip for the create-form issue type / priority pickers.
  const Chip: React.FC<{ active: boolean; label: string; onPress: () => void }> = ({
    active,
    label,
    onPress,
  }) => (
    <Pressable
      onPress={onPress}
      accessibilityRole="button"
      accessibilityState={{ selected: active }}
      style={{
        paddingVertical: spacing.xs,
        paddingHorizontal: spacing.md,
        borderRadius: radius.md,
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

  // Drag-drop drop handler — moves a fault between kanban columns by PATCHing
  // its status. Returns true only when the backend confirmed the change; on
  // failure the card stays in its source column (no optimistic move, no fake
  // success) and the operator sees an error. The backend re-validates RBAC.
  const onMoveWorkOrder = async (w: WorkOrder, targetStatus: string): Promise<boolean> => {
    try {
      const res = await updateWorkOrderStatus(w.id, targetStatus);
      if (!res?.updated) {
        haptic.warning();
        Alert.alert(tr.app.error, tr.departments.maintenance.kanban.moveError);
        return false;
      }
      haptic.success();
      await qc.invalidateQueries({ queryKey: ['maint-work-orders'] });
      return true;
    } catch (e: unknown) {
      haptic.error();
      Alert.alert(
        tr.app.error,
        errorMessage(e, tr.departments.maintenance.kanban.moveError),
      );
      return false;
    }
  };

  const renderTask = (t: MaintenanceTask) => (
    <Card key={t.id} accent={statusAccent[t.status || ''] ?? c.border} style={{ marginBottom: spacing.sm }}>
      <View
        style={{
          flexDirection: 'row',
          justifyContent: 'space-between',
          alignItems: 'flex-start',
        }}
      >
        <View style={{ flex: 1, paddingRight: spacing.sm }}>
          <Body style={{ fontWeight: '600' }}>{issueTypeLabel(t.issue_type)}</Body>
          {t.description ? <Muted>{t.description}</Muted> : null}
          {t.room_number ? (
            <Muted>
              {tr.departments.maintenance.room}: {t.room_number}
            </Muted>
          ) : null}
        </View>
        <Badge label={statusLabel(t.status)} tone={statusTone(t.status)} />
      </View>
      <View style={{ marginTop: spacing.md }}>
        <Button
          title={tr.departments.maintenance.submitUpdate}
          variant="secondary"
          icon="construct-outline"
          onPress={() => openTask(t)}
        />
      </View>
    </Card>
  );

  // Shared loading / error / empty / data renderer so both lists behave alike.
  function renderList<T extends { id: string }>(
    q: { isLoading: boolean; error: unknown; data?: T[] },
    opts: { icon: 'construct-outline' | 'clipboard-outline'; emptyTitle: string; emptyHint: string },
    renderItem: (item: T) => React.ReactNode,
  ): React.ReactNode {
    if (q.isLoading) {
      return (
        <View style={{ gap: spacing.sm }}>
          <SkeletonCard />
          <SkeletonCard />
        </View>
      );
    }
    if (q.error) {
      const msg = isOffline(q.error)
        ? tr.app.offline
        : errorMessage(q.error, tr.departments.maintenance.loadError);
      return (
        <Card>
          <Body>{msg}</Body>
        </Card>
      );
    }
    const items = q.data || [];
    if (items.length === 0) {
      return <EmptyState icon={opts.icon} title={opts.emptyTitle} message={opts.emptyHint} />;
    }
    return <View>{items.map(renderItem)}</View>;
  }

  return (
    <ScrollView
      style={{ flex: 1, backgroundColor: c.bg }}
      contentContainerStyle={{ padding: spacing.lg, paddingBottom: spacing.xl }}
    >
      <H1>{tr.departments.maintenance.title}</H1>
      <View style={{ marginTop: spacing.md }}>
        <Button
          title={tr.departments.maintenance.newWorkOrder}
          icon="add"
          onPress={openCreate}
          fullWidth
        />
      </View>

      {/* Work orders — Trello/Linear style kanban board (drag to update status) */}
      <SectionTitle title={tr.departments.maintenance.workOrders} />
      {workOrdersQ.isLoading ? (
        <View style={{ gap: spacing.sm }}>
          <SkeletonCard />
          <SkeletonCard />
        </View>
      ) : workOrdersQ.error ? (
        <Card>
          <Body>
            {isOffline(workOrdersQ.error)
              ? tr.app.offline
              : errorMessage(workOrdersQ.error, tr.departments.maintenance.loadError)}
          </Body>
        </Card>
      ) : (
        <MaintenanceKanban
          workOrders={workOrdersQ.data || []}
          onMove={onMoveWorkOrder}
        />
      )}

      {/* Technician tasks */}
      <SectionTitle title={tr.departments.maintenance.tasks} />
      {renderList(
        tasksQ,
        {
          icon: 'clipboard-outline',
          emptyTitle: tr.departments.maintenance.noTasks,
          emptyHint: tr.departments.maintenance.noTasksHint,
        },
        renderTask,
      )}

      {/* Create work order sheet */}
      <ActionSheet
        visible={createOpen}
        onClose={() => setCreateOpen(false)}
        title={tr.departments.maintenance.newWorkOrder}
      >
        {createError ? (
          <Body style={{ color: c.danger }}>{createError}</Body>
        ) : null}
        <Muted>{tr.departments.maintenance.issueType}</Muted>
        <View
          style={{
            flexDirection: 'row',
            flexWrap: 'wrap',
            gap: spacing.sm,
            marginBottom: spacing.sm,
          }}
        >
          {ISSUE_TYPES.map((t) => (
            <Chip
              key={t}
              active={issueType === t}
              label={issueTypeLabel(t)}
              onPress={() => setIssueType(t)}
            />
          ))}
        </View>

        <Muted>{tr.departments.maintenance.priority}</Muted>
        <View
          style={{
            flexDirection: 'row',
            flexWrap: 'wrap',
            gap: spacing.sm,
            marginBottom: spacing.sm,
          }}
        >
          {PRIORITIES.map((p) => (
            <Chip
              key={p}
              active={priority === p}
              label={priorityLabel(p)}
              onPress={() => setPriority(p)}
            />
          ))}
        </View>

        <Field
          label={tr.departments.maintenance.roomNumber}
          value={roomNumber}
          onChangeText={setRoomNumber}
        />
        <Field
          label={tr.departments.maintenance.description}
          value={description}
          onChangeText={setDescription}
          multiline
        />
        <FormActions>
          <Button
            title={tr.app.cancel}
            variant="secondary"
            onPress={() => setCreateOpen(false)}
            fullWidth
          />
          <Button
            title={tr.departments.maintenance.create}
            onPress={onCreate}
            loading={creating}
            fullWidth
          />
        </FormActions>
      </ActionSheet>

      {/* Technician task update sheet — single-tap status actions */}
      <ActionSheet
        visible={activeTask !== null}
        onClose={() => setActiveTask(null)}
        title={
          activeTask
            ? `${issueTypeLabel(activeTask.issue_type)} · ${tr.departments.maintenance.updateTask}`
            : tr.departments.maintenance.updateTask
        }
      >
        <Field
          label={tr.departments.maintenance.notes}
          value={taskNotes}
          onChangeText={setTaskNotes}
          multiline
        />
        <Field
          label={tr.departments.maintenance.timeSpent}
          value={taskTime}
          onChangeText={setTaskTime}
          keyboardType="number-pad"
        />
        <SegmentedActions>
          <ActionButton
            label={tr.departments.maintenance.markStarted}
            icon="play"
            onPress={() => onSubmitTask('started')}
            bg={c.surfaceAlt}
            fg={c.text}
            loading={submitting}
          />
          <ActionButton
            label={tr.departments.maintenance.markNeedsParts}
            icon="alert"
            onPress={() => onSubmitTask('needs_parts')}
            bg={c.surfaceAlt}
            fg={c.text}
            loading={submitting}
          />
          <ActionButton
            label={tr.departments.maintenance.markCompleted}
            icon="checkmark"
            onPress={() => onSubmitTask('completed')}
            bg={c.primary}
            fg={c.primaryText}
            loading={submitting}
          />
        </SegmentedActions>
      </ActionSheet>
    </ScrollView>
  );
}
