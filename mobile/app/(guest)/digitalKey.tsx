import React, { useEffect, useMemo, useRef } from 'react';
import { ActivityIndicator, ScrollView, View } from 'react-native';
import { useLocalSearchParams } from 'expo-router';
import { useQuery } from '@tanstack/react-query';
import * as Brightness from 'expo-brightness';
import { useKeepAwake } from 'expo-keep-awake';
import QRCode from 'react-native-qrcode-svg';
import { Body, Card, H1, H2, Muted } from '../../src/components/ui';
import { spacing, useTheme } from '../../src/theme';
import { tr } from '../../src/i18n/tr';
import { getGuestBookings, GuestBooking } from '../../src/api/guestBookings';
import { formatDate, formatTime } from '../../src/utils/format';

/**
 * Misafir Dijital Anahtar / QR ekranı (V3).
 *
 * V3 acceptance: "Resepsiyon kapısı + oda kapısı QR" — TWO scoped QR
 * codes shown on the same screen so the same booking grants:
 *   1. resepsiyon (lobi) erişimi — varışta self-service kiosk.
 *   2. oda kapısı erişimi — odada okuyucuda.
 *
 * Implementation notes:
 *   - The backend delivers a single time-based token (`booking.qr_code_data`,
 *     produced by `core.security.generate_time_based_qr_token`, 72 saat
 *     geçerli). We bind it to two distinct scopes by appending `scope`:
 *     "reception" | "room". The kapı tarayıcısı, payload'daki `scope`
 *     alanını okur ve uygun açma akışını (resepsiyon vs oda) tetikler.
 *     Backend tarafı tek tokenı her iki scope için de kabul eder; hangi
 *     fiziksel kapıyı açacağına `scope` karar verir.
 *   - Ekran ön plandayken parlaklık %100'e çıkar. Bunun amacı QR'in kapı
 *     tarayıcısı tarafından temiz okunabilmesi. Çıkışta orijinal parlaklığa
 *     dönülür.
 *   - useKeepAwake() ekranın uyumasını engeller — kullanıcı QR'i göstermek
 *     için biraz beklerse ekran kilitlenmesin.
 */
export default function GuestDigitalKey() {
  const c = useTheme();
  useKeepAwake();
  const { id } = useLocalSearchParams<{ id?: string }>();
  // V3 (round 7): track previous brightness via a ref instead of state.
  // The cleanup callback in our mount-only `useEffect([])` would otherwise
  // close over the *initial* `null` value and never restore the user's
  // brightness on unmount — leaving the device stuck at 100%.
  const previousBrightnessRef = useRef<number | null>(null);

  const q = useQuery({ queryKey: ['guest-bookings'], queryFn: getGuestBookings });

  const booking: GuestBooking | null = useMemo(() => {
    const all = [...(q.data?.active_bookings || []), ...(q.data?.past_bookings || [])];
    if (id) return all.find((b) => b.id === id) || null;
    return q.data?.active_bookings?.[0] || null;
  }, [q.data, id]);

  useEffect(() => {
    let cancelled = false;
    (async () => {
      try {
        const perms = await Brightness.requestPermissionsAsync();
        if (!perms.granted) return;
        const current = await Brightness.getBrightnessAsync();
        if (cancelled) return;
        previousBrightnessRef.current = current;
        await Brightness.setBrightnessAsync(1);
      } catch {
        // Brightness API not supported on this platform — ignore.
      }
    })();
    return () => {
      cancelled = true;
      const prev = previousBrightnessRef.current;
      if (prev != null) {
        // Fire-and-forget; we cannot await inside a cleanup function.
        Brightness.setBrightnessAsync(prev).catch(() => {
          // best-effort
        });
      }
    };
  }, []);

  // Build a scope-scoped QR payload. We always wrap into a JSON envelope
  // so kapı tarayıcısı `scope` alanını okuyup doğru kapıyı açabilsin.
  // When the backend has issued a signed token we embed it as `token`;
  // legacy bookings without a token fall back to the booking id +
  // confirmation pair (the kiosk still validates server-side).
  function buildPayload(scope: 'reception' | 'room'): string {
    if (!booking) return '';
    const base: Record<string, unknown> = {
      v: 1,
      scope,
      booking_id: booking.id,
      confirmation: booking.confirmation_number,
    };
    if (booking.qr_code_data) base.token = String(booking.qr_code_data);
    if (booking.room?.room_number) base.room = booking.room.room_number;
    return JSON.stringify(base);
  }

  const receptionPayload = useMemo(() => buildPayload('reception'), [booking]);
  const roomPayload = useMemo(() => buildPayload('room'), [booking]);

  if (q.isLoading) {
    return (
      <View
        style={{
          flex: 1,
          backgroundColor: c.bg,
          alignItems: 'center',
          justifyContent: 'center',
        }}
      >
        <ActivityIndicator color={c.primary} />
      </View>
    );
  }

  if (!booking) {
    return (
      <View style={{ flex: 1, backgroundColor: c.bg, padding: spacing.lg, gap: spacing.md }}>
        <H1>{tr.guest.digitalKeyTitle}</H1>
        <Muted>{tr.guest.digitalKeyNoBooking}</Muted>
      </View>
    );
  }

  // The room QR is only meaningful once a physical room has been
  // assigned. Before assignment we still show the reception QR so the
  // guest can complete check-in at the lobby kiosk.
  const hasRoom = !!booking.room?.room_number;

  return (
    <ScrollView
      contentContainerStyle={{
        padding: spacing.lg,
        gap: spacing.lg,
        backgroundColor: c.bg,
        alignItems: 'center',
      }}
    >
      <View style={{ alignSelf: 'stretch' }}>
        <H1>{tr.guest.digitalKeyTitle}</H1>
        <Muted>{tr.guest.digitalKeyHint}</Muted>
      </View>

      {/* Reception QR — works as soon as the booking is confirmed. */}
      <Card
        style={{
          alignItems: 'center',
          gap: spacing.md,
          padding: spacing.lg,
          alignSelf: 'stretch',
        }}
      >
        <H2>{tr.guest.digitalKeyReceptionTitle}</H2>
        <Muted style={{ textAlign: 'center' }}>{tr.guest.digitalKeyReceptionHint}</Muted>
        {receptionPayload ? (
          <View style={{ backgroundColor: '#ffffff', padding: spacing.lg, borderRadius: 12 }}>
            <QRCode
              value={receptionPayload}
              size={220}
              ecl="H"
              backgroundColor="#ffffff"
              color="#000000"
            />
          </View>
        ) : (
          <Muted>{tr.guest.digitalKeyUnavailable}</Muted>
        )}
        <Body style={{ textAlign: 'center' }}>
          {tr.guest.confirmation}: {booking.confirmation_number || '—'}
        </Body>
      </Card>

      {/* Room QR — only meaningful once a room has been assigned. */}
      <Card
        style={{
          alignItems: 'center',
          gap: spacing.md,
          padding: spacing.lg,
          alignSelf: 'stretch',
        }}
      >
        <H2>{tr.guest.digitalKeyRoomTitle}</H2>
        <Muted style={{ textAlign: 'center' }}>{tr.guest.digitalKeyRoomHint}</Muted>
        {hasRoom && roomPayload ? (
          <View style={{ backgroundColor: '#ffffff', padding: spacing.lg, borderRadius: 12 }}>
            <QRCode
              value={roomPayload}
              size={220}
              ecl="H"
              backgroundColor="#ffffff"
              color="#000000"
            />
          </View>
        ) : (
          <Muted>{tr.guest.digitalKeyUnavailable}</Muted>
        )}
        <Body style={{ textAlign: 'center' }}>
          {booking.hotel?.property_name || ''} · Oda {booking.room?.room_number || 'TBA'}
        </Body>
        <Muted style={{ textAlign: 'center' }}>
          {formatDate(booking.check_in)} {formatTime(booking.check_in)} →{' '}
          {formatDate(booking.check_out)} {formatTime(booking.check_out)}
        </Muted>
      </Card>

      <Card style={{ alignSelf: 'stretch' }}>
        <H2>{tr.guest.digitalKeyHowTo}</H2>
        <Body style={{ marginTop: spacing.xs }}>{tr.guest.digitalKeyStep1}</Body>
        <Body>{tr.guest.digitalKeyStep2}</Body>
        <Body>{tr.guest.digitalKeyStep3}</Body>
      </Card>
    </ScrollView>
  );
}
