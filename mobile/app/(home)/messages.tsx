import React from 'react';
import { ScrollView, View } from 'react-native';
import { Card, H1, Muted } from '../../src/components/ui';
import { spacing, useTheme } from '../../src/theme';
import { tr } from '../../src/i18n/tr';

// Tier-1 messaging surface. Staff-to-staff messaging is a later phase; for
// Faz 0 this is the placeholder slot in the common shell so the backbone is
// complete. No fabricated data is shown.
export default function MessagesScreen() {
  const c = useTheme();
  return (
    <View style={{ flex: 1, backgroundColor: c.bg }} testID="smoke-home-messages">
      <ScrollView contentContainerStyle={{ padding: spacing.lg, gap: spacing.md }}>
        <H1>{tr.hub.messagesTitle}</H1>
        <Card>
          <Muted>{tr.hub.messagesSoon}</Muted>
        </Card>
      </ScrollView>
    </View>
  );
}
