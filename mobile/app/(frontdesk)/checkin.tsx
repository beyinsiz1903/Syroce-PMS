import React, { useEffect, useRef, useState } from 'react';
import { ScrollView, View } from 'react-native';
import { useLocalSearchParams, useRouter } from 'expo-router';
import {
  CameraView,
  useCameraPermissions,
  type BarcodeScanningResult,
} from 'expo-camera';
import * as ImagePicker from 'expo-image-picker';
import {
  Badge,
  Body,
  Button,
  Card,
  EmptyState,
  Field,
  H1,
  H2,
  Muted,
  webCenter,
} from '../../src/components/ui';
import { spacing, useTheme } from '../../src/theme';
import { tr } from '../../src/i18n/tr';
import { haptic } from '../../src/hooks/useHaptic';
import { scanIdPhoto, QuickIdResult } from '../../src/api/quickid';
import { createGuest } from '../../src/api/guests';
import { listRooms, Room } from '../../src/api/rooms';
import {
  assignRoom,
  checkin,
  searchBookingByRoom,
  walkInQuick,
} from '../../src/api/bookings';
import { errorMessage } from '../../src/utils/errors';

type Step = 'scan' | 'parsed';

const AVAILABLE_STATUSES = ['available', 'clean', 'inspected'];

export default function CheckinScreen() {
  const c = useTheme();
  const router = useRouter();
  const params = useLocalSearchParams<{ bookingId?: string }>();
  const [step, setStep] = useState<Step>('scan');
  const [permission, requestPermission] = useCameraPermissions();
  const scannedRef = useRef(false);
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const [done, setDone] = useState(false);
  const [parsed, setParsed] = useState<QuickIdResult | null>(null);
  const [bookingId, setBookingId] = useState<string | null>(params.bookingId ?? null);
  const [rooms, setRooms] = useState<Room[]>([]);
  const [roomsError, setRoomsError] = useState(false);
  const [selectedRoom, setSelectedRoom] = useState<Room | null>(null);

  useEffect(() => {
    if (!permission) requestPermission();
  }, [permission, requestPermission]);

  useEffect(() => {
    let cancelled = false;
    setRoomsError(false);
    listRooms()
      .then((rs) => {
        if (!cancelled) {
          setRooms(rs.filter((r) => AVAILABLE_STATUSES.includes((r.status || '').toLowerCase())));
        }
      })
      .catch(() => {
        // Surface the failure in the room picker instead of showing an empty
        // list that looks like "no rooms available".
        if (!cancelled) setRoomsError(true);
      });
    return () => {
      cancelled = true;
    };
  }, []);

  const onBarcodeScanned = async ({ data }: BarcodeScanningResult) => {
    if (scannedRef.current) return;
    scannedRef.current = true;
    haptic.tap();
    const trimmed = (data || '').trim();
    if (trimmed.startsWith('booking:')) {
      setBookingId(trimmed.split(':')[1] || null);
    } else if (/^\d{1,4}$/.test(trimmed)) {
      try {
        const list = await searchBookingByRoom(trimmed);
        if (list.length) setBookingId(list[0].id);
      } catch {
        // Best-effort room->booking lookup; continue to the ID scan even if it
        // fails so a lookup error never aborts the scan flow.
      }
    } else {
      setBookingId(trimmed);
    }
    await pickAndScanId();
  };

  const pickAndScanId = async () => {
    setBusy(true);
    setError(null);
    try {
      const result = await ImagePicker.launchCameraAsync({
        mediaTypes: ImagePicker.MediaTypeOptions.Images,
        quality: 0.7,
        base64: false,
      });
      if (result.canceled) {
        scannedRef.current = false;
        setBusy(false);
        return;
      }
      const uri = result.assets[0].uri;
      const data = await scanIdPhoto(uri);
      setParsed(data);
      setStep('parsed');
      haptic.success();
    } catch (e: unknown) {
      setError(errorMessage(e, tr.errors.generic));
      haptic.error();
      scannedRef.current = false;
    } finally {
      setBusy(false);
    }
  };

  const onConfirm = async () => {
    if (!parsed) return;
    if (!bookingId && !selectedRoom) {
      setError(tr.checkin.needRoom);
      haptic.warning();
      return;
    }
    setBusy(true);
    setError(null);
    try {
      const guest = await createGuest({
        first_name: parsed.first_name,
        last_name: parsed.last_name,
        id_number: parsed.id_number,
        passport_number: parsed.passport_number,
        nationality: parsed.nationality,
        birth_date: parsed.birth_date,
      });

      if (bookingId) {
        // Assign chosen room (if any) before checking in
        if (selectedRoom) {
          try {
            await assignRoom(bookingId, selectedRoom.id);
          } catch {
            // assignment may not be required if booking has a room already
          }
        }
        await checkin(bookingId);
      } else if (selectedRoom) {
        const guestName =
          parsed.full_name ||
          [parsed.first_name, parsed.last_name].filter(Boolean).join(' ') ||
          guest.full_name ||
          'Walk-in';
        await walkInQuick({
          guest_name: guestName,
          room_id: selectedRoom.id,
          nights: 1,
          rate_amount: 0,
          payment_method: 'cash',
          id_number: parsed.id_number || parsed.passport_number,
        });
      }

      haptic.success();
      // Inline success state (NOT Alert.alert — a no-op on Expo Web, which left
      // check-in silently broken there). The operator taps "Bitti" to return.
      setDone(true);
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
            icon="checkmark-circle"
            title={tr.checkin.success}
            message={tr.checkin.successHint}
            action={
              <Button title={tr.checkin.done} icon="arrow-back" onPress={() => router.back()} />
            }
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
          <Muted>{tr.checkin.scan}</Muted>
          <Button title={tr.checkin.photo} icon="camera" onPress={pickAndScanId} loading={busy} fullWidth />
        </View>
      </View>
    );
  }

  if (step === 'scan' && !permission?.granted) {
    return (
      <View style={{ flex: 1, backgroundColor: c.bg }}>
        <View style={[{ flex: 1, padding: spacing.lg, gap: spacing.md }, webCenter]}>
          <H1>{tr.checkin.title}</H1>
          <Card accent={c.warning}>
            <Muted>{tr.errors.permissionCamera}</Muted>
          </Card>
          <Button title={tr.app.retry} icon="refresh" onPress={() => requestPermission()} fullWidth />
          <Button
            title={tr.checkin.photo}
            icon="camera"
            variant="secondary"
            onPress={pickAndScanId}
            loading={busy}
            fullWidth
          />
        </View>
      </View>
    );
  }

  return (
    <ScrollView
      style={{ flex: 1, backgroundColor: c.bg }}
      contentContainerStyle={[
        {
          padding: spacing.lg,
          gap: spacing.md,
          flexGrow: 1,
        },
        webCenter,
      ]}
    >
      <H1>{tr.checkin.title}</H1>
      {bookingId ? (
        <Badge label={`${tr.checkin.reservationLabel}: ${bookingId}`} tone="info" icon="bookmark" />
      ) : (
        <Badge label={tr.checkin.walkinFlow} tone="primary" icon="walk" />
      )}
      {error ? (
        <Card accent={c.danger}>
          <Body style={{ color: c.danger }}>{error}</Body>
        </Card>
      ) : null}

      <Card>
        <H2>{tr.checkin.guest}</H2>
        <View style={{ height: spacing.sm }} />
        <Field
          label={tr.checkin.firstName}
          value={parsed?.first_name || ''}
          onChangeText={(t) => setParsed((p) => ({ ...(p || {}), first_name: t }))}
        />
        <View style={{ height: spacing.sm }} />
        <Field
          label={tr.checkin.lastName}
          value={parsed?.last_name || ''}
          onChangeText={(t) => setParsed((p) => ({ ...(p || {}), last_name: t }))}
        />
        <View style={{ height: spacing.sm }} />
        <Field
          label={tr.checkin.idOrPassport}
          value={parsed?.id_number || parsed?.passport_number || ''}
          onChangeText={(t) => setParsed((p) => ({ ...(p || {}), id_number: t }))}
        />
        {parsed?.nationality ? (
          <View style={{ marginTop: spacing.sm }}>
            <Badge label={parsed.nationality} tone="info" />
          </View>
        ) : null}
      </Card>

      <Card>
        <H2>{tr.checkin.pickRoom}</H2>
        <Muted style={{ marginTop: spacing.xs }}>
          {rooms.length} {tr.checkin.roomsAvailable}
        </Muted>
        <View style={{ height: spacing.sm }} />
        {roomsError ? (
          <Muted style={{ color: c.danger }}>{tr.rooms.loadError}</Muted>
        ) : rooms.length === 0 ? (
          <Muted>{tr.checkin.noRooms}</Muted>
        ) : (
          <View style={{ flexDirection: 'row', flexWrap: 'wrap', gap: spacing.sm }}>
            {rooms.slice(0, 12).map((r) => (
              <Button
                key={r.id}
                title={r.room_number}
                variant={selectedRoom?.id === r.id ? 'primary' : 'secondary'}
                onPress={() => setSelectedRoom(r)}
              />
            ))}
          </View>
        )}
        {selectedRoom ? (
          <Muted style={{ marginTop: spacing.sm }}>
            {tr.checkin.selected}: {tr.today.room} {selectedRoom.room_number}
            {selectedRoom.room_type ? ` (${selectedRoom.room_type})` : ''}
          </Muted>
        ) : null}
      </Card>

      <Button
        title={tr.checkin.confirm}
        icon="checkmark-circle"
        variant="success"
        onPress={onConfirm}
        loading={busy}
        fullWidth
      />
    </ScrollView>
  );
}
