import React, { useEffect, useState } from 'react';
import { ScrollView, View } from 'react-native';
import { useRouter } from 'expo-router';
import { Badge, Body, Button, Card, EmptyState, Field, H1, H2, Muted, webCenter } from '../../src/components/ui';
import { spacing, useTheme } from '../../src/theme';
import { tr } from '../../src/i18n/tr';
import { haptic } from '../../src/hooks/useHaptic';
import { listRooms, Room } from '../../src/api/rooms';
import { walkInQuick } from '../../src/api/bookings';
import { errorMessage } from '../../src/utils/errors';
import { KbsIdentityFields } from '../../src/components/KbsIdentityFields';
import { emptyKbsIdentity, kbsIdentityMissing, kbsMissingText } from '../../src/utils/kbs';

const AVAILABLE_STATUSES = ['available', 'clean', 'inspected'];

export default function WalkInScreen() {
  const c = useTheme();
  const router = useRouter();
  const [name, setName] = useState('');
  const [identity, setIdentity] = useState(emptyKbsIdentity);
  const [phone, setPhone] = useState('');
  const [roomType, setRoomType] = useState<string>('');
  const [rate, setRate] = useState<string>('0');
  const [rooms, setRooms] = useState<Room[]>([]);
  const [suggested, setSuggested] = useState<Room | null>(null);
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const [done, setDone] = useState(false);

  useEffect(() => {
    listRooms().then((rs) => {
      setRooms(rs.filter((r) => AVAILABLE_STATUSES.includes((r.status || '').toLowerCase())));
    });
  }, []);

  const types = Array.from(
    new Set(rooms.map((r) => r.room_type).filter((t): t is string => !!t)),
  );

  const onSuggest = (rt: string) => {
    setRoomType(rt);
    const next = rooms.find((r) => (r.room_type || '') === rt);
    setSuggested(next || null);
  };

  const onConfirm = async () => {
    const missing = kbsIdentityMissing({ ...identity, name });
    if (missing.length) { setError(`KBS için tamamlayın: ${kbsMissingText(missing)}`); return; }
    if (!name || !suggested) {
      setError(tr.walkin.needNameRoom);
      haptic.warning();
      return;
    }
    setBusy(true);
    setError(null);
    try {
      await walkInQuick({
        guest_name: name,
        guest_phone: phone || undefined,
        room_id: suggested.id,
        nights: 1,
        rate_amount: parseFloat(rate || '0') || 0,
        payment_method: 'cash',
        nationality: identity.nationality, id_type: identity.id_type, id_number: identity.id_number || undefined,
        passport_number: identity.passport_number || undefined, birth_date: identity.date_of_birth || undefined, gender: identity.gender || undefined,
      });
      haptic.success();
      // Inline success state (NOT Alert.alert — a no-op on Expo Web).
      setDone(true);
      setIdentity(emptyKbsIdentity());
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
            title={tr.walkin.success}
            message={tr.walkin.successHint}
            action={
              <Button title={tr.walkin.done} icon="arrow-back" onPress={() => router.back()} />
            }
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
      <H1>{tr.walkin.title}</H1>
      {error ? (
        <Card accent={c.danger}>
          <Body style={{ color: c.danger }}>{error}</Body>
        </Card>
      ) : null}

      <Card>
        <KbsIdentityFields value={{ ...identity, name }} onChange={v => { setIdentity(v); setName(v.name); }} />
        <View style={{ height: spacing.sm }} />
        <Field label={tr.walkin.phone} value={phone} onChangeText={setPhone} keyboardType="phone-pad" />
      </Card>

      <Card>
        <H2>{tr.walkin.roomType}</H2>
        {types.length === 0 ? (
          <Muted style={{ marginTop: spacing.sm }}>{tr.walkin.noRooms}</Muted>
        ) : (
          <View
            style={{
              flexDirection: 'row',
              flexWrap: 'wrap',
              gap: spacing.sm,
              marginTop: spacing.sm,
            }}
          >
            {types.map((t) => (
              <Button
                key={t}
                title={t}
                variant={roomType === t ? 'primary' : 'secondary'}
                onPress={() => onSuggest(t)}
              />
            ))}
          </View>
        )}
        {suggested ? (
          <View style={{ marginTop: spacing.md, flexDirection: 'row', alignItems: 'center', gap: spacing.sm }}>
            <Muted>{tr.walkin.suggested}:</Muted>
            <Badge label={`${tr.walkin.room} ${suggested.room_number}`} tone="success" icon="bed" />
          </View>
        ) : null}
      </Card>

      <Card>
        <Field
          label={`${tr.walkin.rate} (TRY)`}
          value={rate}
          onChangeText={setRate}
          keyboardType="decimal-pad"
        />
        <Muted style={{ marginTop: spacing.sm }}>Walk-in tutarı Türk lirası (TRY) olarak kaydedilir.</Muted>
      </Card>

      <Button
        title={tr.walkin.confirm}
        icon="checkmark-circle"
        variant="success"
        onPress={onConfirm}
        loading={busy}
        fullWidth
      />
    </ScrollView>
  );
}
