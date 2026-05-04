import React, { useMemo, useState } from 'react';
import { Alert, ScrollView, View } from 'react-native';
import { useLocalSearchParams, useRouter } from 'expo-router';
import { useQuery } from '@tanstack/react-query';
import { Badge, Body, Button, Card, Field, H1, H2, Muted } from '../../src/components/ui';
import { spacing, useTheme } from '../../src/theme';
import { tr } from '../../src/i18n/tr';
import {
  EarlyLateCalcResponse,
  EarlyLateDirection,
  calculateEarlyLate,
  submitEarlyLateRequest,
} from '../../src/api/earlyLate';
import { getGuestBookings } from '../../src/api/guestBookings';
import { formatCurrency } from '../../src/utils/format';
import { errorMessage } from '../../src/utils/errors';
import { haptic } from '../../src/hooks/useHaptic';

export default function EarlyLateScreen() {
  const c = useTheme();
  const router = useRouter();
  const params = useLocalSearchParams<{ bookingId?: string }>();
  const bookingsQ = useQuery({ queryKey: ['guest-bookings'], queryFn: getGuestBookings });

  const booking = useMemo(() => {
    const all = [
      ...(bookingsQ.data?.active_bookings || []),
      ...(bookingsQ.data?.past_bookings || []),
    ];
    return params.bookingId ? all.find((b) => b.id === params.bookingId) : all[0];
  }, [bookingsQ.data, params.bookingId]);

  const [direction, setDirection] = useState<EarlyLateDirection>('early_checkin');
  const [hour, setHour] = useState('10');
  const [calc, setCalc] = useState<EarlyLateCalcResponse | null>(null);
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState<string | null>(null);

  const onCalc = async () => {
    if (!booking) return;
    const h = parseInt(hour, 10);
    if (Number.isNaN(h) || h < 0 || h > 23) {
      setError('Saat 0–23 aralığında olmalı');
      return;
    }
    setBusy(true);
    setError(null);
    try {
      const res = await calculateEarlyLate(booking.id, direction, h);
      setCalc(res);
      haptic.success();
    } catch (e) {
      setError(errorMessage(e, tr.errors.generic));
      haptic.error();
    } finally {
      setBusy(false);
    }
  };

  const onSubmit = async () => {
    if (!booking || !calc) return;
    setBusy(true);
    setError(null);
    try {
      await submitEarlyLateRequest(
        booking.id,
        direction,
        parseInt(hour, 10),
        calc.amount || 0,
        calc.currency || 'TRY',
      );
      haptic.success();
      Alert.alert(tr.app.success, tr.guest.requestSent, [
        { text: tr.app.close, onPress: () => router.back() },
      ]);
    } catch (e) {
      setError(errorMessage(e, tr.errors.generic));
      haptic.error();
    } finally {
      setBusy(false);
    }
  };

  return (
    <ScrollView
      style={{ flex: 1, backgroundColor: c.bg }}
      contentContainerStyle={{ padding: spacing.lg, gap: spacing.md, paddingBottom: spacing.xxl }}
    >
      <H1>{tr.guest.earlyLateTitle}</H1>
      {!booking ? (
        <Card>
          <Muted>{tr.guest.noBookings}</Muted>
        </Card>
      ) : (
        <Card>
          <H2>
            {booking.hotel?.property_name || 'Otel'} · Oda {booking.room?.room_number || 'TBA'}
          </H2>
          <Muted>Onay no: {booking.confirmation_number || '—'}</Muted>
        </Card>
      )}

      <Card>
        <View style={{ flexDirection: 'row', gap: spacing.sm }}>
          <Button
            title={tr.guest.earlyCheckin}
            variant={direction === 'early_checkin' ? 'primary' : 'secondary'}
            onPress={() => {
              setDirection('early_checkin');
              setCalc(null);
            }}
          />
          <Button
            title={tr.guest.lateCheckout}
            variant={direction === 'late_checkout' ? 'primary' : 'secondary'}
            onPress={() => {
              setDirection('late_checkout');
              setCalc(null);
            }}
          />
        </View>
        <View style={{ height: spacing.sm }} />
        <Field
          label={tr.guest.targetHour}
          value={hour}
          onChangeText={setHour}
          keyboardType="number-pad"
          maxLength={2}
        />
        <View style={{ height: spacing.sm }} />
        <Button title={tr.guest.calculate} onPress={onCalc} loading={busy} disabled={!booking} />
      </Card>

      {calc ? (
        <Card>
          {calc.applicable ? (
            <>
              <H2>{tr.guest.estimatedFee}</H2>
              <Body style={{ fontSize: 28, fontWeight: '700' }}>
                {formatCurrency(calc.amount, calc.currency)}
              </Body>
              {calc.label ? <Muted>{calc.label}</Muted> : null}
              <View style={{ height: spacing.sm }} />
              <Button title={tr.guest.requestSubmit} onPress={onSubmit} loading={busy} fullWidth />
            </>
          ) : (
            <View>
              <Badge label={tr.guest.noChargeForHour} tone="success" />
              <Muted style={{ marginTop: spacing.xs }}>{calc.reason || ''}</Muted>
              <View style={{ height: spacing.sm }} />
              <Button title={tr.guest.requestSubmit} onPress={onSubmit} loading={busy} fullWidth />
            </View>
          )}
        </Card>
      ) : null}

      {error ? <Body style={{ color: c.danger }}>{error}</Body> : null}
    </ScrollView>
  );
}
