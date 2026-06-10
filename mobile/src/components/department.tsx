import React from 'react';
import { Pressable, View } from 'react-native';
import { Body, Card, H2, Muted, SkeletonCard } from './ui';
import { spacing, useTheme } from '../theme';
import { tr } from '../i18n/tr';
import { errorMessage, isOffline } from '../utils/errors';

// Shared widgets for the (departments) area so sibling department screens
// (Spa, MICE, and the upcoming Accounting / Maintenance task) render loading,
// empty and error states identically without copy-pasting layout.

export const SectionTitle: React.FC<{ title: string; right?: React.ReactNode }> = ({
  title,
  right,
}) => (
  <View
    style={{
      flexDirection: 'row',
      alignItems: 'center',
      justifyContent: 'space-between',
      marginTop: spacing.md,
      marginBottom: spacing.sm,
    }}
  >
    <H2>{title}</H2>
    {right ?? null}
  </View>
);

// A tappable entry on the departments hub. `subtitle` describes the screen.
export const DepartmentTile: React.FC<{
  title: string;
  subtitle: string;
  onPress: () => void;
  testID?: string;
}> = ({ title, subtitle, onPress, testID }) => {
  const c = useTheme();
  return (
    <Pressable onPress={onPress} testID={testID} accessibilityRole="button">
      {({ pressed }) => (
        <Card style={{ opacity: pressed ? 0.85 : 1 }}>
          <View
            style={{
              flexDirection: 'row',
              alignItems: 'center',
              justifyContent: 'space-between',
            }}
          >
            <View style={{ flex: 1, paddingRight: spacing.sm }}>
              <H2>{title}</H2>
              <Muted style={{ marginTop: spacing.xs }}>{subtitle}</Muted>
            </View>
            <Body style={{ color: c.textMuted, fontSize: 22 }}>›</Body>
          </View>
        </Card>
      )}
    </Pressable>
  );
};

// Renders loading skeletons, an error card (with offline-aware message) or an
// empty-state card. Returns `null` when there is data so the caller renders it.
export function DepartmentListState({
  loading,
  error,
  isEmpty,
  emptyText,
  skeletonCount = 3,
}: {
  loading: boolean;
  error: unknown;
  isEmpty: boolean;
  emptyText?: string;
  skeletonCount?: number;
}): React.ReactElement | null {
  if (loading) {
    return (
      <View style={{ gap: spacing.sm }}>
        {Array.from({ length: skeletonCount }).map((_, i) => (
          <SkeletonCard key={i} />
        ))}
      </View>
    );
  }
  if (error) {
    const msg = isOffline(error)
      ? tr.app.offline
      : errorMessage(error, tr.departments.loadError);
    return (
      <Card>
        <Body>{msg}</Body>
      </Card>
    );
  }
  if (isEmpty) {
    return (
      <Card>
        <Muted>{emptyText ?? tr.app.empty}</Muted>
      </Card>
    );
  }
  return null;
}
