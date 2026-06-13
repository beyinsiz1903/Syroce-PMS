import React, { useMemo, useState } from 'react';
import { Pressable, ScrollView, View } from 'react-native';
import { Ionicons } from '@expo/vector-icons';
import { Redirect } from 'expo-router';
import {
  useMutation,
  useQuery,
  useQueryClient,
  type UseQueryResult,
} from '@tanstack/react-query';
import {
  ActionButton,
  Badge,
  Body,
  Card,
  EmptyState,
  Field,
  H1,
  ListGroup,
  ListRow,
  Muted,
  SegmentedActions,
  webCenter,
} from '../../src/components/ui';
import { KpiCard, KpiRow } from '../../src/components/KpiCard';
import { FilterChips } from '../../src/components/FilterChips';
import {
  DepartmentListState,
  SectionTitle,
} from '../../src/components/department';
import { spacing, radius, useTheme } from '../../src/theme';
import { tr } from '../../src/i18n/tr';
import { useAuthStore } from '../../src/state/authStore';
import { ROUTES } from '../../src/navigation/routes';
import { screenRedirectsToHub } from '../../src/utils/departmentScreens';
import { haptic } from '../../src/hooks/useHaptic';
import { errorMessage } from '../../src/utils/errors';
import {
  listShifts,
  listLeaveRequests,
  listAttendanceRecords,
  listStaff,
  listAnnouncements,
  markAnnouncementRead,
  markAllAnnouncementsRead,
  getPerformanceSummary,
  decideLeaveRequest,
  type Shift,
  type LeaveRequest,
  type AttendanceRecord,
  type Announcement,
  type AnnouncementList,
  type PerformanceReview,
  type PerformanceSummary,
  type LeaveDecisionAction,
} from '../../src/api/hr';
import { formatDate } from '../../src/utils/format';

type IoniconName = keyof typeof Ionicons.glyphMap;

type Tab = 'staff' | 'shifts' | 'leave' | 'attendance' | 'performance' | 'announcements';

// Cosmetic mirror of the backend require_op("manage_hr") gate (the SAME gate
// that protects the leave-request decision + performance endpoints). View-only
// HR roles such as `finance` (which hold view_hr but NOT manage_hr) must not
// see the performance cockpit or the leave approve/reject controls. This is a
// navigation/affordance gate only — the backend still enforces every write, so
// nothing here weakens RBAC. Derived from the RAW role because normalizeRole
// collapses several roles (e.g. super_admin → gm) and would lose the distinction.
const MANAGE_HR_ROLES = [
  'super_admin',
  'admin',
  'supervisor',
  'hr',
  'hr_manager',
];

function canManageHr(rawRole: string | undefined): boolean {
  if (!rawRole) return false;
  return MANAGE_HR_ROLES.includes(rawRole.toLowerCase());
}

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

function employmentLabel(value?: string | null): string {
  if (!value) return '';
  const map = tr.departments.hr.employmentTypes;
  return map[value] || value;
}

// Map a semantic tone to its theme colour (for Card accent bars).
function toneColor(
  c: ReturnType<typeof useTheme>,
  tone: 'default' | 'success' | 'warning' | 'danger' | 'info' | 'primary',
): string {
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
      return c.border;
  }
}

function priorityLabel(value?: string | null): string {
  if (!value) return '';
  const map = tr.departments.hr.priorities;
  return map[value.toLowerCase()] || value;
}

function priorityTone(value?: string):
  | 'default'
  | 'success'
  | 'warning'
  | 'danger'
  | 'info'
  | 'primary' {
  switch ((value || '').toLowerCase()) {
    case 'critical':
    case 'urgent':
    case 'high':
      return 'danger';
    case 'medium':
    case 'normal':
      return 'warning';
    case 'low':
      return 'info';
    default:
      return 'default';
  }
}

// Read-only HR screen with manager actions. Four tabs: shifts (vardiyalar),
// leave requests (izinler), attendance (devam) and — for manage_hr roles —
// performance (performans, kokpit). Backend GET reads only require auth; the
// (departments) HR entitlement decides whether we show the screen. Leave
// decisions flow through the 2-stage state machine and stay backend-gated by
// require_op("manage_hr").
export default function HrScreen() {
  const c = useTheme();
  const rawRole = useAuthStore((s) => s.user?.role);
  const hrAccess = !screenRedirectsToHub('hr', rawRole);
  const manageHr = canManageHr(rawRole);
  const [tab, setTab] = useState<Tab>('staff');

  const announcementsQ = useQuery({
    queryKey: ['hr-announcements'],
    queryFn: () => listAnnouncements(),
    enabled: hrAccess && tab === 'announcements',
  });
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
  const performanceQ = useQuery({
    queryKey: ['hr-performance'],
    queryFn: () => getPerformanceSummary(),
    enabled: hrAccess && manageHr && tab === 'performance',
  });

  if (screenRedirectsToHub('hr', rawRole)) {
    return <Redirect href={ROUTES.departments} />;
  }

  const tabs: { value: Tab; label: string; icon: IoniconName }[] = [
    { value: 'staff', label: tr.departments.hr.tabStaff, icon: 'people-outline' },
    { value: 'shifts', label: tr.departments.hr.tabShifts, icon: 'time-outline' },
    { value: 'leave', label: tr.departments.hr.tabLeave, icon: 'airplane-outline' },
    { value: 'attendance', label: tr.departments.hr.tabAttendance, icon: 'log-in-outline' },
    ...(manageHr
      ? [{ value: 'performance' as Tab, label: tr.departments.hr.tabPerformance, icon: 'ribbon-outline' as IoniconName }]
      : []),
    { value: 'announcements', label: tr.departments.hr.tabAnnouncements, icon: 'megaphone-outline' },
  ];

  const TabButton: React.FC<{ value: Tab; label: string; icon: IoniconName }> = ({
    value,
    label,
    icon,
  }) => {
    const active = tab === value;
    return (
      <Pressable
        onPress={() => {
          haptic.tap();
          setTab(value);
        }}
        accessibilityRole="button"
        accessibilityState={{ selected: active }}
        style={{
          flexDirection: 'row',
          alignItems: 'center',
          gap: 6,
          paddingVertical: spacing.sm,
          paddingHorizontal: spacing.md,
          borderRadius: radius.pill,
          backgroundColor: active ? c.primary : c.surfaceAlt,
          borderWidth: 1,
          borderColor: active ? c.primary : c.border,
        }}
      >
        <Ionicons name={icon} size={15} color={active ? c.primaryText : c.textMuted} />
        <Body
          style={{ color: active ? c.primaryText : c.text, fontWeight: '600', fontSize: 13 }}
          numberOfLines={1}
        >
          {label}
        </Body>
      </Pressable>
    );
  };

  const renderShift = (s: Shift) => {
    const tone = statusTone(s.status);
    return (
      <Card key={s.id} style={{ marginBottom: spacing.sm }} accent={toneColor(c, tone)}>
        <View
          style={{
            flexDirection: 'row',
            justifyContent: 'space-between',
            alignItems: 'flex-start',
          }}
        >
          <View style={{ flex: 1, paddingRight: spacing.sm }}>
            <Body style={{ fontWeight: '700', fontSize: 16 }}>{s.staff_name || '—'}</Body>
            {s.shift_date ? (
              <View style={{ flexDirection: 'row', alignItems: 'center', gap: 4, marginTop: 2 }}>
                <Ionicons name="calendar-outline" size={13} color={c.textMuted} />
                <Muted>{formatDate(s.shift_date)}</Muted>
              </View>
            ) : null}
          </View>
          <Badge label={shiftStatusLabel(s.status)} tone={tone} />
        </View>
        {s.start_time || s.end_time ? (
          <View
            style={{
              flexDirection: 'row',
              alignItems: 'center',
              gap: 6,
              marginTop: spacing.md,
            }}
          >
            <Ionicons name="time-outline" size={15} color={c.primary} />
            <Body style={{ fontWeight: '600' }}>
              {s.start_time || '—'} – {s.end_time || '—'}
            </Body>
            {s.crosses_midnight ? (
              <Badge label={tr.departments.hr.overnight} tone="info" icon="moon-outline" />
            ) : null}
          </View>
        ) : null}
      </Card>
    );
  };

  const renderAttendance = (a: AttendanceRecord) => {
    const tone = statusTone(a.status);
    return (
      <Card key={a.id} style={{ marginBottom: spacing.sm }} accent={toneColor(c, tone)}>
        <View
          style={{
            flexDirection: 'row',
            justifyContent: 'space-between',
            alignItems: 'flex-start',
          }}
        >
          <View style={{ flex: 1, paddingRight: spacing.sm }}>
            <Body style={{ fontWeight: '700', fontSize: 16 }}>{a.staff_name || '—'}</Body>
            {a.department ? <Muted style={{ marginTop: 2 }}>{a.department}</Muted> : null}
          </View>
          <Badge label={attendanceStatusLabel(a.status)} tone={tone} />
        </View>
        {a.date ? <Muted style={{ marginTop: spacing.sm }}>{formatDate(a.date)}</Muted> : null}
        <View style={{ flexDirection: 'row', gap: spacing.lg, marginTop: spacing.sm }}>
          <View style={{ flexDirection: 'row', alignItems: 'center', gap: 4 }}>
            <Ionicons name="log-in-outline" size={14} color={c.success} />
            <Muted>
              {tr.departments.hr.clockIn}: {clockTime(a.clock_in)}
            </Muted>
          </View>
          <View style={{ flexDirection: 'row', alignItems: 'center', gap: 4 }}>
            <Ionicons name="log-out-outline" size={14} color={c.danger} />
            <Muted>
              {tr.departments.hr.clockOut}: {clockTime(a.clock_out)}
            </Muted>
          </View>
        </View>
      </Card>
    );
  };

  return (
    <ScrollView
      style={{ flex: 1, backgroundColor: c.bg }}
      contentContainerStyle={[{ padding: spacing.lg, paddingBottom: spacing.xl }, webCenter]}
    >
      <H1>{tr.departments.hr.title}</H1>
      <Muted style={{ marginTop: 2 }}>{tr.departments.hr.subtitle}</Muted>

      <ScrollView
        horizontal
        showsHorizontalScrollIndicator={false}
        style={{ marginTop: spacing.md, marginHorizontal: -spacing.lg }}
        contentContainerStyle={{
          flexDirection: 'row',
          gap: spacing.sm,
          paddingHorizontal: spacing.lg,
        }}
      >
        {tabs.map(({ value, label, icon }) => (
          <TabButton key={value} value={value} label={label} icon={icon} />
        ))}
      </ScrollView>

      {tab === 'staff' ? <StaffPanel enabled={hrAccess} /> : null}

      {tab === 'announcements' ? <AnnouncementsPanel query={announcementsQ} /> : null}

      {tab === 'shifts' ? (
        <>
          <SectionTitle title={tr.departments.hr.shifts} />
          {(() => {
            // DepartmentListState is CALLED (not <JSX/>) so it can return null
            // when there is data — a rendered element would always be truthy and
            // the `?? list` fallback would never fire (list would never show).
            const state = DepartmentListState({
              loading: shiftsQ.isLoading,
              error: shiftsQ.error,
              isEmpty: (shiftsQ.data || []).length === 0,
              emptyText: tr.departments.hr.noShifts,
            });
            return state ?? <View>{(shiftsQ.data || []).map(renderShift)}</View>;
          })()}
        </>
      ) : null}

      {tab === 'leave' ? (
        <>
          <SectionTitle title={tr.departments.hr.leave} />
          {(() => {
            const state = DepartmentListState({
              loading: leaveQ.isLoading,
              error: leaveQ.error,
              isEmpty: (leaveQ.data || []).length === 0,
              emptyText: tr.departments.hr.noLeave,
            });
            return (
              state ?? (
                <View>
                  {(leaveQ.data || []).map((l) => (
                    <LeaveRow key={l.id} leave={l} canDecide={manageHr} />
                  ))}
                </View>
              )
            );
          })()}
        </>
      ) : null}

      {tab === 'attendance' ? (
        <>
          <SectionTitle title={tr.departments.hr.attendance} />
          {(() => {
            const state = DepartmentListState({
              loading: attendanceQ.isLoading,
              error: attendanceQ.error,
              isEmpty: (attendanceQ.data || []).length === 0,
              emptyText: tr.departments.hr.noAttendance,
            });
            return state ?? <View>{(attendanceQ.data || []).map(renderAttendance)}</View>;
          })()}
        </>
      ) : null}

      {tab === 'performance' ? <PerformancePanel query={performanceQ} /> : null}
    </ScrollView>
  );
}

// ── Personel dizini ─────────────────────────────────────────────────────────
// KPI özeti (toplam personel + departman sayısı + aktif/pasif) ardından gruplu
// premium personel satırları. Veriler GET /api/hr/staff (PII backend'de maskeli).
// İsme göre arama istemci tarafında; departman filtresi backend'in `department`
// query parametresini kullanır. Departman çipleri + KPI'lar her zaman tam
// dizinden (baseQ) türetilir, böylece filtre seçili olsa da sabit kalır.
function StaffPanel({ enabled }: { enabled: boolean }) {
  const c = useTheme();
  const [search, setSearch] = useState('');
  const [dept, setDept] = useState('');

  // Tam dizin: departman çiplerinin ve KPI özetinin kaynağı (filtreden bağımsız).
  const baseQ = useQuery({
    queryKey: ['hr-staff'],
    queryFn: () => listStaff(),
    enabled,
  });
  // Filtreli liste: yalnızca bir departman seçiliyken backend'e parametre gider.
  const filteredQ = useQuery({
    queryKey: ['hr-staff', dept],
    queryFn: () => listStaff({ department: dept }),
    enabled: enabled && dept !== '',
  });

  const baseStaff = baseQ.data?.staff ?? [];

  const { deptOptions, departments, activeCount, passiveCount } = useMemo(() => {
    const deptSet = new Set<string>();
    let active = 0;
    let passive = 0;
    for (const s of baseStaff) {
      if (s.department) deptSet.add(s.department);
      if (s.active === false) passive += 1;
      else active += 1;
    }
    const sorted = Array.from(deptSet).sort((a, b) => a.localeCompare(b, 'tr'));
    const options = [
      { value: '', label: tr.departments.hr.staffAllDepartments },
      ...sorted.map((d) => ({ value: d, label: d })),
    ];
    return {
      deptOptions: options,
      departments: deptSet.size,
      activeCount: active,
      passiveCount: passive,
    };
  }, [baseStaff]);

  // Görüntülenecek liste: departman seçiliyse filtreli sorgu, değilse tam dizin.
  const sourceStaff = dept === '' ? baseStaff : filteredQ.data?.staff ?? [];
  const q = search.trim().toLowerCase();
  const visibleStaff = q
    ? sourceStaff.filter((s) => (s.name || '').toLowerCase().includes(q))
    : sourceStaff;

  const directoryEmpty = baseStaff.length === 0;
  const listLoading = dept !== '' && filteredQ.isLoading;
  const listError = dept !== '' ? filteredQ.error : null;

  return (
    <>
      <SectionTitle title={tr.departments.hr.staffDirectory} />
      {baseQ.isLoading ? (
        <DepartmentListState loading error={null} isEmpty={false} />
      ) : baseQ.error ? (
        <DepartmentListState loading={false} error={baseQ.error} isEmpty={false} />
      ) : directoryEmpty ? (
        <EmptyState icon="people-outline" title={tr.departments.hr.noStaff} />
      ) : (
        <View style={{ gap: spacing.md }}>
          <KpiRow>
            <KpiCard
              label={tr.departments.hr.staffTotal}
              value={String(baseQ.data?.total ?? baseStaff.length)}
              icon="people"
              tone="info"
            />
            <KpiCard
              label={tr.departments.hr.staffDepartments}
              value={String(departments)}
              icon="business"
              tone="info"
            />
          </KpiRow>
          <KpiRow>
            <KpiCard
              label={tr.departments.hr.staffActive}
              value={String(activeCount)}
              icon="checkmark-circle"
              tone="success"
            />
            <KpiCard
              label={tr.departments.hr.staffPassive}
              value={String(passiveCount)}
              icon="pause-circle"
              tone={passiveCount > 0 ? 'warning' : 'default'}
            />
          </KpiRow>

          <Field
            value={search}
            onChangeText={setSearch}
            placeholder={tr.departments.hr.staffSearchPlaceholder}
            autoCapitalize="none"
            autoCorrect={false}
            returnKeyType="search"
            testID="staff-search"
          />

          {deptOptions.length > 1 ? (
            <FilterChips
              options={deptOptions}
              value={dept}
              onChange={setDept}
              testID="staff-dept-filter"
            />
          ) : null}

          {listLoading ? (
            <DepartmentListState loading error={null} isEmpty={false} />
          ) : listError ? (
            <DepartmentListState loading={false} error={listError} isEmpty={false} />
          ) : visibleStaff.length === 0 ? (
            <EmptyState icon="search-outline" title={tr.departments.hr.noStaffMatch} />
          ) : (
            <ListGroup>
              {visibleStaff.map((s, i) => {
                const sub = [s.position, s.department].filter(Boolean).join(' · ');
                return (
                  <ListRow
                    key={s.id}
                    icon="person-circle-outline"
                    iconColor={s.active === false ? c.textMuted : c.primary}
                    label={s.name || '—'}
                    sublabel={sub || undefined}
                    showChevron={false}
                    last={i === visibleStaff.length - 1}
                    right={
                      s.employment_type ? (
                        <Badge
                          label={employmentLabel(s.employment_type)}
                          tone={s.active === false ? 'default' : 'info'}
                        />
                      ) : undefined
                    }
                  />
                );
              })}
            </ListGroup>
          )}
        </View>
      )}
    </>
  );
}

// ── Duyurular akışı ─────────────────────────────────────────────────────────
// Tenant geneli yayınlanan bildirimler (GET /api/notifications/list). Önceliğe
// göre renkli accent + okunmamışlar için "Yeni" rozeti. Salt-okunur.
function AnnouncementsPanel({ query }: { query: UseQueryResult<AnnouncementList> }) {
  const c = useTheme();
  const qc = useQueryClient();
  const data = query.data;
  const items = data?.items ?? [];
  const empty = items.length === 0;

  // Tap-to-read: optimistically flip the tapped item to read and decrement the
  // unread counter so the "Yeni" badge clears instantly. The backend caches the
  // list per-user for a few seconds, so a plain invalidate could refetch the
  // stale (still-unread) snapshot — the optimistic patch keeps the UI correct
  // until the cache expires; we still invalidate so the server stays the source
  // of truth on the next fetch.
  const markRead = useMutation({
    mutationFn: (id: string) => markAnnouncementRead(id),
    onMutate: async (id: string) => {
      await qc.cancelQueries({ queryKey: ['hr-announcements'] });
      const prev = qc.getQueryData<AnnouncementList>(['hr-announcements']);
      qc.setQueryData<AnnouncementList>(['hr-announcements'], (curr) => {
        if (!curr) return curr;
        let cleared = false;
        const next = curr.items.map((a) => {
          if (a.id === id && a.read === false) {
            cleared = true;
            return { ...a, read: true };
          }
          return a;
        });
        return {
          items: next,
          unreadCount: cleared
            ? Math.max(0, curr.unreadCount - 1)
            : curr.unreadCount,
        };
      });
      return { prev };
    },
    onError: (_err, _id, ctx) => {
      haptic.error();
      if (ctx?.prev) qc.setQueryData(['hr-announcements'], ctx.prev);
    },
    onSettled: () => {
      qc.invalidateQueries({ queryKey: ['hr-announcements'] });
    },
  });

  const onAnnouncementPress = (a: Announcement) => {
    haptic.tap();
    if (a.read === false && !markRead.isPending) {
      markRead.mutate(a.id);
    }
  };

  // Bulk "mark all read": optimistically flip every visible item to read and
  // zero the unread counter so the "Yeni" badges clear at once. Same cache
  // discipline as the per-item path — invalidate on settle so the server stays
  // the source of truth once its own per-user list cache expires.
  const markAllRead = useMutation({
    mutationFn: () => markAllAnnouncementsRead(),
    onMutate: async () => {
      await qc.cancelQueries({ queryKey: ['hr-announcements'] });
      const prev = qc.getQueryData<AnnouncementList>(['hr-announcements']);
      qc.setQueryData<AnnouncementList>(['hr-announcements'], (curr) => {
        if (!curr) return curr;
        return {
          items: curr.items.map((a) =>
            a.read === false ? { ...a, read: true } : a,
          ),
          unreadCount: 0,
        };
      });
      return { prev };
    },
    onError: (_err, _vars, ctx) => {
      haptic.error();
      if (ctx?.prev) qc.setQueryData(['hr-announcements'], ctx.prev);
    },
    onSettled: () => {
      qc.invalidateQueries({ queryKey: ['hr-announcements'] });
    },
  });

  const unreadCount = data?.unreadCount ?? 0;
  const onMarkAllRead = () => {
    if (unreadCount > 0 && !markAllRead.isPending) {
      markAllRead.mutate();
    }
  };

  return (
    <>
      <SectionTitle title={tr.departments.hr.announcements} />
      {query.isLoading ? (
        <DepartmentListState loading error={null} isEmpty={false} />
      ) : query.error ? (
        <DepartmentListState loading={false} error={query.error} isEmpty={false} />
      ) : empty ? (
        <EmptyState icon="megaphone-outline" title={tr.departments.hr.noAnnouncements} />
      ) : (
        <View style={{ gap: spacing.md }}>
          <KpiRow>
            <KpiCard
              label={tr.departments.hr.announcementsTotal}
              value={String(items.length)}
              icon="megaphone"
              tone="info"
            />
            <KpiCard
              label={tr.departments.hr.announcementsUnread}
              value={String(unreadCount)}
              icon="mail-unread"
              tone={unreadCount > 0 ? 'warning' : 'default'}
            />
          </KpiRow>

          {unreadCount > 0 ? (
            <ActionButton
              label={tr.departments.hr.markAllRead}
              icon="checkmark-done"
              onPress={onMarkAllRead}
              bg={c.primary}
              fg={c.primaryText}
              loading={markAllRead.isPending}
              testID="hr-announcements-mark-all-read"
            />
          ) : null}

          <View>
            {items.map((a) => {
              const tone = priorityTone(a.priority);
              const unread = a.read === false;
              return (
                <Pressable
                  key={a.id}
                  onPress={unread ? () => onAnnouncementPress(a) : undefined}
                  disabled={!unread}
                  accessibilityRole={unread ? 'button' : undefined}
                  accessibilityState={unread ? { selected: false } : undefined}
                  accessibilityHint={
                    unread ? tr.departments.hr.markReadHint : undefined
                  }
                  style={({ pressed }) => ({
                    opacity: pressed && unread ? 0.7 : 1,
                  })}
                >
                  <Card
                    style={{ marginBottom: spacing.sm }}
                    accent={toneColor(c, tone)}
                  >
                    <View
                      style={{
                        flexDirection: 'row',
                        justifyContent: 'space-between',
                        alignItems: 'flex-start',
                        gap: spacing.sm,
                      }}
                    >
                      <View style={{ flex: 1 }}>
                        <Body style={{ fontWeight: '700', fontSize: 16 }}>
                          {a.title || '—'}
                        </Body>
                        {a.message ? (
                          <Muted style={{ marginTop: 4 }}>{a.message}</Muted>
                        ) : null}
                      </View>
                      {unread ? (
                        <Badge label={tr.departments.hr.newBadge} tone="primary" />
                      ) : null}
                    </View>
                    <View
                      style={{
                        flexDirection: 'row',
                        alignItems: 'center',
                        justifyContent: 'space-between',
                        marginTop: spacing.md,
                      }}
                    >
                      {a.created_at ? (
                        <View style={{ flexDirection: 'row', alignItems: 'center', gap: 4 }}>
                          <Ionicons name="time-outline" size={13} color={c.textMuted} />
                          <Muted>{formatDate(a.created_at)}</Muted>
                        </View>
                      ) : (
                        <View />
                      )}
                      {a.priority ? (
                        <Badge label={priorityLabel(a.priority)} tone={tone} />
                      ) : null}
                    </View>
                  </Card>
                </Pressable>
              );
            })}
          </View>
        </View>
      )}
    </>
  );
}

// ── Performans kokpiti ──────────────────────────────────────────────────────
// Üst-üste: dört KPI hero kartı (toplam / ortalama puan / yüksek / gelişim) +
// son değerlendirmelerin listesi. Puanlar 0-10 ölçeğinde (backend: ge=0 le=10).
function PerformancePanel({
  query,
}: {
  query: UseQueryResult<PerformanceSummary>;
}) {
  const data = query.data;
  const items = data?.items ?? [];

  const { high, needsWork } = useMemo(() => {
    let h = 0;
    let n = 0;
    for (const r of items) {
      const score = typeof r.overall_score === 'number' ? r.overall_score : null;
      if (score === null) continue;
      if (score >= 8) h += 1;
      else if (score < 5) n += 1;
    }
    return { high: h, needsWork: n };
  }, [items]);

  const empty = items.length === 0;

  return (
    <>
      <SectionTitle title={tr.departments.hr.performance} />
      {query.isLoading ? (
        <DepartmentListState loading error={null} isEmpty={false} />
      ) : query.error ? (
        <DepartmentListState loading={false} error={query.error} isEmpty={false} />
      ) : empty ? (
        <EmptyState
          icon="ribbon-outline"
          title={tr.departments.hr.noPerformance}
          testID="hr-performance-empty"
        />
      ) : (
        <View style={{ gap: spacing.md }}>
          <KpiRow>
            <KpiCard
              label={tr.departments.hr.perfTotal}
              value={String(data?.total ?? items.length)}
              icon="document-text"
              tone="info"
              testID="hr-kpi-total"
            />
            <KpiCard
              label={tr.departments.hr.perfAvgScore}
              value={`${(data?.avg_score ?? 0).toFixed(1)} / 10`}
              icon="star"
              tone="info"
              testID="hr-kpi-avg"
            />
          </KpiRow>
          <KpiRow>
            <KpiCard
              label={tr.departments.hr.perfHigh}
              value={String(high)}
              icon="trophy"
              tone="success"
              testID="hr-kpi-high"
            />
            <KpiCard
              label={tr.departments.hr.perfNeedsWork}
              value={String(needsWork)}
              icon="trending-down"
              tone={needsWork > 0 ? 'warning' : 'default'}
              testID="hr-kpi-needswork"
            />
          </KpiRow>

          <SectionTitle title={tr.departments.hr.perfRecent} />
          <View>
            {items.map((r) => (
              <PerformanceCard key={r.id} review={r} />
            ))}
          </View>
        </View>
      )}
    </>
  );
}

function PerformanceCard({ review }: { review: PerformanceReview }) {
  const score = typeof review.overall_score === 'number' ? review.overall_score : null;
  const tone =
    score === null ? 'default' : score >= 8 ? 'success' : score < 5 ? 'danger' : 'warning';
  return (
    <Card style={{ marginBottom: spacing.sm }}>
      <View
        style={{
          flexDirection: 'row',
          justifyContent: 'space-between',
          alignItems: 'flex-start',
        }}
      >
        <View style={{ flex: 1, paddingRight: spacing.sm }}>
          <Body style={{ fontWeight: '600' }}>{review.staff_name || '—'}</Body>
          {review.period ? (
            <Muted>
              {tr.departments.hr.perfPeriod}: {review.period}
            </Muted>
          ) : null}
        </View>
        {score !== null ? (
          <Badge label={`${tr.departments.hr.perfScore}: ${score} / 10`} tone={tone} />
        ) : null}
      </View>
      <View style={{ marginTop: spacing.sm, gap: 2 }}>
        {review.reviewer_name ? (
          <Muted>
            {tr.departments.hr.perfReviewer}: {review.reviewer_name}
          </Muted>
        ) : null}
        {review.strengths ? (
          <Muted>
            {tr.departments.hr.perfStrengths}: {review.strengths}
          </Muted>
        ) : null}
        {review.improvement_areas ? (
          <Muted>
            {tr.departments.hr.perfImprovement}: {review.improvement_areas}
          </Muted>
        ) : null}
        {review.reviewed_at ? <Muted>{formatDate(review.reviewed_at)}</Muted> : null}
      </View>
    </Card>
  );
}

// ── İzin satırı + 2-aşamalı onay/red aksiyonları ────────────────────────────
// Standart aksiyon deseni (ActionButton + SegmentedActions) — Onayla/Reddet
// aksiyonu Alert.alert DEĞİL inline iki-adım onaydır (Expo Web'de Alert no-op).
// Backend state machine: pending → dept_approve → dept_approved → approve →
// approved; pending|dept_approved → reject (gerekçe ZORUNLU). Tüm kararlar
// backend tarafında require_op("manage_hr") ile yeniden zorlanır.
function LeaveRow({ leave, canDecide }: { leave: LeaveRequest; canDecide: boolean }) {
  const c = useTheme();
  const qc = useQueryClient();
  const [rejecting, setRejecting] = useState(false);
  const [confirming, setConfirming] = useState(false);
  const [reason, setReason] = useState('');
  const [reasonError, setReasonError] = useState(false);

  const status = leave.status || 'pending';
  const isPending = status === 'pending';
  const isDeptApproved = status === 'dept_approved';
  const actionable = canDecide && (isPending || isDeptApproved);

  // pending → dept_approve (departman onayı); dept_approved → approve (final).
  const approveAction: LeaveDecisionAction = isDeptApproved ? 'approve' : 'dept_approve';
  const approveLabel = isDeptApproved
    ? tr.departments.hr.approve
    : tr.departments.hr.deptApprove;

  const mutation = useMutation({
    mutationFn: (vars: { action: LeaveDecisionAction; note?: string }) =>
      decideLeaveRequest(leave.id, vars.action, vars.note),
    onSuccess: () => {
      haptic.success();
      setRejecting(false);
      setConfirming(false);
      setReason('');
      setReasonError(false);
      qc.invalidateQueries({ queryKey: ['hr-leave'] });
    },
    onError: () => {
      haptic.error();
    },
  });

  const onApprovePress = () => {
    haptic.tap();
    if (mutation.isError) mutation.reset();
    setRejecting(false);
    setConfirming((v) => !v);
  };

  const onApproveConfirm = () => {
    mutation.mutate({ action: approveAction });
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
    mutation.mutate({ action: 'reject', note: trimmed });
  };

  return (
    <Card style={{ marginBottom: spacing.sm }}>
      <View
        style={{
          flexDirection: 'row',
          justifyContent: 'space-between',
          alignItems: 'flex-start',
        }}
      >
        <View style={{ flex: 1, paddingRight: spacing.sm }}>
          <Body style={{ fontWeight: '600' }}>{leave.staff_name || '—'}</Body>
          {leave.leave_type ? (
            <Muted>
              {tr.departments.hr.leaveType}: {leave.leave_type}
            </Muted>
          ) : null}
        </View>
        <Badge label={leaveStatusLabel(status)} tone={statusTone(status)} />
      </View>
      {leave.start_date ? (
        <Muted style={{ marginTop: spacing.sm }}>
          {tr.departments.hr.dates}: {formatDate(leave.start_date)}
          {leave.end_date && leave.end_date !== leave.start_date
            ? ` – ${formatDate(leave.end_date)}`
            : ''}
        </Muted>
      ) : null}
      {isDeptApproved ? (
        <View style={{ marginTop: spacing.xs }}>
          <Badge label={tr.departments.hr.deptApprovedBadge} tone="info" />
        </View>
      ) : null}

      {mutation.isError ? (
        <Muted style={{ marginTop: spacing.xs, color: c.danger }}>
          {errorMessage(mutation.error, tr.departments.hr.decisionError)}
        </Muted>
      ) : null}

      {actionable ? (
        rejecting ? (
          <View style={{ marginTop: spacing.sm, gap: spacing.sm }}>
            <Field
              label={tr.departments.hr.rejectReasonLabel}
              placeholder={tr.departments.hr.rejectReasonPlaceholder}
              value={reason}
              onChangeText={(t) => {
                setReason(t);
                if (reasonError) setReasonError(false);
              }}
              multiline
              editable={!mutation.isPending}
            />
            {reasonError ? (
              <Muted style={{ color: c.danger }}>
                {tr.departments.hr.rejectReasonRequired}
              </Muted>
            ) : null}
            <SegmentedActions>
              <ActionButton
                label={tr.departments.hr.cancel}
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
              <ActionButton
                testID="hr-leave-reject-confirm"
                label={tr.departments.hr.reject}
                icon="close-circle"
                onPress={onRejectConfirm}
                bg={c.danger}
                fg="#ffffff"
                loading={mutation.isPending}
              />
            </SegmentedActions>
          </View>
        ) : confirming ? (
          <View style={{ marginTop: spacing.sm, gap: spacing.sm }}>
            <Muted>{tr.departments.hr.approveConfirm}</Muted>
            <SegmentedActions>
              <ActionButton
                label={tr.departments.hr.cancel}
                icon="arrow-undo"
                onPress={() => setConfirming(false)}
                bg={c.surfaceAlt}
                fg={c.text}
                disabled={mutation.isPending}
              />
              <ActionButton
                testID="hr-leave-approve-confirm"
                label={approveLabel}
                icon="checkmark-circle"
                onPress={onApproveConfirm}
                bg={c.success}
                fg="#ffffff"
                loading={mutation.isPending}
              />
            </SegmentedActions>
          </View>
        ) : (
          <View style={{ marginTop: spacing.sm }}>
            <SegmentedActions>
              <ActionButton
                testID="hr-leave-reject"
                label={tr.departments.hr.reject}
                icon="close-circle"
                onPress={onRejectPress}
                bg={c.danger + '14'}
                fg={c.danger}
                disabled={mutation.isPending}
              />
              <ActionButton
                testID="hr-leave-approve"
                label={approveLabel}
                icon="checkmark-circle"
                onPress={onApprovePress}
                bg={c.success}
                fg="#ffffff"
                disabled={mutation.isPending}
              />
            </SegmentedActions>
          </View>
        )
      ) : null}
    </Card>
  );
}
