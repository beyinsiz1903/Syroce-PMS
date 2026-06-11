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
  listShifts,
  listLeaveRequests,
  listAttendanceRecords,
  type Shift,
  type LeaveRequest,
  type AttendanceRecord,
} from '../../src/api/hr';
import { formatDate } from '../../src/utils/format';

type Tab = 'shifts' | 'leave' | 'attendance';

function statusTone(status?: string):
  | 'default'
  | 'success'
  | 'warning'
  | 'danger'
  | 'info'
  | 'primary' {
  switch (status) {
    case 'approved':
    case 'confirmed':
    case 'completed':
    case 'present':
      return 'success';
    case 'rejected':
    case 'cancelled':
    case 'absent':
      return 'danger';
    case 'pending':
    case 'late':
    case 'early_leave':
      return 'warning';
    case 'dept_approved':
    case 'on_leave':
      return 'info';
    default:
      return 'default';
  }
}

function shiftStatusLabel(status?: string): string {
  const map = tr.departments.hr.shiftStatuses as Record<string, string>;
  return (status && map[status]) || status || '—';
}

function leaveStatusLabel(status?: string): string {
  const map = tr.departments.hr.leaveStatuses as Record<string, string>;
  return (status && map[status]) || status || '—';
}

function attendanceStatusLabel(status?: string): string {
  const map = tr.departments.hr.attendanceStatuses as Record<string, string>;
  return (status && map[status]) || status || '—';
}

// Trim an ISO timestamp down to HH:MM for compact clock displays.
function clockTime(value?: string | null): string {
  if (!value) return '—';
  const t = value.includes('T') ? value.split('T')[1] : value;
  return t ? t.slice(0, 5) : '—';
}

// Read-only HR screen. Three tabs: shifts (vardiyalar), leave requests
// (izinler) and attendance (devam). Backend GET reads only require auth; the
// (departments) HR entitlement decides whether we show the screen. Leave /
// shift-swap decisions flow through the unified approvals backbone; writes stay
// backend-gated by require_op("manage_hr").
export default function HrScreen() {
  const c = useTheme();
  const hrAccess = useAuthStore((s) => s.hrAccess);
  const [tab, setTab] = useState<Tab>('shifts');

  const shiftsQ = useQuery({
    queryKey: ['hr-shifts'],
    queryFn: () => listShifts(),
    enabled: hrAccess && tab === 'shifts',
  });
  const leaveQ = useQuery({
    queryKey: ['hr-leave'],
    queryFn: () => listLeaveRequests(),
    enabled: hrAccess && tab === 'leave',
  });
  const attendanceQ = useQuery({
    queryKey: ['hr-attendance'],
    queryFn: () => listAttendanceRecords(),
    enabled: hrAccess && tab === 'attendance',
  });

  if (!hrAccess) return <Redirect href={ROUTES.departments} />;

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

  const renderShift = (s: Shift) => (
    <Card key={s.id} style={{ marginBottom: spacing.sm }}>
      <View
        style={{
          flexDirection: 'row',
          justifyContent: 'space-between',
          alignItems: 'flex-start',
        }}
      >
        <View style={{ flex: 1, paddingRight: spacing.sm }}>
          <Body style={{ fontWeight: '600' }}>{s.staff_name || '—'}</Body>
          {s.shift_date ? (
            <Muted>
              {tr.departments.hr.shiftDate}: {formatDate(s.shift_date)}
            </Muted>
          ) : null}
        </View>
        <Badge label={shiftStatusLabel(s.status)} tone={statusTone(s.status)} />
      </View>
      <View style={{ marginTop: spacing.sm, gap: 2 }}>
        {s.start_time || s.end_time ? (
          <Muted>
            {tr.departments.hr.time}: {s.start_time || '—'} – {s.end_time || '—'}
            {s.crosses_midnight ? ` (${tr.departments.hr.overnight})` : ''}
          </Muted>
        ) : null}
      </View>
    </Card>
  );

  const renderLeave = (l: LeaveRequest) => (
    <Card key={l.id} style={{ marginBottom: spacing.sm }}>
      <View
        style={{
          flexDirection: 'row',
          justifyContent: 'space-between',
          alignItems: 'flex-start',
        }}
      >
        <View style={{ flex: 1, paddingRight: spacing.sm }}>
          <Body style={{ fontWeight: '600' }}>{l.staff_name || '—'}</Body>
          {l.leave_type ? (
            <Muted>
              {tr.departments.hr.leaveType}: {l.leave_type}
            </Muted>
          ) : null}
        </View>
        <Badge label={leaveStatusLabel(l.status)} tone={statusTone(l.status)} />
      </View>
      {l.start_date ? (
        <Muted style={{ marginTop: spacing.sm }}>
          {tr.departments.hr.dates}: {formatDate(l.start_date)}
          {l.end_date && l.end_date !== l.start_date ? ` – ${formatDate(l.end_date)}` : ''}
        </Muted>
      ) : null}
    </Card>
  );

  const renderAttendance = (a: AttendanceRecord) => (
    <Card key={a.id} style={{ marginBottom: spacing.sm }}>
      <View
        style={{
          flexDirection: 'row',
          justifyContent: 'space-between',
          alignItems: 'flex-start',
        }}
      >
        <View style={{ flex: 1, paddingRight: spacing.sm }}>
          <Body style={{ fontWeight: '600' }}>{a.staff_name || '—'}</Body>
          {a.department ? (
            <Muted>
              {tr.departments.hr.department}: {a.department}
            </Muted>
          ) : null}
        </View>
        <Badge label={attendanceStatusLabel(a.status)} tone={statusTone(a.status)} />
      </View>
      <View style={{ marginTop: spacing.sm, gap: 2 }}>
        {a.date ? <Muted>{formatDate(a.date)}</Muted> : null}
        <Muted>
          {tr.departments.hr.clockIn}: {clockTime(a.clock_in)} · {tr.departments.hr.clockOut}:{' '}
          {clockTime(a.clock_out)}
        </Muted>
      </View>
    </Card>
  );

  return (
    <ScrollView
      style={{ flex: 1, backgroundColor: c.bg }}
      contentContainerStyle={{ padding: spacing.lg, paddingBottom: spacing.xl }}
    >
      <H1>{tr.departments.hr.title}</H1>

      <View style={{ flexDirection: 'row', gap: spacing.sm, marginTop: spacing.md }}>
        <TabButton value="shifts" label={tr.departments.hr.tabShifts} />
        <TabButton value="leave" label={tr.departments.hr.tabLeave} />
        <TabButton value="attendance" label={tr.departments.hr.tabAttendance} />
      </View>

      {tab === 'shifts' ? (
        <>
          <SectionTitle title={tr.departments.hr.shifts} />
          {(() => {
            const state = (
              <DepartmentListState
                loading={shiftsQ.isLoading}
                error={shiftsQ.error}
                isEmpty={(shiftsQ.data || []).length === 0}
                emptyText={tr.departments.hr.noShifts}
              />
            );
            return state ?? <View>{(shiftsQ.data || []).map(renderShift)}</View>;
          })()}
        </>
      ) : null}

      {tab === 'leave' ? (
        <>
          <SectionTitle title={tr.departments.hr.leave} />
          {(() => {
            const state = (
              <DepartmentListState
                loading={leaveQ.isLoading}
                error={leaveQ.error}
                isEmpty={(leaveQ.data || []).length === 0}
                emptyText={tr.departments.hr.noLeave}
              />
            );
            return state ?? <View>{(leaveQ.data || []).map(renderLeave)}</View>;
          })()}
        </>
      ) : null}

      {tab === 'attendance' ? (
        <>
          <SectionTitle title={tr.departments.hr.attendance} />
          {(() => {
            const state = (
              <DepartmentListState
                loading={attendanceQ.isLoading}
                error={attendanceQ.error}
                isEmpty={(attendanceQ.data || []).length === 0}
                emptyText={tr.departments.hr.noAttendance}
              />
            );
            return state ?? <View>{(attendanceQ.data || []).map(renderAttendance)}</View>;
          })()}
        </>
      ) : null}
    </ScrollView>
  );
}
