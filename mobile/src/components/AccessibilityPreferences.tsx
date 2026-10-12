import React from 'react';
import { View } from 'react-native';
import { Body, Card, H2, Muted, Button } from './ui';
import { spacing } from '../theme';
import { TextScale, useSettingsStore } from '../state/settingsStore';

const choices: { value: TextScale; label: string }[] = [
  { value: 'standard', label: 'Standart' }, { value: 'large', label: 'Büyük' }, { value: 'extra_large', label: 'Çok büyük' },
];

export function AccessibilityPreferences() {
  const textScale = useSettingsStore((s) => s.textScale);
  const setTextScale = useSettingsStore((s) => s.setTextScale);
  return <Card accessibilityLabel="Erişilebilirlik tercihleri"><H2>Erişilebilirlik</H2><Muted style={{ marginTop: spacing.xs }}>Metin boyutu cihazınızın ayarlarına ek olarak uygulama içinde de büyütülebilir.</Muted><View style={{ flexDirection: 'row', flexWrap: 'wrap', gap: spacing.sm, marginTop: spacing.md }}>{choices.map((choice) => <Button key={choice.value} title={choice.label} variant={textScale === choice.value ? 'primary' : 'secondary'} onPress={() => setTextScale(choice.value)} accessibilityState={{ selected: textScale === choice.value }} />)}</View><Body style={{ marginTop: spacing.md }}>Seçili: {choices.find((choice) => choice.value === textScale)?.label}</Body></Card>;
}
