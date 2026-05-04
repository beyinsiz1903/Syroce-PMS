import React, { useEffect, useRef, useState } from 'react';
import { Alert, ScrollView, View } from 'react-native';
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
  Field,
  H1,
  H2,
  Muted,
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
  const [parsed, setParsed] = useState<QuickIdResult | null>(null);
  const [bookingId, setBookingId] = useState<string | null>(params.bookingId ?? null);
  const [rooms, setRooms] = useState<Room[]>([]);
  const [selectedRoom, setSelectedRoom] = useState<Room | null>(null);

  useEffect(() => {
    if (!permission) requestPermission();
  }, [permission, requestPermission]);

  useEffect(() => {
    listRooms().then((rs) => {
      setRooms(rs.filter((r) => AVAILABLE_STATUSES.includes((r.status || '').toLowerCase())));
    });
  }, []);

  const onBarcodeScanned = async ({ data }: BarcodeScanningResult) => {
    if (scannedRef.current) return;
    scannedRef.current = true;
    haptic.tap();
    const trimmed = (data || '').trim();
    if (trimmed.startsWith('booking:')) {
      setBookingId(trimmed.split(':')[1] || null);
    } else if (/^\d{1,4}$/.test(trimmed)) {
      const list = await searchBookingByRoom(trimmed);
      if (list.length) setBookingId(list[0].id);
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
      setError('Rezervasyon yoksa walk-in için oda seçin');
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
      Alert.alert(tr.app.success, tr.checkin.success, [
        { text: tr.app.close, onPress: () => router.back() },
      ]);
    } catch (e: unknown) {
      setError(errorMessage(e, tr.errors.generic));
      haptic.error();
    } finally {
      setBusy(false);
    }
  };

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
          <Button title={tr.checkin.photo} onPress={pickAndScanId} loading={busy} />
        </View>
      </View>
    );
  }

  if (step === 'scan' && !permission?.granted) {
    return (
      <View style={{ flex: 1, padding: spacing.lg, backgroundColor: c.bg, gap: spacing.md }}>
        <H1>{tr.checkin.title}</H1>
        <Muted>{tr.errors.permissionCamera}</Muted>
        <Button title={tr.app.retry} onPress={() => requestPermission()} />
        <Button
          title={tr.checkin.photo}
          variant="secondary"
          onPress={pickAndScanId}
          loading={busy}
        />
      </View>
    );
  }

  return (
    <ScrollView
      contentContainerStyle={{
        padding: spacing.lg,
        gap: spacing.md,
        backgroundColor: c.bg,
        flexGrow: 1,
      }}
    >
      <H1>{tr.checkin.title}</H1>
      {bookingId ? <Muted>Rezervasyon: {bookingId}</Muted> : <Muted>Walk-in akışı</Muted>}
      {error ? <Body style={{ color: c.danger }}>{error}</Body> : null}

      <Card>
        <H2>Misafir</H2>
        <Field
          label="Ad"
          value={parsed?.first_name || ''}
          onChangeText={(t) => setParsed((p) => ({ ...(p || {}), first_name: t }))}
        />
        <View style={{ height: spacing.sm }} />
        <Field
          label="Soyad"
          value={parsed?.last_name || ''}
          onChangeText={(t) => setParsed((p) => ({ ...(p || {}), last_name: t }))}
        />
        <View style={{ height: spacing.sm }} />
        <Field
          label="Kimlik / Pasaport"
          value={parsed?.id_number || parsed?.passport_number || ''}
          onChangeText={(t) => setParsed((p) => ({ ...(p || {}), id_number: t }))}
        />
        {parsed?.nationality ? <Badge label={parsed.nationality} tone="info" /> : null}
      </Card>

      <Card>
        <H2>{tr.checkin.pickRoom}</H2>
        <Muted>{rooms.length} uygun oda</Muted>
        <View style={{ height: spacing.sm }} />
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
        {selectedRoom ? (
          <Muted style={{ marginTop: spacing.sm }}>
            Seçildi: Oda {selectedRoom.room_number} ({selectedRoom.room_type || ''})
          </Muted>
        ) : null}
      </Card>

      <Button title={tr.checkin.confirm} onPress={onConfirm} loading={busy} fullWidth />
    </ScrollView>
  );
}
