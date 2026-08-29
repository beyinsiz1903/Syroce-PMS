import React, { useMemo, useRef, useState } from 'react';
import { ScrollView, View } from 'react-native';
import { useRouter } from 'expo-router';
import { useMutation, useQuery, useQueryClient } from '@tanstack/react-query';

import { Badge, Body, Button, Card, EmptyState, Field, H1, H2, Muted, SkeletonCard, webCenter } from '../../src/components/ui';
import { DatePicker } from '../../src/components/DatePicker';
import { getAvailability, type AvailabilityRoom } from '../../src/api/availability';
import { createQuickBooking, type QuickBookingPayload } from '../../src/api/bookings';
import { ROUTES } from '../../src/navigation/routes';
import { spacing, useTheme } from '../../src/theme';
import { tr } from '../../src/i18n/tr';
import { addDaysISO } from '../../src/utils/reservationCalendar';
import { parsePaymentAmount } from '../../src/utils/paymentEntry';
import { errorMessage } from '../../src/utils/errors';
import { haptic } from '../../src/hooks/useHaptic';

function localTodayISO(): string {
  const now = new Date();
  const y = now.getFullYear();
  const m = String(now.getMonth() + 1).padStart(2, '0');
  const d = String(now.getDate()).padStart(2, '0');
  return `${y}-${m}-${d}`;
}

function reservationKey(): string {
  return `mobile-reservation-${Date.now().toString(36)}-${Math.random().toString(36).slice(2, 10)}`;
}

export default function NewReservationScreen() {
  const c = useTheme();
  const router = useRouter();
  const qc = useQueryClient();
  const today = localTodayISO();

  const [guestName, setGuestName] = useState('');
  const [checkIn, setCheckIn] = useState(today);
  const [checkOut, setCheckOut] = useState(addDaysISO(today, 1));
  const [room, setRoom] = useState<AvailabilityRoom | null>(null);
  const [amount, setAmount] = useState('');
  const [adults, setAdults] = useState('2');
  const [children, setChildren] = useState('0');
  const [formError, setFormError] = useState<string | null>(null);
  const [done, setDone] = useState(false);
  const attempt = useRef<{ fingerprint: string; key: string } | null>(null);

  const datesValid = !!checkIn && !!checkOut && checkOut > checkIn;
  const roomsQ = useQuery({
    queryKey: ['new-reservation-availability', checkIn, checkOut],
    queryFn: () => getAvailability(checkIn, checkOut),
    enabled: datesValid,
  });
  const availableRooms = useMemo(
    () =>
      (roomsQ.data ?? [])
        .filter((r) => r.available === true)
        .sort((a, b) =>
          String(a.room_number || a.id).localeCompare(String(b.room_number || b.id), 'tr', {
            numeric: true,
          }),
        ),
    [roomsQ.data],
  );

  const mutation = useMutation({
    mutationFn: async () => {
      const total = parsePaymentAmount(amount);
      const adultCount = Number(adults);
      const childCount = Number(children || '0');
      if (
        !guestName.trim() ||
        !datesValid ||
        !room ||
        total === null ||
        !Number.isInteger(adultCount) ||
        adultCount < 1 ||
        !Number.isInteger(childCount) ||
        childCount < 0
      ) {
        throw new Error(tr.reservations.invalidReservation);
      }
      const payload: QuickBookingPayload = {
        guest_name: guestName.trim(),
        room_id: room.id,
        check_in: `${checkIn}T14:00:00+03:00`,
        check_out: `${checkOut}T12:00:00+03:00`,
        total_amount: total,
        adults: adultCount,
        children: childCount,
      };
      const fingerprint = JSON.stringify(payload);
      if (!attempt.current || attempt.current.fingerprint !== fingerprint) {
        attempt.current = { fingerprint, key: reservationKey() };
      }
      return createQuickBooking(payload, attempt.current.key);
    },
    onSuccess: () => {
      haptic.success();
      setFormError(null);
      setDone(true);
      void qc.invalidateQueries({ queryKey: ['reservations-search'] });
      void qc.invalidateQueries({ queryKey: ['calendar'] });
      void qc.invalidateQueries({ queryKey: ['frontdesk-rooms'] });
    },
    onError: (e: unknown) => {
      haptic.error();
      setFormError(errorMessage(e, tr.reservations.actionError));
    },
  });

  if (done) {
    return (
      <View style={{ flex: 1, backgroundColor: c.bg }}>
        <View style={[{ flex: 1, padding: spacing.lg, justifyContent: 'center' }, webCenter]}>
          <EmptyState
            icon="checkmark-circle"
            title={tr.reservations.reservationCreated}
            message={tr.reservations.reservationCreatedHint}
            action={
              <View style={{ gap: spacing.sm }}>
                <Button
                  title={tr.calendar.title}
                  icon="calendar-outline"
                  onPress={() => router.replace(ROUTES.reservationCalendar)}
                />
                <Button
                  title={tr.reservations.title}
                  variant="secondary"
                  onPress={() => router.replace(ROUTES.reservations)}
                />
              </View>
            }
          />
        </View>
      </View>
    );
  }

  return (
    <ScrollView
      style={{ flex: 1, backgroundColor: c.bg }}
      contentContainerStyle={[{ padding: spacing.lg, gap: spacing.md, paddingBottom: spacing.xxl }, webCenter]}
    >
      <View>
        <H1>{tr.reservations.newReservation}</H1>
        <Muted style={{ marginTop: 2 }}>{tr.reservations.newReservationHint}</Muted>
      </View>

      {formError ? (
        <Card accent={c.danger}>
          <Body style={{ color: c.danger }}>{formError}</Body>
        </Card>
      ) : null}

      <Card>
        <Field
          label={tr.reservations.guestName}
          value={guestName}
          onChangeText={setGuestName}
          autoCapitalize="words"
        />
        <View style={{ height: spacing.sm }} />
        <View style={{ flexDirection: 'row', gap: spacing.sm }}>
          <Field
            style={{ flex: 1 }}
            label={tr.reservations.adults}
            value={adults}
            onChangeText={setAdults}
            keyboardType="number-pad"
          />
          <Field
            style={{ flex: 1 }}
            label={tr.reservations.children}
            value={children}
            onChangeText={setChildren}
            keyboardType="number-pad"
          />
        </View>
      </Card>

      <Card>
        <H2>{tr.reservations.selectDates}</H2>
        <View style={{ height: spacing.sm }} />
        <DatePicker
          mode="range"
          startValue={checkIn}
          endValue={checkOut}
          onRangeChange={(start, end) => {
            setCheckIn(start || '');
            setCheckOut(end || '');
            setRoom(null);
          }}
          minimumDate={today}
          testID="new-reservation-dates"
        />
      </Card>

      <Card>
        <H2>{tr.reservations.availableRooms}</H2>
        {roomsQ.isLoading ? (
          <View style={{ marginTop: spacing.sm }}><SkeletonCard /></View>
        ) : availableRooms.length === 0 ? (
          <Muted style={{ marginTop: spacing.sm }}>{tr.reservations.noAvailableRooms}</Muted>
        ) : (
          <View style={{ flexDirection: 'row', flexWrap: 'wrap', gap: spacing.sm, marginTop: spacing.sm }}>
            {availableRooms.map((candidate) => (
              <Button
                key={candidate.id}
                title={`${candidate.room_number || '—'}${candidate.room_type ? ` · ${candidate.room_type}` : ''}`}
                variant={room?.id === candidate.id ? 'primary' : 'secondary'}
                onPress={() => setRoom(candidate)}
              />
            ))}
          </View>
        )}
        {room ? (
          <View style={{ marginTop: spacing.md }}>
            <Badge label={`${tr.reservations.room} ${room.room_number || '—'}`} tone="success" icon="bed" />
          </View>
        ) : null}
      </Card>

      <Card>
        <Field
          label={tr.reservations.reservationAmount}
          value={amount}
          onChangeText={setAmount}
          keyboardType="decimal-pad"
        />
      </Card>

      <Button
        testID="new-reservation-submit"
        title={tr.reservations.createReservation}
        icon="calendar-outline"
        variant="success"
        loading={mutation.isPending}
        onPress={() => mutation.mutate()}
        fullWidth
      />
    </ScrollView>
  );
}
