import React from 'react';
import { Pressable, Text, View } from 'react-native';
import { Ionicons } from '@expo/vector-icons';
import { Card, H2, Muted } from './ui';
import { radius, spacing, useTheme } from '../theme';
import { useSettingsStore, type ThemeMode } from '../state/settingsStore';
import { tr } from '../i18n/tr';

// Acik / Koyu / Sistem uclu secici. Tek dogruluk kaynagi settingsStore.themeMode;
// secim AsyncStorage'a yazilir ve useTheme()'i cagiran tum ekranlara aninda yansir.
// 'system' = cihazin OS acik/koyu ayarini izle.
const OPTIONS: {
  mode: ThemeMode;
  icon: keyof typeof Ionicons.glyphMap;
  label: () => string;
}[] = [
  { mode: 'light', icon: 'sunny-outline', label: () => tr.more.themeLight },
  { mode: 'dark', icon: 'moon-outline', label: () => tr.more.themeDark },
  { mode: 'system', icon: 'phone-portrait-outline', label: () => tr.more.themeSystem },
];

export const ThemeModeSelector: React.FC = () => {
  const c = useTheme();
  const mode = useSettingsStore((s) => s.themeMode);
  const setThemeMode = useSettingsStore((s) => s.setThemeMode);

  return (
    <Card>
      <H2>{tr.more.theme}</H2>
      <Muted style={{ marginTop: 2, marginBottom: spacing.md }}>{tr.more.themeHint}</Muted>
      <View style={{ flexDirection: 'row', gap: spacing.sm }}>
        {OPTIONS.map((o) => {
          const selected = mode === o.mode;
          return (
            <Pressable
              key={o.mode}
              onPress={() => setThemeMode(o.mode)}
              accessibilityRole="button"
              accessibilityState={{ selected }}
              accessibilityLabel={o.label()}
              testID={`theme-mode-${o.mode}`}
              style={{
                flex: 1,
                paddingVertical: spacing.md,
                borderRadius: radius.md,
                alignItems: 'center',
                gap: 4,
                backgroundColor: selected ? c.primarySoft : c.surfaceAlt,
                borderWidth: 1,
                borderColor: selected ? c.primary : c.border,
              }}
            >
              <Ionicons name={o.icon} size={20} color={selected ? c.primary : c.textMuted} />
              <Text
                style={{
                  color: selected ? c.primary : c.text,
                  fontSize: 13,
                  fontWeight: selected ? '700' : '500',
                }}
              >
                {o.label()}
              </Text>
            </Pressable>
          );
        })}
      </View>
    </Card>
  );
};

export default ThemeModeSelector;
