import React from 'react';
import { View } from 'react-native';
import { useRouter, useSegments } from 'expo-router';
import { Button, Card, H2, Muted } from './ui';
import { spacing } from '../theme';
import { tr } from '../i18n/tr';
import { useAuthStore } from '../state/authStore';
import { ALL_ROLE_GROUPS } from '../navigation/routes';

// All-access role switcher. Renders nothing for single-role users; for
// super_admin/admin it offers one-tap navigation into every role group's
// screens. AuthGate permits these users to sit in any group, so switching
// is a plain `router.replace` to the target group root.
export function RoleSwitcher() {
  const router = useRouter();
  const segments = useSegments();
  const allAccess = useAuthStore((s) => s.allAccess);

  if (!allAccess) return null;

  const current = segments[0];

  return (
    <Card>
      <H2>{tr.roleSwitch.title}</H2>
      <Muted style={{ marginTop: spacing.xs, marginBottom: spacing.sm }}>
        {tr.roleSwitch.subtitle}
      </Muted>
      <View style={{ gap: spacing.sm }}>
        {ALL_ROLE_GROUPS.map((g) => (
          <Button
            key={g.group}
            title={tr.roleSwitch.groups[g.key]}
            variant={current === g.group ? 'primary' : 'secondary'}
            onPress={() => router.replace(g.route)}
            fullWidth
          />
        ))}
      </View>
    </Card>
  );
}
