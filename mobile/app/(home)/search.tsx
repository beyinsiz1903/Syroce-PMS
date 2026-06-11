import React from 'react';
import { ScrollView, View } from 'react-native';
import { Card, Field, H1, Muted } from '../../src/components/ui';
import { spacing, useTheme } from '../../src/theme';
import { tr } from '../../src/i18n/tr';

// Tier-1 unified-search surface. The cross-entity search backend lands in a
// later phase; for Faz 0 this is the placeholder slot in the common shell so
// the backbone is complete. The input is non-functional by design here.
export default function SearchScreen() {
  const c = useTheme();
  return (
    <View style={{ flex: 1, backgroundColor: c.bg }} testID="smoke-home-search">
      <ScrollView contentContainerStyle={{ padding: spacing.lg, gap: spacing.md }}>
        <H1>{tr.hub.searchTitle}</H1>
        <Field placeholder={tr.hub.searchPlaceholder} editable={false} />
        <Card>
          <Muted>{tr.hub.searchSoon}</Muted>
        </Card>
      </ScrollView>
    </View>
  );
}
