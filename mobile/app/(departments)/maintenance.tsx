import React, { useState } from 'react';
import { Alert, Pressable, ScrollView, View } from 'react-native';
import { Redirect } from 'expo-router';
import { useQuery, useQueryClient } from '@tanstack/react-query';
import { Badge, Body, Button, Card, Field, H1, Muted } from '../../src/components/ui';
import {
  DepartmentListState,
  SectionTitle,
} from '../../src/components/department';
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
  type MaintenanceTask,
  type WorkOrder,
} from '../../src/api/maintenance';
import { formatDate } from '../../src/utils/format';
import { errorMessage } from '../../src/utils/errors';

const ISSUE_TYPES = [
  'plumbing',
  'hvac',
  'electrical',
  'furniture',
  'housekeeping_damage',
  'other',
] as const;
const PRIORITIES = ['low', 'normal', 'high', 'urgent'] as const;
const STATUS_FILTERS = ['open', 'in_progress', 'completed'] as const;

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

function priorityTone(p?: string): 'default' | 'warning' | 'danger' | 'info' {
  switch (p) {
    case 'urgent':
      return 'danger';
    case 'high':
      return 'warning';
    case 'low':
      return 'info';
    default:
      return 'default';
  }
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

// Maintenance department screen: work-order list (status filter) + create form +
// mobile technician task submission. The create + submit actions are gated by the
// backend require_module("housekeeping"); the mobile `maintenanceAccess`
// entitlement mirrors that role set. Cosmetic only — the backend still enforces.
export default function MaintenanceScreen() {
  const c = useTheme();
  const qc = useQueryClient();
  const maintenanceAccess = useAuthStore((s) => s.maintenanceAccess);

  const [statusFilter, setStatusFilter] = useState<string>('');

  // Create-work-order form state.
  const [issueType, setIssueType] = useState<string>('');
  const [priority, setPriority] = useState<string>('normal');
  const [roomNumber, setRoomNumber] = useState('');
  const [description, setDescription] = useState('');
  const [creating, setCreating] = useState(false);
  const [createError, setCreateError] = useState<string | null>(null);

  // Per-task technician-submit state.
  const [activeTaskId, setActiveTaskId] = useState<string | null>(null);
  const [taskNotes, setTaskNotes] = useState('');
  const [taskTime, setTaskTime] = useState('');
  const [submitting, setSubmitting] = useState(false);

  const workOrdersQ = useQuery({
    queryKey: ['maint-work-orders', statusFilter],
    queryFn: () => listWorkOrders(statusFilter ? { status: statusFilter } : undefined),
    enabled: maintenanceAccess,
  });
  const tasksQ = useQuery({
    queryKey: ['maint-tasks'],
    queryFn: listMaintenanceTasks,
    enabled: maintenanceAccess,
  });

  // Hard guard — a user without maintenance entitlement is sent to the hub.
  if (!maintenanceAccess) return <Redirect href={ROUTES.departments} />;

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
      setIssueType('');
      setPriority('normal');
      setRoomNumber('');
      setDescription('');
      qc.invalidateQueries({ queryKey: ['maint-work-orders'] });
      Alert.alert(tr.app.success, tr.departments.maintenance.created);
    } catch (e: unknown) {
      setCreateError(errorMessage(e, tr.errors.generic));
      haptic.error();
    } finally {
      setCreating(false);
    }
  };

  const onSubmitTask = async (
    taskId: string,
    status: 'started' | 'completed' | 'needs_parts',
  ) => {
    setSubmitting(true);
    try {
      await submitTechnicianTask({
        task_id: taskId,
        status,
        notes: taskNotes || undefined,
        time_spent_minutes: taskTime ? parseInt(taskTime, 10) || undefined : undefined,
      });
      haptic.success();
      setActiveTaskId(null);
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

  const Chip: React.FC<{ active: boolean; label: string; onPress: () => void }> = ({
    active,
    label,
    onPress,
  }) => (
    <Pressable
      onPress={onPress}
      accessibilityRole="button"
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

  const renderWorkOrder = (w: WorkOrder) => (
    <Card key={w.id} style={{ marginBottom: spacing.sm }}>
      <View
        style={{
          flexDirection: 'row',
          justifyContent: 'space-between',
          alignItems: 'flex-start',
        }}
      >
        <View style={{ flex: 1, paddingRight: spacing.sm }}>
          <Body style={{ fontWeight: '600' }}>{issueTypeLabel(w.issue_type)}</Body>
          {w.description ? <Muted>{w.description}</Muted> : null}
        </View>
        <Badge label={statusLabel(w.status)} tone={statusTone(w.status)} />
      </View>
      <View
        style={{
          marginTop: spacing.sm,
          flexDirection: 'row',
          gap: spacing.sm,
          alignItems: 'center',
          flexWrap: 'wrap',
        }}
      >
        <Badge label={priorityLabel(w.priority)} tone={priorityTone(w.priority)} />
        {w.room_number ? (
          <Muted>
            {tr.departments.maintenance.room}: {w.room_number}
          </Muted>
        ) : null}
        {w.created_at ? <Muted>{formatDate(w.created_at)}</Muted> : null}
      </View>
    </Card>
  );

  const renderTask = (t: MaintenanceTask) => {
    const open = activeTaskId === t.id;
    return (
      <Card key={t.id} style={{ marginBottom: spacing.sm }}>
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

        {open ? (
          <View style={{ marginTop: spacing.md, gap: spacing.sm }}>
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
            <View style={{ flexDirection: 'row', gap: spacing.sm, flexWrap: 'wrap' }}>
              <Button
                title={tr.departments.maintenance.markStarted}
                variant="secondary"
                onPress={() => onSubmitTask(t.id, 'started')}
                loading={submitting}
              />
              <Button
                title={tr.departments.maintenance.markNeedsParts}
                variant="secondary"
                onPress={() => onSubmitTask(t.id, 'needs_parts')}
                loading={submitting}
              />
              <Button
                title={tr.departments.maintenance.markCompleted}
                onPress={() => onSubmitTask(t.id, 'completed')}
                loading={submitting}
              />
            </View>
          </View>
        ) : (
          <View style={{ marginTop: spacing.sm }}>
            <Button
              title={tr.departments.maintenance.submitUpdate}
              variant="secondary"
              onPress={() => {
                setActiveTaskId(t.id);
                setTaskNotes('');
                setTaskTime('');
              }}
            />
          </View>
        )}
      </Card>
    );
  };

  return (
    <ScrollView
      style={{ flex: 1, backgroundColor: c.bg }}
      contentContainerStyle={{ padding: spacing.lg, paddingBottom: spacing.xl }}
    >
      <H1>{tr.departments.maintenance.title}</H1>

      {/* Create work order */}
      <SectionTitle title={tr.departments.maintenance.newWorkOrder} />
      <Card>
        {createError ? (
          <Body style={{ color: c.danger, marginBottom: spacing.sm }}>{createError}</Body>
        ) : null}
        <Muted>{tr.departments.maintenance.issueType}</Muted>
        <View
          style={{
            flexDirection: 'row',
            flexWrap: 'wrap',
            gap: spacing.sm,
            marginTop: spacing.sm,
            marginBottom: spacing.md,
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
            marginTop: spacing.sm,
            marginBottom: spacing.md,
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
        <View style={{ height: spacing.sm }} />
        <Field
          label={tr.departments.maintenance.description}
          value={description}
          onChangeText={setDescription}
          multiline
        />
        <View style={{ height: spacing.md }} />
        <Button
          title={tr.departments.maintenance.create}
          onPress={onCreate}
          loading={creating}
          fullWidth
        />
      </Card>

      {/* Work orders list with status filter */}
      <SectionTitle title={tr.departments.maintenance.workOrders} />
      <View
        style={{
          flexDirection: 'row',
          flexWrap: 'wrap',
          gap: spacing.sm,
          marginBottom: spacing.md,
        }}
      >
        <Chip
          active={statusFilter === ''}
          label={tr.departments.maintenance.filterAll}
          onPress={() => setStatusFilter('')}
        />
        {STATUS_FILTERS.map((s) => (
          <Chip
            key={s}
            active={statusFilter === s}
            label={statusLabel(s)}
            onPress={() => setStatusFilter(s)}
          />
        ))}
      </View>
      {(() => {
        const state = (
          <DepartmentListState
            loading={workOrdersQ.isLoading}
            error={workOrdersQ.error}
            isEmpty={(workOrdersQ.data || []).length === 0}
            emptyText={tr.departments.maintenance.noWorkOrders}
          />
        );
        return state ?? <View>{(workOrdersQ.data || []).map(renderWorkOrder)}</View>;
      })()}

      {/* Technician tasks */}
      <SectionTitle title={tr.departments.maintenance.tasks} />
      {(() => {
        const state = (
          <DepartmentListState
            loading={tasksQ.isLoading}
            error={tasksQ.error}
            isEmpty={(tasksQ.data || []).length === 0}
            emptyText={tr.departments.maintenance.noTasks}
          />
        );
        return state ?? <View>{(tasksQ.data || []).map(renderTask)}</View>;
      })()}
    </ScrollView>
  );
}
