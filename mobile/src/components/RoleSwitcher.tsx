import React from 'react';
import { View } from 'react-native';
import { useRouter, useSegments } from 'expo-router';
import { Ionicons } from '@expo/vector-icons';
import { Card, H2, ListRow, Muted } from './ui';
import { spacing } from '../theme';
import { tr } from '../i18n/tr';
import { useAuthStore } from '../state/authStore';
import { ALL_ROLE_GROUPS, type SwitchableRole } from '../navigation/routes';

const ROLE_ICONS: Record<SwitchableRole, keyof typeof Ionicons.glyphMap> = {
  gm: 'briefcase-outline',
  front_desk: 'desktop-outline',
  housekeeping: 'brush-outline',
  guest_app: 'person-outline',
};

// All-access role switcher. Renders nothing for single-role users; for
// super_admin/admin it offers one-tap navigation into every role group's
// screens, presented as an Apple "Settings"-style list (active group shows a
// checkmark). AuthGate permits these users to sit in any group, so switching
// is a plain `router.replace` to the target group root.
export function RoleSwitcher() {
  const router = useRouter();
  const segments = useSegments();
  const allAccess = useAuthStore((s) => s.allAccess);

  if (!allAccess) return null;

  const current = segments[0];

  return (
    <View style={{ gap: spacing.sm }}>
      <H2>{tr.roleSwitch.title}</H2>
      <Muted>{tr.roleSwitch.subtitle}</Muted>
      <Card padded={false} style={{ overflow: 'hidden' }}>
        {ALL_ROLE_GROUPS.map((g, i) => (
          <ListRow
            key={g.group}
            icon={ROLE_ICONS[g.key]}
            label={tr.roleSwitch.groups[g.key]}
            onPress={() => router.replace(g.route)}
            active={current === g.group}
            last={i === ALL_ROLE_GROUPS.length - 1}
          />
        ))}
      </Card>
    </View>
  );
}
