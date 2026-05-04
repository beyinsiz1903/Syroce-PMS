import React, { useEffect, useMemo, useState } from 'react';
import { Alert, Pressable, ScrollView, Switch, View } from 'react-native';
import { useLocalSearchParams, useRouter } from 'expo-router';
import { useQuery } from '@tanstack/react-query';
import * as ImagePicker from 'expo-image-picker';
import * as FileSystem from 'expo-file-system';
// Reading EncodingType safely across SDK shapes
const FS_BASE64 = (FileSystem as { EncodingType?: { Base64?: string } }).EncodingType?.Base64 ?? 'base64';
import { Badge, Body, Button, Card, Field, H1, H2, Muted } from '../../src/components/ui';
import { spacing, useTheme } from '../../src/theme';
import { tr } from '../../src/i18n/tr';
import { haptic } from '../../src/hooks/useHaptic';
import { errorMessage } from '../../src/utils/errors';
import { GuestBooking, getGuestBookings } from '../../src/api/guestBookings';
import { submitOnlineCheckin } from '../../src/api/guestCheckin';
import { formatDate } from '../../src/utils/format';

function isCheckinOpen(booking: GuestBooking | null | undefined): boolean {
  if (!booking?.check_in) return false;
  try {
    const ci = new Date(booking.check_in);
    const opens = new Date(ci);
    opens.setHours(6, 0, 0, 0);
    const now = new Date();
    return now >= opens;
  } catch {
    return false;
  }
}

async function safeDeleteFile(uri: string | null | undefined) {
  if (!uri) return;
  try {
    await FileSystem.deleteAsync(uri, { idempotent: true });
  } catch {
    // best effort
  }
}

export default function OnlineCheckinScreen() {
  const c = useTheme();
  const router = useRouter();
  const params = useLocalSearchParams<{ bookingId?: string }>();
  const q = useQuery({ queryKey: ['guest-bookings'], queryFn: getGuestBookings });

  const [bookingId, setBookingId] = useState<string | null>(params.bookingId ?? null);
  const [photoUri, setPhotoUri] = useState<string | null>(null);
  const [signatureName, setSignatureName] = useState('');
  const [signatureConsent, setSignatureConsent] = useState(false);
  const [arrivalTime, setArrivalTime] = useState('');
  const [flightNumber, setFlightNumber] = useState('');
  const [nationality, setNationality] = useState('');
  const [passport, setPassport] = useState('');
  const [specialRequests, setSpecialRequests] = useState('');
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const [done, setDone] = useState(false);

  const eligibleBookings = useMemo(
    () => (q.data?.active_bookings || []).filter((b) => b.status !== 'checked_in'),
    [q.data],
  );
  const booking = useMemo(
    () => eligibleBookings.find((b) => b.id === bookingId) || null,
    [eligibleBookings, bookingId],
  );
  const checkinOpen = isCheckinOpen(booking);

  useEffect(() => {
    if (!bookingId && eligibleBookings.length === 1) {
      setBookingId(eligibleBookings[0].id);
    }
  }, [eligibleBookings, bookingId]);

  const takePhoto = async () => {
    setError(null);
    try {
      const perm = await ImagePicker.requestCameraPermissionsAsync();
      if (!perm.granted) {
        setError(tr.errors.permissionCamera);
        return;
      }
      const result = await ImagePicker.launchCameraAsync({
        mediaTypes: ImagePicker.MediaTypeOptions.Images,
        quality: 0.6,
      });
      if (result.canceled) return;
      setPhotoUri(result.assets[0].uri);
      haptic.success();
    } catch (e) {
      setError(errorMessage(e, tr.errors.generic));
    }
  };

  const onSubmit = async () => {
    if (!booking) {
      setError(tr.guest.onlineCheckinNoBooking);
      return;
    }
    if (!checkinOpen) {
      setError(tr.guest.onlineCheckinOpensAt);
      return;
    }
    if (!photoUri) {
      setError(tr.guest.idPhotoTake);
      return;
    }
    if (!signatureConsent || signatureName.trim().length < 3) {
      setError(tr.guest.signatureHint);
      return;
    }
    setBusy(true);
    setError(null);
    try {
      // Encode the local ID photo as base64 so it actually reaches the server.
      let idPhotoBase64: string | undefined;
      try {
        idPhotoBase64 = await FileSystem.readAsStringAsync(photoUri, {
          encoding: FS_BASE64 as FileSystem.EncodingType,
        });
      } catch {
        // If the encoding helper fails, fail fast — the photo MUST land on the server.
        throw new Error('Kimlik fotoğrafı okunamadı, lütfen yeniden çekin');
      }

      await submitOnlineCheckin({
        booking_id: booking.id,
        passport_number: passport || undefined,
        nationality: nationality || undefined,
        estimated_arrival_time: arrivalTime || undefined,
        flight_number: flightNumber || undefined,
        special_requests: specialRequests || undefined,
        id_photo_base64: idPhotoBase64,
        signature_text: signatureName.trim(),
        signature_consent: true,
      });
      // Success: wipe the local raw photo per privacy requirement
      await safeDeleteFile(photoUri);
      setPhotoUri(null);
      setDone(true);
      haptic.success();
      Alert.alert(tr.app.success, tr.guest.onlineCheckinCompleted);
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
      <H1>{tr.guest.onlineCheckinTitle}</H1>

      <Card>
        <H2>{tr.guest.pickBooking}</H2>
        {q.isLoading ? (
          <Muted>{tr.app.loading}</Muted>
        ) : eligibleBookings.length === 0 ? (
          <Muted>{tr.guest.onlineCheckinNoBooking}</Muted>
        ) : (
          eligibleBookings.map((b) => (
            <Pressable
              key={b.id}
              onPress={() => setBookingId(b.id)}
              accessibilityRole="button"
              style={{
                borderWidth: 1,
                borderColor: bookingId === b.id ? c.primary : c.border,
                borderRadius: 10,
                padding: spacing.md,
                marginTop: spacing.sm,
                backgroundColor: bookingId === b.id ? c.primary + '11' : 'transparent',
              }}
            >
              <Body style={{ fontWeight: '600' }}>
                {b.hotel?.property_name || 'Otel'} · Oda {b.room?.room_number || 'TBA'}
              </Body>
              <Muted>
                {formatDate(b.check_in)} → {formatDate(b.check_out)}
              </Muted>
            </Pressable>
          ))
        )}
        {booking ? (
          <View style={{ marginTop: spacing.sm }}>
            {checkinOpen ? (
              <Badge label="Online check-in açık" tone="success" />
            ) : (
              <Badge label={tr.guest.onlineCheckinUnavailable} tone="warning" />
            )}
            {!checkinOpen ? <Muted>{tr.guest.onlineCheckinOpensAt}</Muted> : null}
          </View>
        ) : null}
      </Card>

      <Card>
        <H2>Misafir bilgileri</H2>
        <Field
          label={tr.guest.passport}
          value={passport}
          onChangeText={setPassport}
          autoCapitalize="characters"
        />
        <View style={{ height: spacing.sm }} />
        <Field label={tr.guest.nationality} value={nationality} onChangeText={setNationality} />
        <View style={{ height: spacing.sm }} />
        <Field
          label={tr.guest.arrivalTime}
          value={arrivalTime}
          onChangeText={setArrivalTime}
          keyboardType="numbers-and-punctuation"
          placeholder="14:30"
        />
        <View style={{ height: spacing.sm }} />
        <Field label={tr.guest.flightNumber} value={flightNumber} onChangeText={setFlightNumber} />
        <View style={{ height: spacing.sm }} />
        <Field
          label={tr.guest.specialRequests}
          value={specialRequests}
          onChangeText={setSpecialRequests}
          multiline
          numberOfLines={3}
        />
      </Card>

      <Card>
        <H2>{tr.guest.idPhoto}</H2>
        {photoUri ? (
          <>
            <Body style={{ color: c.success, marginTop: spacing.xs }}>{tr.guest.idPhotoTaken}</Body>
            <View style={{ height: spacing.sm }} />
            <Button title={tr.guest.idPhotoRetake} variant="secondary" onPress={takePhoto} />
          </>
        ) : (
          <>
            <Muted>Pasaport veya kimlik fotoğrafınızı çekin.</Muted>
            <View style={{ height: spacing.sm }} />
            <Button title={tr.guest.idPhotoTake} onPress={takePhoto} />
          </>
        )}
      </Card>

      <Card>
        <H2>{tr.guest.signature}</H2>
        <Muted>{tr.guest.signatureHint}</Muted>
        <View style={{ height: spacing.sm }} />
        <Field
          label={tr.guest.signatureName}
          value={signatureName}
          onChangeText={setSignatureName}
          autoCapitalize="words"
        />
        <View
          style={{
            flexDirection: 'row',
            alignItems: 'center',
            gap: spacing.sm,
            marginTop: spacing.sm,
          }}
        >
          <Switch
            value={signatureConsent}
            onValueChange={setSignatureConsent}
            accessibilityLabel={tr.guest.signatureConsent}
          />
          <Body style={{ flex: 1 }}>{tr.guest.signatureConsent}</Body>
        </View>
      </Card>

      {error ? <Body style={{ color: c.danger }}>{error}</Body> : null}
      {done ? <Body style={{ color: c.success }}>{tr.guest.onlineCheckinCompleted}</Body> : null}

      <Button
        title={tr.guest.submitCheckin}
        onPress={onSubmit}
        loading={busy}
        disabled={!booking || !checkinOpen}
        fullWidth
      />
      {done ? (
        <Button
          title={tr.app.close}
          variant="secondary"
          onPress={() => router.back()}
          fullWidth
        />
      ) : null}
    </ScrollView>
  );
}
