import React from 'react';
import { View } from 'react-native';
import { Button, Card, H2, Muted } from './ui';
import { spacing } from '../theme';
import { useSettingsStore } from '../state/settingsStore';

export function LanguagePreferences() {
  const locale = useSettingsStore((s) => s.locale);
  const setLocale = useSettingsStore((s) => s.setLocale);
  return <Card><H2>Dil / Language</H2><Muted style={{ marginTop: spacing.xs }}>Türkçe varsayılandır. English, ortak navigasyon ve oturum akışında kullanılabilir; henüz çevrilmemiş operasyon terimleri güvenli biçimde Türkçe kalır.</Muted><View style={{ flexDirection: 'row', gap: spacing.sm, marginTop: spacing.md }}><Button title="Türkçe" variant={locale === 'tr' ? 'primary' : 'secondary'} onPress={() => setLocale('tr')} accessibilityState={{ selected: locale === 'tr' }} /><Button title="English" variant={locale === 'en' ? 'primary' : 'secondary'} onPress={() => setLocale('en')} accessibilityState={{ selected: locale === 'en' }} /></View></Card>;
}
