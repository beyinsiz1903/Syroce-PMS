import React, { useState } from 'react';
import { Alert, ScrollView, View } from 'react-native';
import { Body, Button, Card, Field, H1, Muted } from '../../src/components/ui';
import { spacing, useTheme } from '../../src/theme';
import { tr } from '../../src/i18n/tr';
import { api } from '../../src/api/client';
import { haptic } from '../../src/hooks/useHaptic';
import { errorMessage } from '../../src/utils/errors';

export default function DamageScreen() {
  const c = useTheme();
  const [roomId, setRoomId] = useState('');
  const [description, setDescription] = useState('');
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState<string | null>(null);

  const onSubmit = async () => {
    if (!roomId || !description) {
      setError('Oda ID ve açıklama gerekli');
      return;
    }
    setBusy(true);
    setError(null);
    try {
      await api.post('/api/housekeeping/mobile/report-issue', {
        room_id: roomId,
        issue_type: 'damage',
        description,
        priority: 'high',
        photos: [],
      });
      haptic.success();
      Alert.alert(tr.app.success, 'Hasar bildirildi');
      setRoomId('');
      setDescription('');
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
      <H1>{tr.tabs.damage}</H1>
      <Muted>Hasar veya bakım bildirimi gönder</Muted>
      {error ? <Body style={{ color: c.danger }}>{error}</Body> : null}
      <Card>
        <Field label="Oda ID" value={roomId} onChangeText={setRoomId} autoCapitalize="none" />
        <View style={{ height: spacing.sm }} />
        <Field
          label="Açıklama"
          value={description}
          onChangeText={setDescription}
          multiline
          numberOfLines={4}
        />
      </Card>
      <Button title={tr.app.save} onPress={onSubmit} loading={busy} fullWidth />
    </ScrollView>
  );
}
