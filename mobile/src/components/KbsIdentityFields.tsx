import React from 'react';
import { View } from 'react-native';
import { Button, Field, Muted } from './ui';
import { type KbsIdentity } from '../utils/kbs';
import { spacing } from '../theme';

export function KbsIdentityFields({ value, onChange }: { value: KbsIdentity; onChange: (v: KbsIdentity) => void }) {
  const foreign = !['TR', 'TC', 'TUR', 'TURKIYE'].includes(value.nationality.trim().toUpperCase());
  const set = (key: keyof KbsIdentity, v: string) => onChange({ ...value, [key]: v });
  return <View style={{ gap: spacing.sm }}>
    <Field label="Ad ve soyad" value={value.name} onChangeText={v => set('name', v)} autoCapitalize="words" testID="kbs-identity-name" />
    <Field label="Uyruk / ülke kodu (TR, DE, GB…)" value={value.nationality} onChangeText={v => onChange({ ...value, nationality: v.toUpperCase(), id_type: v.toUpperCase() === 'TR' ? 'tc_kimlik' : 'passport' })} autoCapitalize="characters" testID="kbs-identity-nationality" />
    {foreign && <View style={{ flexDirection: 'row', gap: spacing.sm }}>
      <Button title="Pasaport" variant={value.id_type === 'passport' ? 'primary' : 'secondary'} onPress={() => set('id_type', 'passport')} />
      <Button title="Yabancı kimlik (YKN)" variant={value.id_type === 'foreign_identity_card' ? 'primary' : 'secondary'} onPress={() => set('id_type', 'foreign_identity_card')} />
    </View>}
    {foreign && value.id_type !== 'foreign_identity_card'
      ? <Field label="Pasaport numarası" value={value.passport_number} onChangeText={v => set('passport_number', v)} autoCapitalize="characters" autoCorrect={false} testID="kbs-identity-passport" />
      : <Field label={foreign ? '11 haneli yabancı kimlik numarası' : '11 haneli T.C. kimlik numarası'} value={value.id_number} onChangeText={v => set('id_number', v)} keyboardType="number-pad" maxLength={11} autoCorrect={false} testID="kbs-identity-number" />}
    {foreign && value.id_type !== 'foreign_identity_card' && <>
      <Field label="Doğum tarihi (YYYY-AA-GG)" value={value.date_of_birth} onChangeText={v => set('date_of_birth', v)} placeholder="1985-04-23" autoCorrect={false} testID="kbs-identity-birth-date" />
      <View style={{ flexDirection: 'row', gap: spacing.sm }}>
        <Button title="Kadın" variant={value.gender === 'F' ? 'primary' : 'secondary'} onPress={() => set('gender', 'F')} />
        <Button title="Erkek" variant={value.gender === 'M' ? 'primary' : 'secondary'} onPress={() => set('gender', 'M')} />
      </View>
    </>}
    <Muted>Kimlik bilgileri yalnız yetkili PMS sunucusuna kaydedilir. Bu form tek başına kuruma bildirim göndermez.</Muted>
  </View>;
}
