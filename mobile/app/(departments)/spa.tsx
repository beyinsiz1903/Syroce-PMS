import React, { useMemo, useState } from 'react';
import { Alert, Pressable, ScrollView, View } from 'react-native';
import { Redirect } from 'expo-router';
import { useMutation, useQuery, useQueryClient } from '@tanstack/react-query';
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
  ListGroup,
  ListRow,
  Muted,
  SectionTitle,
  SkeletonCard,
} from '../../src/components/ui';
import { DatePicker } from '../../src/components/DatePicker';
import { spacing, radius, useTheme } from '../../src/theme';
import { tr } from '../../src/i18n/tr';
import { useAuthStore } from '../../src/state/authStore';
import { ROUTES } from '../../src/navigation/routes';
import {
  createSpaAppointment,
  getSpaAvailability,
  listSpaAppointments,
  listSpaServices,
  listSpaTherapists,
  type SpaAppointment,
  type SpaAvailabilitySlot,
} from '../../src/api/spa';
import { listViewState } from '../../src/utils/departmentScreens';
import { errorMessage, isOffline } from '../../src/utils/errors';
import { formatCurrency, formatDate, formatTime } from '../../src/utils/format';

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

  const renderAppointment = (a: SpaAppointment) => (
    <Card key={a.id} style={{ marginBottom: spacing.sm }} accent={c.primary}>
      <View
        style={{
          flexDirection: 'row',
          justifyContent: 'space-between',
          alignItems: 'flex-start',
        }}
      >
        <View style={{ flex: 1, paddingRight: spacing.sm }}>
          <Body style={{ fontWeight: '600' }}>{a.service_name || '—'}</Body>
          {a.guest_name ? <Muted>{a.guest_name}</Muted> : null}
        </View>
        <Badge label={statusLabel(a.status)} tone={appointmentTone(a.status)} />
      </View>
      <View style={{ marginTop: spacing.sm, gap: 2 }}>
        <Muted>
          {formatDate(a.starts_at)} · {formatTime(a.starts_at)}
          {a.ends_at ? ` – ${formatTime(a.ends_at)}` : ''}
        </Muted>
        <Muted>
          {S.withTherapist}:{' '}
          {(a.therapist_id && therapistName.get(a.therapist_id)) || S.unassigned}
        </Muted>
        {typeof a.price === 'number' ? (
          <Muted>{formatCurrency(a.price, a.currency)}</Muted>
        ) : null}
      </View>
    </Card>
  );

  return (
    <ScrollView
      style={{ flex: 1, backgroundColor: c.bg }}
      contentContainerStyle={{ padding: spacing.lg, paddingBottom: spacing.xl }}
    >
      <H1>{S.title}</H1>

      {/* ── Appointments (date-selectable) ─────────────────────────────────── */}
      <SectionTitle title={S.appointments} />
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

      <Button
        title={S.newAppointment}
        icon="add"
        onPress={openForm}
        fullWidth
        style={{ marginBottom: spacing.md }}
      />

      {renderSection(
        apptsQ,
        { icon: 'calendar-outline', title: S.noAppointments },
        (items) => <View>{items.map(renderAppointment)}</View>,
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

      {/* ── Therapists (list pattern) ──────────────────────────────────────── */}
      <SectionTitle title={S.therapists} />
      {renderSection(
        therapistsQ,
        { icon: 'people-outline', title: S.noTherapists },
        (items) => (
          <ListGroup>
            {items.map((t, idx) => (
              <ListRow
                key={t.id}
                icon="person-outline"
                label={t.name}
                sublabel={[
                  t.specialties && t.specialties.length > 0
                    ? t.specialties.join(', ')
                    : undefined,
                  t.work_start && t.work_end
                    ? `${t.work_start} – ${t.work_end}`
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
    </ScrollView>
  );
}
