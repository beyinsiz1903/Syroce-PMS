import React, { useMemo, useState } from 'react';
import { Alert, Pressable, ScrollView, Text, View } from 'react-native';
import { Ionicons } from '@expo/vector-icons';
import { Redirect } from 'expo-router';
import { useMutation, useQuery, useQueryClient } from '@tanstack/react-query';
import {
  ActionButton,
  ActionSheet,
  Badge,
  Body,
  Button,
  Card,
  EmptyState,
  Field,
  FormActions,
  H1,
  ListGroup,
  ListRow,
  Muted,
  SectionTitle,
  SegmentedActions,
  SkeletonCard,
  webCenter,
} from '../../src/components/ui';
import { DatePicker } from '../../src/components/DatePicker';
import { spacing, radius, useTheme } from '../../src/theme';
import { tr } from '../../src/i18n/tr';
import { useAuthStore } from '../../src/state/authStore';
import { ROUTES } from '../../src/navigation/routes';
import {
  cancelActivityBooking,
  createActivityBooking,
  createSpaAppointment,
  getSpaAvailability,
  listActivities,
  listActivityBookings,
  listActivityResources,
  listSpaAppointments,
  listSpaServices,
  listSpaTherapists,
  updateSpaAppointmentStatus,
  type Activity,
  type ActivityBooking,
  type ActivityResource,
  type SpaAppointment,
  type SpaAppointmentStatus,
  type SpaAvailabilitySlot,
} from '../../src/api/spa';
import { searchGuests, type Guest } from '../../src/api/guests';
import { listViewState } from '../../src/utils/departmentScreens';
import { errorMessage, isOffline } from '../../src/utils/errors';
import { formatCurrency, formatDate, formatTime } from '../../src/utils/format';
import { haptic } from '../../src/hooks/useHaptic';

type Range = 'today' | 'week' | 'date';

type EmptyIcon = React.ComponentProps<typeof EmptyState>['icon'];

function isoDate(d: Date): string {
  return d.toISOString().slice(0, 10);
}

// The backend filters `starts_at` with string $gte/$lte against stored ISO
// datetimes (e.g. "2026-06-12T11:30:00+00:00"). A bare YYYY-MM-DD upper bound
// sorts lexicographically *before* same-day datetimes, so it would silently
// drop that day's appointments. We therefore send full day boundaries
// (00:00:00 .. 23:59:59) so the inclusive range covers the whole day.
function rangeParams(
  range: Range,
  customDate: string | undefined,
): { date_from: string; date_to: string } {
  const dayBounds = (fromDay: string, toDay: string) => ({
    date_from: `${fromDay}T00:00:00`,
    date_to: `${toDay}T23:59:59`,
  });
  if (range === 'date' && customDate) {
    return dayBounds(customDate, customDate);
  }
  const now = new Date();
  const fromDay = isoDate(now);
  const to = new Date(now);
  if (range === 'week') to.setDate(to.getDate() + 6);
  return dayBounds(fromDay, isoDate(to));
}

function appointmentTone(status?: string):
  | 'default'
  | 'success'
  | 'warning'
  | 'danger'
  | 'info' {
  switch (status) {
    case 'completed':
      return 'success';
    case 'in_progress':
      return 'info';
    case 'no_show':
    case 'cancelled':
      return 'danger';
    case 'scheduled':
      return 'warning';
    default:
      return 'default';
  }
}

function statusLabel(status?: string): string {
  const map = tr.departments.spa.statuses as Record<string, string>;
  return (status && map[status]) || status || '—';
}

function activityStatusTone(status?: string):
  | 'default'
  | 'success'
  | 'warning'
  | 'danger'
  | 'info' {
  switch (status) {
    case 'completed':
      return 'success';
    case 'cancelled':
    case 'no_show':
      return 'danger';
    case 'booked':
      return 'info';
    default:
      return 'default';
  }
}

function activityStatusLabel(status?: string): string {
  const map = tr.departments.spa.activities.statuses as Record<string, string>;
  return (status && map[status]) || status || '—';
}

function activityTypeLabel(type?: string): string {
  const map = tr.departments.spa.activities.types as Record<string, string>;
  return (type && map[type]) || type || '';
}

function resourceKindLabel(kind?: string): string {
  const map = tr.departments.spa.activities.kinds as Record<string, string>;
  return (kind && map[kind]) || kind || '';
}

// Mirror of backend `_SPA_TRANSITIONS` (backend/domains/spa/router.py). Used
// ONLY to decide which actions to surface — the backend remains the source of
// truth and re-validates every transition (and the role gate on `completed`).
const SPA_TRANSITIONS: Record<string, SpaAppointmentStatus[]> = {
  scheduled: ['in_progress', 'completed', 'no_show', 'cancelled'],
  in_progress: ['completed', 'cancelled'],
  completed: [],
  no_show: [],
  cancelled: [],
};

function statusActionLabel(status: SpaAppointmentStatus): string {
  const map = tr.departments.spa.statusActions as Record<string, string>;
  return map[status] || statusLabel(status);
}

function statusActionIcon(status: SpaAppointmentStatus): EmptyIcon {
  switch (status) {
    case 'in_progress':
      return 'play';
    case 'completed':
      return 'checkmark';
    case 'no_show':
      return 'close-circle-outline';
    case 'cancelled':
      return 'ban-outline';
    default:
      return 'ellipse-outline';
  }
}

const TIME_RE = /^([01]\d|2[0-3]):([0-5]\d)$/;

// Combine a YYYY-MM-DD day and a HH:MM wall time into an ISO instant. The
// backend treats the value as the appointment start; we send an explicit ISO
// (with offset) so there is no naive-vs-UTC ambiguity on the wire.
function buildStartsAt(dateISO: string, hhmm: string): string {
  return new Date(`${dateISO}T${hhmm}:00`).toISOString();
}

// Render a slot's UTC ISO start as a local HH:MM. This is the same wall time the
// user sees in the appointment list (formatTime), and feeding it back through
// buildStartsAt reconstructs the identical UTC instant — so selecting a slot and
// submitting round-trips to the very window availability reported as free.
function slotTimeValue(iso: string): string {
  const d = new Date(iso);
  const hh = String(d.getHours()).padStart(2, '0');
  const mm = String(d.getMinutes()).padStart(2, '0');
  return `${hh}:${mm}`;
}

// Activity-booking card. Shows the activity / resource / time and — for a still
// "booked" planning — an inline two-step cancel (Alert.alert is a no-op on Expo
// Web, the e2e target, so we confirm in-card like the HR leave decisions). On
// success it invalidates the 'activity-bookings' query so the list refreshes and
// the status badge flips to "İptal". The backend re-enforces auth on the cancel.
function BookingCard({
  booking,
  activityLabel,
  resourceLabel,
}: {
  booking: ActivityBooking;
  activityLabel: string;
  resourceLabel: string;
}) {
  const c = useTheme();
  const qc = useQueryClient();
  const A = tr.departments.spa.activities;
  const [confirming, setConfirming] = useState(false);

  const cancellable = (booking.status || 'booked') === 'booked';

  const cancelMut = useMutation({
    mutationFn: () => cancelActivityBooking(booking.id),
    onSuccess: () => {
      haptic.success();
      setConfirming(false);
      qc.invalidateQueries({ queryKey: ['activity-bookings'] });
    },
    onError: () => {
      haptic.error();
    },
  });

  return (
    <Card style={{ marginBottom: spacing.sm }} accent={c.primary}>
      <View
        style={{
          flexDirection: 'row',
          justifyContent: 'space-between',
          alignItems: 'flex-start',
        }}
      >
        <View style={{ flex: 1, paddingRight: spacing.sm }}>
          <Body style={{ fontWeight: '600' }}>{activityLabel}</Body>
          {booking.guest_name ? <Muted>{booking.guest_name}</Muted> : null}
          <Muted>
            {A.resource}: {resourceLabel}
          </Muted>
        </View>
        <Badge
          label={activityStatusLabel(booking.status)}
          tone={activityStatusTone(booking.status)}
        />
      </View>
      <View style={{ marginTop: spacing.sm, gap: 2 }}>
        <Muted>
          {formatDate(booking.starts_at)} · {formatTime(booking.starts_at)}
          {booking.ends_at ? ` – ${formatTime(booking.ends_at)}` : ''}
        </Muted>
        {booking.note ? <Muted>{booking.note}</Muted> : null}
      </View>

      {cancelMut.isError ? (
        <Muted style={{ marginTop: spacing.xs, color: c.danger }}>
          {errorMessage(cancelMut.error, A.cancelError)}
        </Muted>
      ) : null}

      {cancellable ? (
        confirming ? (
          <View style={{ marginTop: spacing.sm, gap: spacing.sm }}>
            <Muted>{A.cancelConfirm}</Muted>
            <SegmentedActions>
              <ActionButton
                label={A.keep}
                icon="arrow-undo"
                onPress={() => setConfirming(false)}
                bg={c.surfaceAlt}
                fg={c.text}
                disabled={cancelMut.isPending}
              />
              <ActionButton
                testID={`activity-booking-cancel-confirm-${booking.id}`}
                label={A.cancel}
                icon="close-circle"
                onPress={() => cancelMut.mutate()}
                bg={c.danger}
                fg="#ffffff"
                loading={cancelMut.isPending}
              />
            </SegmentedActions>
          </View>
        ) : (
          <View style={{ marginTop: spacing.sm }}>
            <SegmentedActions>
              <ActionButton
                testID={`activity-booking-cancel-${booking.id}`}
                label={A.cancel}
                icon="close-circle"
                onPress={() => {
                  haptic.tap();
                  if (cancelMut.isError) cancelMut.reset();
                  setConfirming(true);
                }}
                bg={c.danger + '14'}
                fg={c.danger}
              />
            </SegmentedActions>
          </View>
        )
      ) : null}
    </Card>
  );
}

// Compact KPI tile for the occupancy strip: a soft-tinted icon chip, a large
// number and a muted label. Derived entirely from the live appointment list —
// no placeholder data. Tone drives the accent so the strip reads at a glance.
function StatTile({
  label,
  value,
  icon,
  tone,
}: {
  label: string;
  value: number;
  icon: EmptyIcon;
  tone: 'primary' | 'success' | 'warning' | 'info' | 'danger';
}) {
  const c = useTheme();
  const toneColor: Record<string, string> = {
    primary: c.primary,
    success: c.success,
    warning: c.warning,
    info: c.info,
    danger: c.danger,
  };
  const accent = toneColor[tone];
  return (
    <Card style={{ flexGrow: 1, flexBasis: '47%', minWidth: 140 }} accent={accent}>
      <View style={{ flexDirection: 'row', alignItems: 'center', gap: spacing.sm }}>
        <View
          style={{
            width: 36,
            height: 36,
            borderRadius: radius.pill,
            backgroundColor: accent + '1f',
            alignItems: 'center',
            justifyContent: 'center',
          }}
        >
          <Ionicons name={icon} size={20} color={accent} />
        </View>
        <View style={{ flex: 1 }}>
          <Text style={{ color: c.text, fontSize: 24, fontWeight: '800', letterSpacing: -0.4 }}>
            {value}
          </Text>
          <Muted numberOfLines={1}>{label}</Muted>
        </View>
      </View>
    </Card>
  );
}

// A single agenda row on the time axis: the wall-clock start (and end) sit on a
// left rail with a colored node + connector line, the appointment card to the
// right. The node colour follows the therapist's colour when known, else the
// status tone — so the timeline reads like a real day planner.
function TimelineRow({
  appt,
  therapistColor,
  isFirst,
  isLast,
  children,
}: {
  appt: SpaAppointment;
  therapistColor?: string;
  isFirst: boolean;
  isLast: boolean;
  children: React.ReactNode;
}) {
  const c = useTheme();
  const toneMap: Record<string, string> = {
    success: c.success,
    info: c.info,
    danger: c.danger,
    warning: c.warning,
    default: c.textMuted,
  };
  const nodeColor = therapistColor || toneMap[appointmentTone(appt.status)] || c.primary;
  return (
    <View style={{ flexDirection: 'row' }}>
      {/* Time gutter */}
      <View style={{ width: 52, alignItems: 'flex-end', paddingTop: 2 }}>
        <Text style={{ color: c.text, fontSize: 15, fontWeight: '700' }}>
          {formatTime(appt.starts_at)}
        </Text>
        {appt.ends_at ? (
          <Text style={{ color: c.textMuted, fontSize: 11 }}>{formatTime(appt.ends_at)}</Text>
        ) : null}
      </View>
      {/* Rail */}
      <View style={{ width: 24, alignItems: 'center' }}>
        <View
          style={{
            position: 'absolute',
            top: isFirst ? 8 : 0,
            bottom: isLast ? undefined : 0,
            height: isLast ? 16 : undefined,
            width: 2,
            backgroundColor: c.border,
          }}
        />
        <View
          style={{
            width: 12,
            height: 12,
            borderRadius: radius.pill,
            backgroundColor: nodeColor,
            borderWidth: 2,
            borderColor: c.surface,
            marginTop: 6,
          }}
        />
      </View>
      {/* Card */}
      <View style={{ flex: 1, paddingBottom: spacing.sm }}>{children}</View>
    </View>
  );
}

// Spa & Wellness screen. Reads (appointments / services / therapists) are open
// to any authenticated user; the (departments) entitlement just decides whether
// the screen is shown. The "new appointment" form posts to a backend that still
// enforces require_spa_ops + manage_sales, so a non-privileged user simply gets
// a 403 surfaced inline.
export default function SpaScreen() {
  const c = useTheme();
  const qc = useQueryClient();
  const spaAccess = useAuthStore((s) => s.spaAccess);
  const S = tr.departments.spa;

  const [view, setView] = useState<'spa' | 'activities'>('spa');

  const [range, setRange] = useState<Range>('today');
  const [customDate, setCustomDate] = useState<string | undefined>(undefined);

  const params = useMemo(() => rangeParams(range, customDate), [range, customDate]);

  const apptsQ = useQuery({
    queryKey: ['spa-appointments', params.date_from, params.date_to],
    queryFn: () => listSpaAppointments(params),
  });
  const servicesQ = useQuery({ queryKey: ['spa-services'], queryFn: listSpaServices });
  const therapistsQ = useQuery({ queryKey: ['spa-therapists'], queryFn: listSpaTherapists });

  const therapistName = useMemo(() => {
    const m = new Map<string, string>();
    (therapistsQ.data || []).forEach((t) => m.set(t.id, t.name));
    return m;
  }, [therapistsQ.data]);

  const therapistColor = useMemo(() => {
    const m = new Map<string, string>();
    (therapistsQ.data || []).forEach((t) => {
      if (t.color) m.set(t.id, t.color);
    });
    return m;
  }, [therapistsQ.data]);

  // Appointment derivations for the calendar-centric layout. The agenda shows
  // the live (scheduled / in_progress) appointments on the time axis; terminal
  // ones (completed / cancelled / no_show) drop into the işlem geçmişi section.
  // All sorted by start so the day reads top-to-bottom. Purely a view split —
  // the same raw list the backend returned, never seeded or faked.
  const sortedAppts = useMemo(() => {
    const items = [...(apptsQ.data || [])];
    items.sort((a, b) => (a.starts_at || '').localeCompare(b.starts_at || ''));
    return items;
  }, [apptsQ.data]);

  const activeAppts = useMemo(
    () =>
      sortedAppts.filter(
        (a) => (a.status || 'scheduled') === 'scheduled' || a.status === 'in_progress',
      ),
    [sortedAppts],
  );
  const historyAppts = useMemo(
    () =>
      sortedAppts.filter(
        (a) =>
          a.status === 'completed' || a.status === 'cancelled' || a.status === 'no_show',
      ),
    [sortedAppts],
  );

  // Per-day grouping for the agenda so the week range reads as a planner with
  // day headers; a single day collapses to one group.
  const agendaByDay = useMemo(() => {
    const groups = new Map<string, SpaAppointment[]>();
    activeAppts.forEach((a) => {
      const key = (a.starts_at || '').slice(0, 10) || '—';
      const arr = groups.get(key) || [];
      arr.push(a);
      groups.set(key, arr);
    });
    return Array.from(groups.entries()).map(([day, items]) => ({ day, items }));
  }, [activeAppts]);

  const occupancyStats = useMemo(() => {
    let scheduled = 0;
    let inProgress = 0;
    let completed = 0;
    let closed = 0;
    sortedAppts.forEach((a) => {
      switch (a.status) {
        case 'in_progress':
          inProgress += 1;
          break;
        case 'completed':
          completed += 1;
          break;
        case 'cancelled':
        case 'no_show':
          closed += 1;
          break;
        default:
          scheduled += 1;
      }
    });
    return { total: sortedAppts.length, scheduled, inProgress, completed, closed };
  }, [sortedAppts]);

  // Active (non-terminal) load per therapist, surfaced on the therapist cards.
  const therapistLoad = useMemo(() => {
    const m = new Map<string, number>();
    activeAppts.forEach((a) => {
      if (a.therapist_id) m.set(a.therapist_id, (m.get(a.therapist_id) || 0) + 1);
    });
    return m;
  }, [activeAppts]);

  // ── Activity scheduler state ──────────────────────────────────────────────
  const A = S.activities;
  // Bookings are queried for a single day; the catalogue / resources are global.
  const [activityDate, setActivityDate] = useState<string>(() => isoDate(new Date()));

  const bookingsQ = useQuery({
    queryKey: ['activity-bookings', activityDate],
    queryFn: () => listActivityBookings({ date: activityDate }),
    enabled: view === 'activities',
  });
  const activitiesQ = useQuery({
    queryKey: ['activities'],
    queryFn: () => listActivities(),
    enabled: view === 'activities',
  });
  const resourcesQ = useQuery({
    queryKey: ['activity-resources'],
    queryFn: () => listActivityResources(),
    enabled: view === 'activities',
  });

  const activityName = useMemo(() => {
    const m = new Map<string, string>();
    (activitiesQ.data || []).forEach((a) => m.set(a.id, a.name));
    return m;
  }, [activitiesQ.data]);
  const resourceName = useMemo(() => {
    const m = new Map<string, string>();
    (resourcesQ.data || []).forEach((r) => m.set(r.id, r.name));
    return m;
  }, [resourcesQ.data]);

  // ── New-activity-booking form state ───────────────────────────────────────
  const [actFormOpen, setActFormOpen] = useState(false);
  const [aActivity, setAActivity] = useState<string | undefined>(undefined);
  const [aResource, setAResource] = useState<string | undefined>(undefined);
  const [aGuest, setAGuest] = useState<Guest | null>(null);
  const [aGuestQuery, setAGuestQuery] = useState('');
  const [aDate, setADate] = useState<string | undefined>(undefined);
  const [aTime, setATime] = useState('');
  const [aNote, setANote] = useState('');
  const [actFormError, setActFormError] = useState<string | null>(null);

  const guestSearchQ = useQuery({
    queryKey: ['activity-guest-search', aGuestQuery.trim()],
    queryFn: () => searchGuests(aGuestQuery.trim()),
    enabled: actFormOpen && !aGuest && aGuestQuery.trim().length >= 2,
    staleTime: 30_000,
  });

  const resetActForm = () => {
    setAActivity(undefined);
    setAResource(undefined);
    setAGuest(null);
    setAGuestQuery('');
    setADate(undefined);
    setATime('');
    setANote('');
    setActFormError(null);
  };

  const openActForm = () => {
    resetActForm();
    setADate(activityDate);
    setActFormOpen(true);
  };

  const createBookingMut = useMutation({
    mutationFn: createActivityBooking,
    onSuccess: () => {
      qc.invalidateQueries({ queryKey: ['activity-bookings'] });
      setActFormOpen(false);
      resetActForm();
      Alert.alert(tr.app.success, A.created);
    },
    onError: (e: unknown) => setActFormError(errorMessage(e, A.createError)),
  });

  const submitActForm = () => {
    setActFormError(null);
    if (!aActivity || !aResource || !aGuest || !aDate || !aTime.trim()) {
      setActFormError(A.validationMissing);
      return;
    }
    if (!TIME_RE.test(aTime.trim())) {
      setActFormError(S.validationTime);
      return;
    }
    createBookingMut.mutate({
      activity_id: aActivity,
      resource_id: aResource,
      guest_id: aGuest.id,
      starts_at: buildStartsAt(aDate, aTime.trim()),
      note: aNote.trim() || null,
    });
  };

  const guestLabel = (g: Guest): string =>
    [g.first_name, g.last_name].filter(Boolean).join(' ').trim() ||
    g.full_name ||
    g.email ||
    g.phone ||
    g.id;

  // ── New-appointment form state ────────────────────────────────────────────
  const [formOpen, setFormOpen] = useState(false);
  const [fService, setFService] = useState<string | undefined>(undefined);
  const [fTherapist, setFTherapist] = useState<string | undefined>(undefined);
  const [fDate, setFDate] = useState<string | undefined>(undefined);
  const [fTime, setFTime] = useState('');
  const [fGuest, setFGuest] = useState('');
  const [fPhone, setFPhone] = useState('');
  const [fNotes, setFNotes] = useState('');
  const [formError, setFormError] = useState<string | null>(null);

  const resetForm = () => {
    setFService(undefined);
    setFTherapist(undefined);
    setFDate(undefined);
    setFTime('');
    setFGuest('');
    setFPhone('');
    setFNotes('');
    setFormError(null);
  };

  const openForm = () => {
    resetForm();
    setFDate(customDate || isoDate(new Date()));
    setFormOpen(true);
  };

  // Live availability: once a service + date are chosen we ask the backend for
  // the therapist x slot grid so staff can pick a free slot instead of typing.
  // Kept disabled until both are present (the endpoint requires a date and the
  // service drives the block duration).
  const availabilityQ = useQuery({
    queryKey: ['spa-availability', fService, fDate],
    queryFn: () => getSpaAvailability({ date: fDate!, service_id: fService }),
    enabled: formOpen && !!fService && !!fDate,
  });

  // A slot is offered when the chosen therapist is free in it; with no therapist
  // selected ("auto") we fall back to the any-therapist summary.
  const slotOpen = (slot: SpaAvailabilitySlot): boolean => {
    if (fTherapist) {
      return slot.therapists.some(
        (t) => t.therapist_id === fTherapist && t.available,
      );
    }
    return slot.any_available;
  };

  const createMut = useMutation({
    mutationFn: createSpaAppointment,
    onSuccess: () => {
      qc.invalidateQueries({ queryKey: ['spa-appointments'] });
      setFormOpen(false);
      resetForm();
      Alert.alert(tr.app.success, S.created);
    },
    onError: (e: unknown) => setFormError(errorMessage(e, S.createError)),
  });

  const submitForm = () => {
    setFormError(null);
    if (!fService || !fDate || !fTime.trim() || !fGuest.trim()) {
      setFormError(S.validationMissing);
      return;
    }
    if (!TIME_RE.test(fTime.trim())) {
      setFormError(S.validationTime);
      return;
    }
    createMut.mutate({
      service_id: fService,
      starts_at: buildStartsAt(fDate, fTime.trim()),
      guest_name: fGuest.trim(),
      therapist_id: fTherapist || null,
      guest_phone: fPhone.trim() || null,
      notes: fNotes.trim() || null,
    });
  };

  // ── Status-transition state ───────────────────────────────────────────────
  // Tapping an appointment card opens this sheet with only the transitions the
  // backend would accept from its current status. The backend re-validates the
  // transition and enforces require_finance on `completed`; any 403/409 is
  // surfaced inline rather than swallowed.
  const [activeAppt, setActiveAppt] = useState<SpaAppointment | null>(null);
  const [statusError, setStatusError] = useState<string | null>(null);

  const statusMut = useMutation({
    mutationFn: (vars: { id: string; status: SpaAppointmentStatus }) =>
      updateSpaAppointmentStatus(vars.id, vars.status),
    onSuccess: () => {
      qc.invalidateQueries({ queryKey: ['spa-appointments'] });
      setActiveAppt(null);
      setStatusError(null);
      Alert.alert(tr.app.success, S.statusUpdated);
    },
    onError: (e: unknown) => setStatusError(errorMessage(e, S.statusUpdateError)),
  });

  const openStatusSheet = (a: SpaAppointment) => {
    setStatusError(null);
    setActiveAppt(a);
  };

  const submitStatus = (status: SpaAppointmentStatus) => {
    if (!activeAppt) return;
    setStatusError(null);
    statusMut.mutate({ id: activeAppt.id, status });
  };

  const activeTransitions = activeAppt
    ? SPA_TRANSITIONS[activeAppt.status || 'scheduled'] || []
    : [];

  // Hard guard: a user who somehow lands here without spa entitlement is sent
  // to the hub. This is cosmetic only — the backend still enforces every write.
  if (!spaAccess) return <Redirect href={ROUTES.departments} />;

  // Shared loading / error / empty / data renderer so each section presents
  // states identically. Uses EmptyState for the empty branch per the design kit.
  const renderSection = <T,>(
    q: { isLoading: boolean; error: unknown; data?: T[] },
    empty: { icon: EmptyIcon; title: string; message?: string },
    render: (items: T[]) => React.ReactNode,
  ): React.ReactNode => {
    const items = q.data || [];
    const state = listViewState({
      loading: q.isLoading,
      error: q.error,
      isEmpty: items.length === 0,
    });
    if (state === 'loading') {
      return (
        <View style={{ gap: spacing.sm }}>
          {[0, 1, 2].map((i) => (
            <SkeletonCard key={i} />
          ))}
        </View>
      );
    }
    if (state === 'error') {
      const msg = isOffline(q.error)
        ? tr.app.offline
        : errorMessage(q.error, tr.departments.loadError);
      return (
        <Card>
          <Body>{msg}</Body>
        </Card>
      );
    }
    if (state === 'empty') {
      return <EmptyState icon={empty.icon} title={empty.title} message={empty.message} />;
    }
    return render(items);
  };

  const RangeTab: React.FC<{ value: Range; label: string }> = ({ value, label }) => {
    const active = range === value;
    return (
      <Pressable
        onPress={() => setRange(value)}
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

  // Shared appointment card. `context='timeline'` drops the date line (the rail
  // already carries the time) and the bottom margin (the row owns spacing);
  // `context='history'` keeps a full date+time line and stacks with a margin.
  // Tapping always opens the status sheet — the backend re-validates every
  // transition, so a terminal appointment simply shows "no transitions".
  const renderAppointmentCard = (
    a: SpaAppointment,
    context: 'timeline' | 'history',
  ) => {
    const canManage = (SPA_TRANSITIONS[a.status || 'scheduled'] || []).length > 0;
    const accent =
      (a.therapist_id && therapistColor.get(a.therapist_id)) || c.primary;
    return (
      <Pressable
        key={a.id}
        onPress={() => openStatusSheet(a)}
        accessibilityRole="button"
        accessibilityLabel={`${a.service_name || ''} ${S.manageAppointment}`}
        testID={`spa-appointment-${a.id}`}
        style={({ pressed }) => ({ opacity: pressed ? 0.85 : 1 })}
      >
        <Card
          style={context === 'history' ? { marginBottom: spacing.sm } : undefined}
          accent={accent}
        >
          <View
            style={{
              flexDirection: 'row',
              justifyContent: 'space-between',
              alignItems: 'flex-start',
            }}
          >
            <View style={{ flex: 1, paddingRight: spacing.sm }}>
              <Body style={{ fontWeight: '700' }}>{a.service_name || '—'}</Body>
              {a.guest_name ? <Muted>{a.guest_name}</Muted> : null}
            </View>
            <Badge label={statusLabel(a.status)} tone={appointmentTone(a.status)} />
          </View>
          <View style={{ marginTop: spacing.sm, gap: 2 }}>
            {context === 'history' ? (
              <Muted>
                {formatDate(a.starts_at)} · {formatTime(a.starts_at)}
                {a.ends_at ? ` – ${formatTime(a.ends_at)}` : ''}
              </Muted>
            ) : null}
            <View style={{ flexDirection: 'row', alignItems: 'center', gap: 6 }}>
              <Ionicons name="person-outline" size={13} color={c.textMuted} />
              <Muted>
                {(a.therapist_id && therapistName.get(a.therapist_id)) || S.unassigned}
              </Muted>
            </View>
            {typeof a.price === 'number' ? (
              <View style={{ flexDirection: 'row', alignItems: 'center', gap: 6 }}>
                <Ionicons name="pricetag-outline" size={13} color={c.textMuted} />
                <Muted>{formatCurrency(a.price, a.currency)}</Muted>
              </View>
            ) : null}
          </View>
          {canManage ? (
            <View
              style={{
                marginTop: spacing.sm,
                flexDirection: 'row',
                gap: 4,
                alignItems: 'center',
              }}
            >
              <Ionicons name="swap-horizontal" size={14} color={c.primary} />
              <Body style={{ color: c.primary, fontSize: 13, fontWeight: '600' }}>
                {S.changeStatus}
              </Body>
            </View>
          ) : null}
        </Card>
      </Pressable>
    );
  };

  // The calendar-centric agenda: per-day groups (single day collapses to one),
  // each appointment on the time rail. Day header only shows when more than one
  // day is in range (week view) to keep a single day clean.
  const renderAgenda = (groups: { day: string; items: SpaAppointment[] }[]) => {
    const multiDay = groups.length > 1;
    return (
      <View>
        {groups.map((group) => (
          <View key={group.day} style={{ marginBottom: multiDay ? spacing.md : 0 }}>
            {multiDay ? (
              <View
                style={{
                  flexDirection: 'row',
                  alignItems: 'center',
                  gap: spacing.sm,
                  marginBottom: spacing.sm,
                }}
              >
                <Ionicons name="calendar-outline" size={15} color={c.primary} />
                <Body style={{ fontWeight: '700' }}>{formatDate(group.day)}</Body>
              </View>
            ) : null}
            {group.items.map((a, idx) => (
              <TimelineRow
                key={a.id}
                appt={a}
                therapistColor={
                  (a.therapist_id && therapistColor.get(a.therapist_id)) || undefined
                }
                isFirst={idx === 0}
                isLast={idx === group.items.length - 1}
              >
                {renderAppointmentCard(a, 'timeline')}
              </TimelineRow>
            ))}
          </View>
        ))}
      </View>
    );
  };

  const renderBooking = (b: ActivityBooking) => (
    <BookingCard
      key={b.id}
      booking={b}
      activityLabel={activityName.get(b.activity_id) || A.activity}
      resourceLabel={resourceName.get(b.resource_id) || '—'}
    />
  );

  const ViewTab: React.FC<{ value: 'spa' | 'activities'; label: string }> = ({
    value,
    label,
  }) => {
    const active = view === value;
    return (
      <Pressable
        onPress={() => setView(value)}
        accessibilityRole="button"
        testID={`spa-view-${value}`}
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

  return (
    <ScrollView
      style={{ flex: 1, backgroundColor: c.bg }}
      contentContainerStyle={[{ padding: spacing.lg, paddingBottom: spacing.xl }, webCenter]}
    >
      <H1>{S.title}</H1>

      {/* ── View switch: Spa appointments vs Activity scheduler ─────────────── */}
      <View style={{ flexDirection: 'row', gap: spacing.sm, marginTop: spacing.sm }}>
        <ViewTab value="spa" label={S.viewSpa} />
        <ViewTab value="activities" label={S.viewActivities} />
      </View>
      <View style={{ height: spacing.md }} />

      {view === 'spa' ? (
        <>
      <Muted style={{ marginBottom: spacing.md }}>{S.subtitle}</Muted>

      {/* ── Range + date selection (drives the calendar window) ────────────── */}
      <View style={{ flexDirection: 'row', gap: spacing.sm, marginBottom: spacing.sm }}>
        <RangeTab value="today" label={S.today} />
        <RangeTab value="week" label={S.week} />
      </View>
      <View style={{ marginBottom: spacing.md }}>
        <DatePicker
          value={range === 'date' ? customDate : undefined}
          placeholder={S.pickDate}
          allowClear
          testID="spa-date-picker"
          onChange={(iso) => {
            setCustomDate(iso);
            setRange(iso ? 'date' : 'today');
          }}
        />
      </View>

      {/* ── Occupancy strip (derived from the live appointment list) ───────── */}
      {!apptsQ.isLoading && !apptsQ.error && occupancyStats.total > 0 ? (
        <View style={{ marginBottom: spacing.sm }}>
          <SectionTitle title={S.occupancy} />
          <View
            style={{
              flexDirection: 'row',
              flexWrap: 'wrap',
              gap: spacing.sm,
            }}
          >
            <StatTile
              label={S.statScheduled}
              value={occupancyStats.scheduled}
              icon="calendar-outline"
              tone="warning"
            />
            <StatTile
              label={S.statInProgress}
              value={occupancyStats.inProgress}
              icon="play"
              tone="info"
            />
            <StatTile
              label={S.statCompleted}
              value={occupancyStats.completed}
              icon="checkmark-circle-outline"
              tone="success"
            />
            <StatTile
              label={S.statClosed}
              value={occupancyStats.closed}
              icon="close-circle-outline"
              tone="danger"
            />
          </View>
        </View>
      ) : null}

      <Button
        title={S.newAppointment}
        icon="add"
        onPress={openForm}
        fullWidth
        style={{ marginBottom: spacing.md }}
      />

      {/* ── Agenda timeline (active appointments on the time axis) ─────────── */}
      <SectionTitle title={S.agenda} />
      {renderSection(
        { isLoading: apptsQ.isLoading, error: apptsQ.error, data: activeAppts },
        { icon: 'calendar-outline', title: S.noActiveAppointments },
        () => renderAgenda(agendaByDay),
      )}

      {/* ── İşlem geçmişi (terminal appointments in range) ─────────────────── */}
      {!apptsQ.isLoading && !apptsQ.error && historyAppts.length > 0 ? (
        <>
          <SectionTitle title={S.history} />
          <View>{historyAppts.map((a) => renderAppointmentCard(a, 'history'))}</View>
        </>
      ) : null}

      {/* ── Therapists (premium cards with live load) ──────────────────────── */}
      <SectionTitle title={S.therapists} />
      {renderSection(
        therapistsQ,
        { icon: 'people-outline', title: S.noTherapists },
        (items) => (
          <View>
            {items.map((t) => {
              const load = therapistLoad.get(t.id) || 0;
              return (
                <Card
                  key={t.id}
                  style={{ marginBottom: spacing.sm }}
                  accent={t.color || c.primary}
                >
                  <View
                    style={{
                      flexDirection: 'row',
                      alignItems: 'center',
                      justifyContent: 'space-between',
                      gap: spacing.sm,
                    }}
                  >
                    <View
                      style={{
                        flexDirection: 'row',
                        alignItems: 'center',
                        gap: spacing.sm,
                        flex: 1,
                      }}
                    >
                      <View
                        style={{
                          width: 12,
                          height: 12,
                          borderRadius: radius.pill,
                          backgroundColor: t.color || c.primary,
                        }}
                      />
                      <Body style={{ fontWeight: '700', flexShrink: 1 }} numberOfLines={1}>
                        {t.name}
                      </Body>
                    </View>
                    {load > 0 ? (
                      <Badge label={`${load} ${S.therapistLoad}`} tone="info" />
                    ) : null}
                  </View>
                  {t.specialties && t.specialties.length > 0 ? (
                    <Muted style={{ marginTop: spacing.sm }}>
                      {t.specialties.join(', ')}
                    </Muted>
                  ) : null}
                  {t.work_start && t.work_end ? (
                    <View
                      style={{
                        flexDirection: 'row',
                        alignItems: 'center',
                        gap: 6,
                        marginTop: 4,
                      }}
                    >
                      <Ionicons name="time-outline" size={13} color={c.textMuted} />
                      <Muted>
                        {t.work_start} – {t.work_end}
                      </Muted>
                    </View>
                  ) : null}
                </Card>
              );
            })}
          </View>
        ),
      )}

      {/* ── Service catalogue (list pattern) ───────────────────────────────── */}
      <SectionTitle title={S.services} />
      {renderSection(
        servicesQ,
        { icon: 'flower-outline', title: S.noServices },
        (items) => (
          <ListGroup>
            {items.map((s, idx) => (
              <ListRow
                key={s.id}
                icon="flower-outline"
                label={s.name}
                sublabel={[
                  s.category,
                  typeof s.duration_minutes === 'number'
                    ? `${s.duration_minutes} ${S.minutes}`
                    : undefined,
                ]
                  .filter(Boolean)
                  .join(' · ')}
                value={
                  typeof s.price === 'number'
                    ? formatCurrency(s.price, s.currency)
                    : undefined
                }
                showChevron={false}
                last={idx === items.length - 1}
              />
            ))}
          </ListGroup>
        ),
      )}
        </>
      ) : (
        <>
      {/* ── Activity bookings (date-based list) ─────────────────────────────── */}
      <SectionTitle title={A.schedule} />
      <View style={{ marginBottom: spacing.md }}>
        <DatePicker
          value={activityDate}
          placeholder={S.pickDate}
          testID="activity-date-picker"
          onChange={(iso) => setActivityDate(iso || isoDate(new Date()))}
        />
      </View>

      <Button
        title={A.newBooking}
        icon="add"
        onPress={openActForm}
        fullWidth
        style={{ marginBottom: spacing.md }}
      />

      {renderSection(
        bookingsQ,
        { icon: 'calendar-outline', title: A.noBookings },
        (items) => <View>{items.map(renderBooking)}</View>,
      )}

      {/* ── Activity catalogue (list pattern) ──────────────────────────────── */}
      <SectionTitle title={A.catalog} />
      {renderSection(
        activitiesQ,
        { icon: 'bicycle-outline', title: A.noActivities },
        (items) => (
          <ListGroup>
            {items.map((a, idx) => (
              <ListRow
                key={a.id}
                icon="bicycle-outline"
                label={a.name}
                sublabel={[
                  activityTypeLabel(a.type),
                  typeof a.duration_min === 'number'
                    ? `${a.duration_min} ${S.minutes}`
                    : undefined,
                ]
                  .filter(Boolean)
                  .join(' · ')}
                value={
                  typeof a.price === 'number' && a.price > 0
                    ? formatCurrency(a.price)
                    : undefined
                }
                showChevron={false}
                last={idx === items.length - 1}
              />
            ))}
          </ListGroup>
        ),
      )}

      {/* ── Activity resources (list pattern) ──────────────────────────────── */}
      <SectionTitle title={A.resources} />
      {renderSection(
        resourcesQ,
        { icon: 'people-outline', title: A.noResources },
        (items) => (
          <ListGroup>
            {items.map((r, idx) => (
              <ListRow
                key={r.id}
                icon="person-outline"
                label={r.name}
                sublabel={[
                  resourceKindLabel(r.kind),
                  typeof r.capacity === 'number'
                    ? `${A.capacity}: ${r.capacity}`
                    : undefined,
                ]
                  .filter(Boolean)
                  .join(' · ')}
                showChevron={false}
                last={idx === items.length - 1}
              />
            ))}
          </ListGroup>
        ),
      )}
        </>
      )}

      {/* ── New-appointment form (standard form pattern) ───────────────────── */}
      <ActionSheet
        visible={formOpen}
        onClose={() => setFormOpen(false)}
        title={S.newAppointmentTitle}
        testID="spa-new-appointment-sheet"
      >
        <Muted>{S.service}</Muted>
        <Card padded={false}>
          {(servicesQ.data || []).length === 0 ? (
            <View style={{ padding: spacing.md }}>
              <Muted>{S.noServices}</Muted>
            </View>
          ) : (
            (servicesQ.data || []).map((s, idx, arr) => (
              <ListRow
                key={s.id}
                icon="flower-outline"
                label={s.name}
                sublabel={
                  typeof s.price === 'number'
                    ? formatCurrency(s.price, s.currency)
                    : undefined
                }
                active={fService === s.id}
                showChevron={false}
                last={idx === arr.length - 1}
                onPress={() => setFService(s.id)}
              />
            ))
          )}
        </Card>

        <Muted>{S.therapist}</Muted>
        <Card padded={false}>
          <ListRow
            icon="shuffle-outline"
            label={S.therapistAuto}
            active={!fTherapist}
            showChevron={false}
            onPress={() => setFTherapist(undefined)}
            last={(therapistsQ.data || []).length === 0}
          />
          {(therapistsQ.data || []).map((t, idx, arr) => (
            <ListRow
              key={t.id}
              icon="person-outline"
              label={t.name}
              active={fTherapist === t.id}
              showChevron={false}
              last={idx === arr.length - 1}
              onPress={() => setFTherapist(t.id)}
            />
          ))}
        </Card>

        <Muted>{S.dateLabel}</Muted>
        <DatePicker
          value={fDate}
          placeholder={S.pickDate}
          testID="spa-form-date"
          onChange={(iso) => setFDate(iso)}
        />

        <Field
          label={S.time}
          value={fTime}
          onChangeText={setFTime}
          placeholder={S.timePlaceholder}
          keyboardType="numbers-and-punctuation"
          autoCapitalize="none"
        />

        {/* Live availability slots — picking one fills the time field above. */}
        <Muted>{S.availableSlots}</Muted>
        {!fService || !fDate ? (
          <Muted style={{ marginBottom: spacing.sm }}>{S.availabilityHint}</Muted>
        ) : availabilityQ.isLoading ? (
          <Muted style={{ marginBottom: spacing.sm }}>{S.availabilityLoading}</Muted>
        ) : availabilityQ.error ? (
          <Muted style={{ marginBottom: spacing.sm, color: c.danger }}>
            {isOffline(availabilityQ.error)
              ? tr.app.offline
              : errorMessage(availabilityQ.error, S.availabilityError)}
          </Muted>
        ) : (() => {
            const all = availabilityQ.data?.slots || [];
            if (all.length === 0 || !all.some(slotOpen)) {
              return (
                <Muted style={{ marginBottom: spacing.sm }}>
                  {S.noAvailableSlots}
                </Muted>
              );
            }
            return (
              <View
                style={{
                  flexDirection: 'row',
                  flexWrap: 'wrap',
                  gap: spacing.sm,
                  marginBottom: spacing.sm,
                }}
              >
                {all.map((slot) => {
                  const label = slotTimeValue(slot.starts_at);
                  const open = slotOpen(slot);
                  const active = open && fTime === label;
                  return (
                    <Pressable
                      key={slot.starts_at}
                      onPress={() => open && setFTime(label)}
                      disabled={!open}
                      accessibilityRole="button"
                      accessibilityState={{ disabled: !open, selected: active }}
                      testID={`spa-slot-${label}`}
                      style={{
                        paddingVertical: spacing.sm,
                        paddingHorizontal: spacing.md,
                        borderRadius: radius.md,
                        opacity: open ? 1 : 0.4,
                        backgroundColor: active
                          ? c.primary
                          : open
                            ? c.surfaceAlt
                            : c.surface,
                        borderWidth: 1,
                        borderColor: active ? c.primary : c.border,
                      }}
                    >
                      <Body
                        style={{
                          color: active ? c.primaryText : c.text,
                          fontWeight: '600',
                          textDecorationLine: open ? 'none' : 'line-through',
                        }}
                      >
                        {label}
                      </Body>
                    </Pressable>
                  );
                })}
              </View>
            );
          })()}

        <Field
          label={S.guestName}
          value={fGuest}
          onChangeText={setFGuest}
          placeholder={S.guestNamePlaceholder}
        />
        <Field
          label={S.guestPhone}
          value={fPhone}
          onChangeText={setFPhone}
          placeholder={S.guestPhonePlaceholder}
          keyboardType="phone-pad"
        />
        <Field
          label={S.notes}
          value={fNotes}
          onChangeText={setFNotes}
          placeholder={S.notesPlaceholder}
          multiline
        />

        {formError ? (
          <Body style={{ color: c.danger }}>{formError}</Body>
        ) : null}

        <FormActions>
          <Button
            title={tr.app.cancel}
            variant="secondary"
            onPress={() => setFormOpen(false)}
          />
          <Button title={S.create} onPress={submitForm} loading={createMut.isPending} />
        </FormActions>
      </ActionSheet>

      {/* ── New-activity-booking form (standard form pattern) ──────────────── */}
      <ActionSheet
        visible={actFormOpen}
        onClose={() => setActFormOpen(false)}
        title={A.newBookingTitle}
        testID="activity-new-booking-sheet"
      >
        <Muted>{A.activity}</Muted>
        <Card padded={false}>
          {(activitiesQ.data || []).length === 0 ? (
            <View style={{ padding: spacing.md }}>
              <Muted>{A.noActivities}</Muted>
            </View>
          ) : (
            (activitiesQ.data || []).map((a, idx, arr) => (
              <ListRow
                key={a.id}
                icon="bicycle-outline"
                label={a.name}
                sublabel={activityTypeLabel(a.type) || undefined}
                active={aActivity === a.id}
                showChevron={false}
                last={idx === arr.length - 1}
                onPress={() => setAActivity(a.id)}
              />
            ))
          )}
        </Card>

        <Muted>{A.resource}</Muted>
        <Card padded={false}>
          {(resourcesQ.data || []).length === 0 ? (
            <View style={{ padding: spacing.md }}>
              <Muted>{A.noResources}</Muted>
            </View>
          ) : (
            (resourcesQ.data || []).map((r, idx, arr) => (
              <ListRow
                key={r.id}
                icon="person-outline"
                label={r.name}
                sublabel={resourceKindLabel(r.kind) || undefined}
                active={aResource === r.id}
                showChevron={false}
                last={idx === arr.length - 1}
                onPress={() => setAResource(r.id)}
              />
            ))
          )}
        </Card>

        <Muted>{A.guest}</Muted>
        {aGuest ? (
          <Card padded={false}>
            <ListRow
              icon="person-circle-outline"
              label={guestLabel(aGuest)}
              sublabel={aGuest.phone || aGuest.email || undefined}
              showChevron={false}
              last
              onPress={() => {
                setAGuest(null);
                setAGuestQuery('');
              }}
            />
          </Card>
        ) : (
          <>
            <Field
              value={aGuestQuery}
              onChangeText={setAGuestQuery}
              placeholder={A.guestSearchPlaceholder}
              autoCapitalize="none"
            />
            {aGuestQuery.trim().length < 2 ? (
              <Muted>{A.guestSearchHint}</Muted>
            ) : guestSearchQ.isLoading ? (
              <SkeletonCard />
            ) : (guestSearchQ.data || []).length === 0 ? (
              <Muted>{A.guestNoResults}</Muted>
            ) : (
              <Card padded={false}>
                {(guestSearchQ.data || []).slice(0, 8).map((g, idx, arr) => (
                  <ListRow
                    key={g.id}
                    icon="person-outline"
                    label={guestLabel(g)}
                    sublabel={g.phone || g.email || undefined}
                    showChevron={false}
                    last={idx === arr.length - 1}
                    onPress={() => {
                      setAGuest(g);
                      setAGuestQuery('');
                    }}
                  />
                ))}
              </Card>
            )}
          </>
        )}

        <Muted>{S.dateLabel}</Muted>
        <DatePicker
          value={aDate}
          placeholder={S.pickDate}
          testID="activity-form-date"
          onChange={(iso) => setADate(iso)}
        />

        <Field
          label={S.time}
          value={aTime}
          onChangeText={setATime}
          placeholder={S.timePlaceholder}
          keyboardType="numbers-and-punctuation"
          autoCapitalize="none"
        />
        <Field
          label={A.note}
          value={aNote}
          onChangeText={setANote}
          placeholder={A.notePlaceholder}
          multiline
        />

        {actFormError ? (
          <Body style={{ color: c.danger }}>{actFormError}</Body>
        ) : null}

        <FormActions>
          <Button
            title={tr.app.cancel}
            variant="secondary"
            onPress={() => setActFormOpen(false)}
          />
          <Button
            title={A.create}
            onPress={submitActForm}
            loading={createBookingMut.isPending}
          />
        </FormActions>
      </ActionSheet>

      {/* ── Appointment status-transition sheet ────────────────────────────── */}
      <ActionSheet
        visible={activeAppt !== null}
        onClose={() => setActiveAppt(null)}
        title={activeAppt ? activeAppt.service_name || S.manageAppointment : S.manageAppointment}
        testID="spa-status-sheet"
      >
        {activeAppt ? (
          <>
            {activeAppt.guest_name ? <Muted>{activeAppt.guest_name}</Muted> : null}
            <Muted>
              {S.currentStatus}: {statusLabel(activeAppt.status)}
            </Muted>

            {statusError ? (
              <Body style={{ color: c.danger, marginTop: spacing.sm }}>{statusError}</Body>
            ) : null}

            {activeTransitions.length === 0 ? (
              <Body style={{ marginTop: spacing.md }}>{S.noTransitions}</Body>
            ) : (
              <View style={{ marginTop: spacing.md }}>
                <Muted>{S.changeStatus}</Muted>
                <View style={{ marginTop: spacing.sm }}>
                  <SegmentedActions testID="spa-status-actions">
                    {activeTransitions.map((next) => {
                      const primary = next === 'completed' || next === 'in_progress';
                      return (
                        <ActionButton
                          key={next}
                          testID={`spa-status-${next}`}
                          label={statusActionLabel(next)}
                          icon={statusActionIcon(next)}
                          onPress={() => submitStatus(next)}
                          bg={primary ? c.primary : c.surfaceAlt}
                          fg={primary ? c.primaryText : c.text}
                          loading={statusMut.isPending}
                        />
                      );
                    })}
                  </SegmentedActions>
                </View>
                {activeTransitions.includes('completed') ? (
                  <Muted style={{ marginTop: spacing.sm }}>{S.financeRequired}</Muted>
                ) : null}
              </View>
            )}

            <View style={{ marginTop: spacing.lg }}>
              <Button
                title={tr.app.cancel}
                variant="secondary"
                onPress={() => setActiveAppt(null)}
                fullWidth
              />
            </View>
          </>
        ) : null}
      </ActionSheet>
    </ScrollView>
  );
}
