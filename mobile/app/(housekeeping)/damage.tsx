import React, { useRef, useState } from 'react';
import { Pressable, ScrollView, Text, View } from 'react-native';
import { useLocalSearchParams } from 'expo-router';
import * as ImagePicker from 'expo-image-picker';
import {
  Body,
  Button,
  Card,
  DetailHeader,
  Field,
  FormActions,
  Muted,
  webCenter,
} from '../../src/components/ui';
import { FilterChips } from '../../src/components/FilterChips';
import { SignaturePad, SignaturePadHandle } from '../../src/components/SignaturePad';
import { spacing, radius, useTheme } from '../../src/theme';
import { tr } from '../../src/i18n/tr';
import { reportIssue } from '../../src/api/housekeeping';
import { haptic } from '../../src/hooks/useHaptic';
import { errorMessage } from '../../src/utils/errors';

const ISSUE_TYPES = [
  { value: 'damage', label: tr.housekeeping.issueDamage },
  { value: 'maintenance', label: tr.housekeeping.issueMaintenance },
  { value: 'cleaning', label: tr.housekeeping.issueCleaning },
];

const PRIORITIES = [
  { value: 'normal', label: tr.housekeeping.priorityNormal },
  { value: 'high', label: tr.housekeeping.priorityHigh },
  { value: 'urgent', label: tr.housekeeping.priorityUrgent },
];

export default function DamageScreen() {
  const c = useTheme();
  // Kat Hizmetleri listesinden "Hasar Bildir" ile gelindiyse oda onceden
  // doldurulur (housekeeper UUID yazmak zorunda kalmaz).
  const params = useLocalSearchParams<{ roomId?: string; roomNumber?: string }>();
  const prefillRoomId = typeof params.roomId === 'string' ? params.roomId : '';
  const roomNumber = typeof params.roomNumber === 'string' ? params.roomNumber : '';
  const [roomId, setRoomId] = useState(prefillRoomId);
  const [issueType, setIssueType] = useState('damage');
  const [priority, setPriority] = useState('high');
  const [description, setDescription] = useState('');
  const [photos, setPhotos] = useState<string[]>([]);
  const [signatureSvg, setSignatureSvg] = useState<string | null>(null);
  const sigRef = useRef<SignaturePadHandle>(null);
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const [done, setDone] = useState(false);

  // Capture a photo via the camera. base64:true so the bytes ride along in the
  // report-issue `photos` list (the backend has no separate upload endpoint for
  // housekeeping issues — unlike the check-in id-photo multipart path).
  const addPhoto = async () => {
    setError(null);
    try {
      const result = await ImagePicker.launchCameraAsync({
        mediaTypes: ImagePicker.MediaTypeOptions.Images,
        quality: 0.6,
        base64: true,
      });
      if (result.canceled) return;
      const asset = result.assets[0];
      if (!asset?.base64) return;
      haptic.tap();
      setPhotos((prev) => [...prev, `data:image/jpeg;base64,${asset.base64}`]);
    } catch {
      haptic.error();
      setError(tr.housekeeping.photoError);
    }
  };

  const removePhoto = (idx: number) => {
    haptic.tap();
    setPhotos((prev) => prev.filter((_, i) => i !== idx));
  };

  const clearForm = () => {
    setRoomId(prefillRoomId);
    setIssueType('damage');
    setPriority('high');
    setDescription('');
    setPhotos([]);
    setSignatureSvg(null);
    sigRef.current?.clear();
  };

  const onSubmit = async () => {
    if (!roomId.trim() || !description.trim()) {
      setError(tr.housekeeping.reportFormError);
      haptic.warning();
      return;
    }
    setBusy(true);
    setError(null);
    setDone(false);
    try {
      // The reporter signature has no dedicated backend field, so persist it as
      // an SVG data-URI alongside the photos (it renders as an image in any
      // viewer) — captured for real, never silently dropped.
      const sigEntry = signatureSvg
        ? [`data:image/svg+xml;utf8,${encodeURIComponent(signatureSvg)}`]
        : [];
      await reportIssue({
        room_id: roomId.trim(),
        issue_type: issueType,
        description: description.trim(),
        priority,
        photos: [...photos, ...sigEntry],
      });
      haptic.success();
      setDone(true);
      clearForm();
    } catch (e: unknown) {
      setError(errorMessage(e, tr.errors.generic));
      haptic.error();
    } finally {
      setBusy(false);
    }
  };

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
      keyboardShouldPersistTaps="handled"
    >
      <DetailHeader title={tr.tabs.damage} subtitle={tr.housekeeping.damageSubtitle} />

      {done ? (
        <Card accent={c.success}>
          <Body style={{ color: c.success, fontWeight: '700' }}>
            {tr.housekeeping.reportSuccess}
          </Body>
        </Card>
      ) : null}
      {error ? (
        <Card accent={c.danger}>
          <Body style={{ color: c.danger }}>{error}</Body>
        </Card>
      ) : null}

      <Card>
        {roomNumber ? (
          <Muted style={{ marginBottom: spacing.xs }}>Oda {roomNumber}</Muted>
        ) : null}
        <Field
          label={tr.housekeeping.roomIdLabel}
          value={roomId}
          onChangeText={(t) => {
            setRoomId(t);
            if (done) setDone(false);
          }}
          autoCapitalize="none"
          testID="hk-damage-room"
        />
        <View style={{ height: spacing.md }} />
        <Muted style={{ marginBottom: spacing.xs }}>{tr.housekeeping.issueTypeLabel}</Muted>
        <FilterChips options={ISSUE_TYPES} value={issueType} onChange={setIssueType} />
        <View style={{ height: spacing.sm }} />
        <Muted style={{ marginBottom: spacing.xs }}>{tr.housekeeping.priority}</Muted>
        <FilterChips options={PRIORITIES} value={priority} onChange={setPriority} />
        <View style={{ height: spacing.md }} />
        <Field
          label={tr.housekeeping.descriptionLabel}
          placeholder={tr.housekeeping.descriptionPlaceholder}
          value={description}
          onChangeText={(t) => {
            setDescription(t);
            if (done) setDone(false);
          }}
          multiline
          numberOfLines={4}
          testID="hk-damage-description"
        />
      </Card>

      <Card>
        <View
          style={{ flexDirection: 'row', justifyContent: 'space-between', alignItems: 'center' }}
        >
          <Muted>{tr.housekeeping.photoSection}</Muted>
          <Button
            title={tr.housekeeping.photoAdd}
            variant="secondary"
            icon="camera"
            onPress={() => void addPhoto()}
            testID="hk-damage-add-photo"
            style={{ paddingVertical: spacing.xs, paddingHorizontal: spacing.sm, minHeight: 0 }}
          />
        </View>
        {photos.length > 0 ? (
          <>
            <Muted style={{ marginTop: spacing.sm }}>
              {photos.length} {tr.housekeeping.photoAttached}
            </Muted>
            <View
              style={{ flexDirection: 'row', flexWrap: 'wrap', gap: spacing.xs, marginTop: spacing.xs }}
            >
              {photos.map((_, idx) => (
                <Pressable
                  key={idx}
                  onPress={() => removePhoto(idx)}
                  style={{
                    flexDirection: 'row',
                    alignItems: 'center',
                    gap: spacing.xs,
                    borderWidth: 1,
                    borderColor: c.border,
                    borderRadius: radius.md,
                    paddingVertical: spacing.xs,
                    paddingHorizontal: spacing.sm,
                  }}
                >
                  <Text style={{ color: c.text, fontSize: 13 }}>#{idx + 1}</Text>
                  <Text style={{ color: c.danger, fontSize: 12, fontWeight: '600' }}>
                    {tr.housekeeping.photoRemove}
                  </Text>
                </Pressable>
              ))}
            </View>
          </>
        ) : null}
      </Card>

      <Card>
        <Muted>{tr.housekeeping.signatureSection}</Muted>
        <Muted style={{ marginTop: spacing.xs, marginBottom: spacing.sm }}>
          {tr.housekeeping.signatureHint}
        </Muted>
        <SignaturePad
          ref={sigRef}
          onChange={setSignatureSvg}
          clearLabel={tr.housekeeping.signatureClear}
        />
      </Card>

      <FormActions>
        <Button
          title={tr.app.cancel}
          variant="secondary"
          onPress={clearForm}
          disabled={busy}
          fullWidth
        />
        <Button
          title={tr.app.save}
          onPress={() => void onSubmit()}
          loading={busy}
          testID="hk-damage-submit"
          fullWidth
        />
      </FormActions>
    </ScrollView>
  );
}
