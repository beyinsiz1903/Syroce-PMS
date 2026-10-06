import React, { useState } from 'react';
import { Alert, Pressable, ScrollView, View } from 'react-native';
import { useRouter } from 'expo-router';
import { Body, Button, Card, Field, H1, Muted } from '../../src/components/ui';
import { radius, spacing, useTheme } from '../../src/theme';
import { tr } from '../../src/i18n/tr';
import { createWorkOrder } from '../../src/api/maintenance';
import { errorMessage } from '../../src/utils/errors';
import { haptic } from '../../src/hooks/useHaptic';

const ISSUE_TYPES = ['plumbing', 'hvac', 'electrical', 'furniture', 'housekeeping_damage', 'other'] as const;
const PRIORITIES = ['normal', 'high', 'urgent'] as const;

export default function FaultReportScreen() {
  const c = useTheme();
  const router = useRouter();
  const [issueType, setIssueType] = useState<(typeof ISSUE_TYPES)[number]>('other');
  const [priority, setPriority] = useState<(typeof PRIORITIES)[number]>('normal');
  const [roomNumber, setRoomNumber] = useState('');
  const [description, setDescription] = useState('');
  const [saving, setSaving] = useState(false);

  const submit = async () => {
    if (!description.trim()) {
      Alert.alert(tr.app.error, 'Arızayı kısaca açıklayın.');
      return;
    }
    setSaving(true);
    try {
      await createWorkOrder({
        issue_type: issueType,
        priority,
        room_number: roomNumber.trim() || undefined,
        description: description.trim(),
        source: 'frontdesk',
      });
      haptic.success();
      Alert.alert(tr.app.success, tr.departments.maintenance.created, [
        { text: tr.checkout.done, onPress: () => router.back() },
      ]);
    } catch (error: unknown) {
      haptic.error();
      Alert.alert(tr.app.error, errorMessage(error, tr.errors.generic));
    } finally {
      setSaving(false);
    }
  };

  const Chip = ({ label, active, onPress }: { label: string; active: boolean; onPress: () => void }) => (
    <Pressable
      accessibilityRole="button"
      accessibilityState={{ selected: active }}
      onPress={onPress}
      style={{
        paddingHorizontal: spacing.md,
        paddingVertical: spacing.sm,
        borderRadius: radius.pill,
        borderWidth: 1,
        borderColor: active ? c.primary : c.border,
        backgroundColor: active ? c.primary : c.surface,
      }}
    >
      <Body style={{ color: active ? c.primaryText : c.text, fontWeight: '700' }}>{label}</Body>
    </Pressable>
  );

  return (
    <ScrollView
      style={{ flex: 1, backgroundColor: c.bg }}
      contentContainerStyle={{ padding: spacing.lg, gap: spacing.md }}
    >
      <H1>Arıza Bildirimi</H1>
      <Muted>Teknisyen ekibine iletilecek kısa bir iş emri oluşturun.</Muted>
      <Card>
        <Field
          label={tr.departments.maintenance.roomNumber}
          value={roomNumber}
          onChangeText={setRoomNumber}
          keyboardType="number-pad"
          placeholder="Örn. 204"
        />
        <View style={{ height: spacing.md }} />
        <Body style={{ fontWeight: '700', marginBottom: spacing.sm }}>{tr.departments.maintenance.issueType}</Body>
        <View style={{ flexDirection: 'row', flexWrap: 'wrap', gap: spacing.sm }}>
          {ISSUE_TYPES.map((type) => (
            <Chip
              key={type}
              label={tr.departments.maintenance.issueTypes[type]}
              active={issueType === type}
              onPress={() => setIssueType(type)}
            />
          ))}
        </View>
        <View style={{ height: spacing.lg }} />
        <Body style={{ fontWeight: '700', marginBottom: spacing.sm }}>{tr.departments.maintenance.priority}</Body>
        <View style={{ flexDirection: 'row', flexWrap: 'wrap', gap: spacing.sm }}>
          {PRIORITIES.map((value) => (
            <Chip
              key={value}
              label={tr.departments.maintenance.priorities[value]}
              active={priority === value}
              onPress={() => setPriority(value)}
            />
          ))}
        </View>
        <View style={{ height: spacing.lg }} />
        <Field
          label={tr.departments.maintenance.description}
          value={description}
          onChangeText={setDescription}
          multiline
          placeholder="Örn. Banyoda sıcak su gelmiyor."
        />
      </Card>
      <Button
        title={tr.departments.maintenance.create}
        icon="construct"
        loading={saving}
        onPress={submit}
        fullWidth
      />
    </ScrollView>
  );
}
