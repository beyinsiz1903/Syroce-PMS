import React from 'react';
import { Alert, View } from 'react-native';
import { Body, Button, Card, H1, H2, Muted } from '../../src/components/ui';
import { spacing, useTheme } from '../../src/theme';
import { tr } from '../../src/i18n/tr';
import { useAuthStore } from '../../src/state/authStore';
import { getApiUrl } from '../../src/api/client';

export default function MoreScreen() {
  const c = useTheme();
  const { user, logout } = useAuthStore();

  const onLogout = () => {
    Alert.alert(tr.more.logout, '', [
      { text: tr.app.cancel, style: 'cancel' },
      { text: tr.more.logout, style: 'destructive', onPress: () => logout() },
    ]);
  };

  return (
    <View style={{ flex: 1, backgroundColor: c.bg, padding: spacing.lg, gap: spacing.md }}>
      <H1>{tr.more.profile}</H1>
      <Card>
        <H2>{user?.name || user?.username || user?.email || '—'}</H2>
        <Muted>{user?.email}</Muted>
        <Muted>Rol: {user?.role || '—'}</Muted>
        {user?.hotel_id ? <Muted>Otel ID: {user.hotel_id}</Muted> : null}
      </Card>

      <Card>
        <Muted>{tr.more.apiUrl}</Muted>
        <Body>{getApiUrl()}</Body>
      </Card>

      <Button title={tr.more.logout} variant="danger" onPress={onLogout} fullWidth />
    </View>
  );
}
