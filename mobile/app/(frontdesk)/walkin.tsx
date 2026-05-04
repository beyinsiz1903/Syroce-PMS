import React, { useEffect, useState } from 'react';
import { Alert, ScrollView, View } from 'react-native';
import { useRouter } from 'expo-router';
import { Body, Button, Card, Field, H1, H2, Muted } from '../../src/components/ui';
import { spacing, useTheme } from '../../src/theme';
import { tr } from '../../src/i18n/tr';
import { haptic } from '../../src/hooks/useHaptic';
import { listRooms, Room } from '../../src/api/rooms';
import { walkInQuick } from '../../src/api/bookings';
import { errorMessage } from '../../src/utils/errors';

const AVAILABLE_STATUSES = ['available', 'clean', 'inspected'];

export default function WalkInScreen() {
  const c = useTheme();
  const router = useRouter();
  const [name, setName] = useState('');
  const [phone, setPhone] = useState('');
  const [roomType, setRoomType] = useState<string>('');
  const [rate, setRate] = useState<string>('0');
  const [rooms, setRooms] = useState<Room[]>([]);
  const [suggested, setSuggested] = useState<Room | null>(null);
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState<string | null>(null);

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
    if (!name || !suggested) {
      setError('Ad ve oda gerekli');
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
      });
      haptic.success();
      Alert.alert(tr.app.success, tr.walkin.success, [
        { text: tr.app.close, onPress: () => router.back() },
      ]);
    } catch (e: unknown) {
      setError(errorMessage(e, tr.errors.generic));
      haptic.error();
    } finally {
      setBusy(false);
    }
  };

  return (
    <ScrollView
      contentContainerStyle={{
        padding: spacing.lg,
        gap: spacing.md,
        backgroundColor: c.bg,
        flexGrow: 1,
      }}
    >
      <H1>{tr.walkin.title}</H1>
      {error ? <Body style={{ color: c.danger }}>{error}</Body> : null}

      <Card>
        <Field label={tr.walkin.name} value={name} onChangeText={setName} autoCapitalize="words" />
        <View style={{ height: spacing.sm }} />
        <Field label={tr.walkin.phone} value={phone} onChangeText={setPhone} keyboardType="phone-pad" />
      </Card>

      <Card>
        <H2>{tr.walkin.roomType}</H2>
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
        {suggested ? (
          <View style={{ marginTop: spacing.md }}>
            <Muted>{tr.walkin.suggested}</Muted>
            <H2>Oda {suggested.room_number}</H2>
          </View>
        ) : null}
      </Card>

      <Card>
        <Field
          label={tr.walkin.rate}
          value={rate}
          onChangeText={setRate}
          keyboardType="decimal-pad"
        />
      </Card>

      <Button title={tr.walkin.confirm} onPress={onConfirm} loading={busy} fullWidth />
    </ScrollView>
  );
}
