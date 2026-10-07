import React, { useEffect, useMemo, useRef, useState } from 'react';
import { ActivityIndicator, ScrollView, View } from 'react-native';
import { useLocalSearchParams, useRouter } from 'expo-router';
import { CameraView, useCameraPermissions, type BarcodeScanningResult } from 'expo-camera';
import * as ImagePicker from 'expo-image-picker';

import { Badge, Body, Button, Card, EmptyState, Field, H1, H2, Muted, webCenter } from '../../src/components/ui';
import { addReservationGuest, getInHouse, getTodayArrivals, searchBookingByRoom, type Booking } from '../../src/api/bookings';
import { scanIdPhoto, type QuickIdResult } from '../../src/api/quickid';
import { haptic } from '../../src/hooks/useHaptic';
import { tr } from '../../src/i18n/tr';
import { ROUTES } from '../../src/navigation/routes';
import { spacing, useTheme } from '../../src/theme';
import { captureAndScanIdentity } from '../../src/utils/checkinCapture';
import { errorMessage } from '../../src/utils/errors';

type Step = 'scan' | 'capture' | 'parsed';
type Destination = 'existing' | null;

function guestName(identity: QuickIdResult | null): string {
  return identity?.full_name || [identity?.first_name, identity?.last_name].filter(Boolean).join(' ').trim();
}

function identityNumber(identity: QuickIdResult | null): string {
  return identity?.id_number || identity?.passport_number || '';
}

function mergeReservations(...groups: Booking[][]): Booking[] {
  const unique = new Map<string, Booking>();
  groups.flat().forEach((booking) => {
    if (booking?.id) unique.set(booking.id, booking);
  });
  return Array.from(unique.values());
}

export default function CheckinScreen() {
  const c = useTheme();
  const router = useRouter();
  const params = useLocalSearchParams<{ bookingId?: string }>();
  const [permission, requestPermission] = useCameraPermissions();
  const scannedRef = useRef(false);
  const [step, setStep] = useState<Step>('scan');
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const [done, setDone] = useState(false);
  const [parsed, setParsed] = useState<QuickIdResult | null>(null);
  const [destination, setDestination] = useState<Destination>(null);
  const [suggestedBookingId, setSuggestedBookingId] = useState<string | null>(params.bookingId ?? null);
  const [reservations, setReservations] = useState<Booking[]>([]);
  const [reservationsLoading, setReservationsLoading] = useState(false);
  const [reservationsError, setReservationsError] = useState(false);
  const [reservationSearch, setReservationSearch] = useState('');
  const [selectedBookingId, setSelectedBookingId] = useState<string | null>(null);

  useEffect(() => {
    if (!permission) requestPermission();
  }, [permission, requestPermission]);

  useEffect(() => {
    if (destination !== 'existing') return;
    let active = true;
    setReservationsLoading(true);
    setReservationsError(false);
    Promise.all([getTodayArrivals(), getInHouse()])
      .then(([arrivals, inHouse]) => {
        if (!active) return;
        const merged = mergeReservations(arrivals, inHouse).sort((a, b) => {
          if (a.id === suggestedBookingId) return -1;
          if (b.id === suggestedBookingId) return 1;
          return String(a.room_number || '').localeCompare(String(b.room_number || ''), 'tr', { numeric: true });
        });
        setReservations(merged);
      })
      .catch(() => {
        if (active) setReservationsError(true);
      })
      .finally(() => {
        if (active) setReservationsLoading(false);
      });
    return () => {
      active = false;
    };
  }, [destination, suggestedBookingId]);

  const filteredReservations = useMemo(() => {
    const needle = reservationSearch.trim().toLocaleLowerCase('tr-TR');
    if (!needle) return reservations;
    return reservations.filter((booking) =>
      [booking.guest_name, booking.room_number, booking.id]
        .filter(Boolean)
        .some((value) => String(value).toLocaleLowerCase('tr-TR').includes(needle)),
    );
  }, [reservationSearch, reservations]);

  const selectedBooking = reservations.find((booking) => booking.id === selectedBookingId) || null;

  const startPhotoCapture = () => {
    if (busy || step === 'capture') return;
    // CameraView must unmount before UIImagePicker opens or iOS can remain on
    // the camera after the operator taps "Use Photo".
    scannedRef.current = true;
    setError(null);
    setDestination(null);
    setSelectedBookingId(null);
    setStep('capture');
  };

  const onBarcodeScanned = async ({ data }: BarcodeScanningResult) => {
    if (scannedRef.current) return;
    scannedRef.current = true;
    haptic.tap();
    const trimmed = (data || '').trim();
    if (trimmed.startsWith('booking:')) {
      setSuggestedBookingId(trimmed.split(':')[1] || null);
    } else if (/^\d{1,4}$/.test(trimmed)) {
      try {
        const list = await searchBookingByRoom(trimmed);
        setSuggestedBookingId(list[0]?.id || null);
      } catch {
        setSuggestedBookingId(null);
      }
    } else if (trimmed) {
      setSuggestedBookingId(trimmed);
    }
    startPhotoCapture();
  };

  useEffect(() => {
    if (step !== 'capture') return;
    let active = true;
    setBusy(true);
    void captureAndScanIdentity({
      launchCamera: () => ImagePicker.launchCameraAsync({ mediaTypes: ['images'], quality: 0.7, base64: false }),
      scanPhoto: scanIdPhoto,
    })
      .then((result) => {
        if (!active) return;
        if (result.status === 'cancelled') {
          scannedRef.current = false;
          setStep('scan');
          return;
        }
        if (result.status === 'failed') {
          const message = errorMessage(result.error, tr.checkin.scanFailed);
          setError(message === 'NETWORK' ? tr.checkin.scanFailed : message);
          scannedRef.current = false;
          setStep('scan');
          haptic.error();
          return;
        }
        setParsed(result.data);
        setStep('parsed');
        haptic.success();
      })
      .finally(() => {
        if (active) setBusy(false);
      });
    return () => {
      active = false;
    };
  }, [step]);

  const openNewReservation = () => {
    if (!parsed) return;
    router.push({
      pathname: ROUTES.newReservation,
      params: { guest_name: guestName(parsed), guest_id_number: identityNumber(parsed) },
    });
  };

  const addToReservation = async () => {
    if (!parsed || !selectedBookingId) {
      setError(tr.checkin.selectReservationRequired);
      haptic.warning();
      return;
    }
    const name = guestName(parsed);
    if (!name) {
      setError(tr.checkin.guestNameRequired);
      haptic.warning();
      return;
    }
    setBusy(true);
    setError(null);
    try {
      await addReservationGuest(selectedBookingId, {
        name,
        id_type: parsed.passport_number || String(parsed.document_type || '').toLowerCase().includes('pass') ? 'passport' : 'tc_kimlik',
        id_number: identityNumber(parsed),
        nationality: parsed.nationality || 'TR',
        date_of_birth: parsed.birth_date || '',
      });
      setDone(true);
      haptic.success();
    } catch (e: unknown) {
      setError(errorMessage(e, tr.errors.generic));
      haptic.error();
    } finally {
      setBusy(false);
    }
  };

  if (done) {
    return (
      <View style={{ flex: 1, backgroundColor: c.bg }}>
        <View style={[{ flex: 1, padding: spacing.lg, justifyContent: 'center' }, webCenter]}>
          <EmptyState
            icon="person-add-outline"
            title={tr.checkin.guestAdded}
            message={tr.checkin.guestAddedHint}
            action={<Button title={tr.checkin.done} icon="arrow-back" onPress={() => router.back()} />}
          />
        </View>
      </View>
    );
  }

  if (step === 'scan' && permission?.granted) {
    return (
      <View style={{ flex: 1, backgroundColor: c.bg }}>
        <CameraView
          style={{ flex: 1 }}
          facing="back"
          barcodeScannerSettings={{ barcodeTypes: ['qr', 'ean13', 'code128', 'pdf417'] }}
          onBarcodeScanned={onBarcodeScanned}
        />
        <View style={{ padding: spacing.lg, gap: spacing.sm, backgroundColor: c.surface }}>
          {error ? <Card accent={c.danger}><Body style={{ color: c.danger }}>{error}</Body></Card> : null}
          <Muted>{tr.checkin.scan}</Muted>
          <Button title={tr.checkin.photo} icon="camera" onPress={startPhotoCapture} loading={busy} fullWidth />
        </View>
      </View>
    );
  }

  if (step === 'capture') {
    return (
      <View style={{ flex: 1, backgroundColor: c.bg }}>
        <View style={[{ flex: 1, padding: spacing.lg, alignItems: 'center', justifyContent: 'center', gap: spacing.md }, webCenter]}>
          <ActivityIndicator size="large" color={c.primary} />
          <H2>{tr.checkin.parsing}</H2>
          <Muted style={{ textAlign: 'center' }}>{tr.checkin.parsingHint}</Muted>
        </View>
      </View>
    );
  }

  if (step === 'scan' && !permission?.granted) {
    return (
      <View style={{ flex: 1, backgroundColor: c.bg }}>
        <View style={[{ flex: 1, padding: spacing.lg, gap: spacing.md }, webCenter]}>
          <H1>{tr.checkin.title}</H1>
          <Card accent={c.warning}><Muted>{tr.errors.permissionCamera}</Muted></Card>
          <Button title={tr.app.retry} icon="refresh" onPress={() => requestPermission()} fullWidth />
          <Button title={tr.checkin.photo} icon="camera" variant="secondary" onPress={startPhotoCapture} loading={busy} fullWidth />
        </View>
      </View>
    );
  }

  return (
    <ScrollView
      style={{ flex: 1, backgroundColor: c.bg }}
      contentContainerStyle={[{ padding: spacing.lg, gap: spacing.md, flexGrow: 1, paddingBottom: spacing.xxl }, webCenter]}
    >
      <H1>{tr.checkin.title}</H1>
      {error ? <Card accent={c.danger}><Body style={{ color: c.danger }}>{error}</Body></Card> : null}

      <Card>
        <H2>{tr.checkin.guest}</H2>
        <View style={{ height: spacing.sm }} />
        <Field label={tr.checkin.firstName} value={parsed?.first_name || ''} onChangeText={(value) => setParsed((current) => ({ ...(current || {}), first_name: value, full_name: '' }))} />
        <View style={{ height: spacing.sm }} />
        <Field label={tr.checkin.lastName} value={parsed?.last_name || ''} onChangeText={(value) => setParsed((current) => ({ ...(current || {}), last_name: value, full_name: '' }))} />
        <View style={{ height: spacing.sm }} />
        <Field label={tr.checkin.idOrPassport} value={identityNumber(parsed)} onChangeText={(value) => setParsed((current) => ({ ...(current || {}), id_number: value }))} />
        {parsed?.nationality ? <View style={{ marginTop: spacing.sm }}><Badge label={parsed.nationality} tone="info" /></View> : null}
      </Card>

      {!destination ? (
        <Card accent={c.info}>
          <H2>{tr.checkin.chooseDestination}</H2>
          <Muted style={{ marginTop: spacing.xs }}>{tr.checkin.chooseDestinationHint}</Muted>
          <View style={{ height: spacing.md }} />
          <Button title={tr.checkin.addExisting} icon="person-add-outline" onPress={() => setDestination('existing')} fullWidth />
          <View style={{ height: spacing.sm }} />
          <Button title={tr.checkin.createNewReservation} icon="calendar-outline" variant="secondary" onPress={openNewReservation} fullWidth />
          <View style={{ height: spacing.sm }} />
          <Muted style={{ textAlign: 'center' }}>{tr.checkin.noAutomaticCheckin}</Muted>
        </Card>
      ) : null}

      {destination === 'existing' ? (
        <Card>
          <H2>{tr.checkin.selectReservation}</H2>
          <Muted style={{ marginTop: spacing.xs }}>{tr.checkin.selectReservationHint}</Muted>
          <View style={{ height: spacing.sm }} />
          <Field placeholder={tr.checkin.searchReservation} value={reservationSearch} onChangeText={setReservationSearch} autoCapitalize="words" />
          <View style={{ height: spacing.md }} />
          {reservationsLoading ? <ActivityIndicator color={c.primary} /> : null}
          {reservationsError ? <Muted style={{ color: c.danger }}>{tr.checkin.reservationLoadError}</Muted> : null}
          {!reservationsLoading && !reservationsError && filteredReservations.length === 0 ? <Muted>{tr.checkin.noActiveReservations}</Muted> : null}
          {filteredReservations.map((booking) => (
            <View key={booking.id} style={{ marginBottom: spacing.sm }}>
              <Button
                title={`${booking.room_number ? `${tr.today.room} ${booking.room_number} · ` : ''}${booking.guest_name || tr.checkin.unnamedReservation}`}
                icon="bed-outline"
                variant={selectedBookingId === booking.id ? 'primary' : 'secondary'}
                onPress={() => setSelectedBookingId(booking.id)}
                fullWidth
              />
              {booking.id === suggestedBookingId ? <Muted style={{ marginTop: 2 }}>{tr.checkin.suggestedReservation}</Muted> : null}
            </View>
          ))}
          <Button title={tr.checkin.changeChoice} variant="outline" onPress={() => { setDestination(null); setSelectedBookingId(null); }} fullWidth />
        </Card>
      ) : null}

      {destination === 'existing' && selectedBooking ? (
        <Card accent={c.success}>
          <H2>{tr.checkin.confirmSelection}</H2>
          <Body style={{ marginTop: spacing.xs }}>{selectedBooking.guest_name || tr.checkin.unnamedReservation}</Body>
          <Muted>{selectedBooking.room_number ? `${tr.today.room} ${selectedBooking.room_number}` : tr.checkin.roomNotAssigned}</Muted>
          <View style={{ height: spacing.md }} />
          <Button title={tr.checkin.addGuestOnly} icon="person-add-outline" variant="success" onPress={addToReservation} loading={busy} fullWidth />
          <Muted style={{ textAlign: 'center', marginTop: spacing.sm }}>{tr.checkin.noStatusChange}</Muted>
        </Card>
      ) : null}
    </ScrollView>
  );
}
