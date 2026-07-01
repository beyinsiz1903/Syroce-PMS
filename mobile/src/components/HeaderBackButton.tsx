import React from 'react';
import { Pressable } from 'react-native';
import { Ionicons } from '@expo/vector-icons';
import { router } from 'expo-router';
import { spacing, useTheme } from '../theme';
import { haptic } from '../hooks/useHaptic';

// Tabs gezgini (expo-router) push edilen `href:null` detay ekranlarinda
// header'da geri oku gostermez — bu yuzden detay sayfalarinda kullanici
// kapana kisilir. Bu bilesen header `headerLeft` olarak takilir; gecmis
// varsa geri gider, yoksa verilen `fallback` rotasina doner.
export function HeaderBackButton({ fallback }: { fallback?: string }) {
  const c = useTheme();
  return (
    <Pressable
      onPress={() => {
        haptic.tap();
        if (router.canGoBack()) {
          router.back();
        } else if (fallback) {
          router.replace(fallback as never);
        }
      }}
      accessibilityRole="button"
      accessibilityLabel="Geri"
      testID="header-back"
      hitSlop={12}
      style={({ pressed }) => ({
        paddingHorizontal: spacing.md,
        paddingVertical: spacing.xs,
        opacity: pressed ? 0.6 : 1,
      })}
    >
      <Ionicons name="chevron-back" size={26} color={c.text} />
    </Pressable>
  );
}
