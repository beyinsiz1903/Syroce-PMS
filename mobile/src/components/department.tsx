import React from 'react';
import { Pressable, View } from 'react-native';
import { Ionicons } from '@expo/vector-icons';
import { Body, Card, Muted, SkeletonCard } from './ui';
import { radius, spacing, useTheme } from '../theme';
import { tr } from '../i18n/tr';
import { errorMessage, isOffline } from '../utils/errors';
import { listViewState } from '../utils/departmentScreens';

// Shared widgets for the (departments) area so sibling department screens
// (Spa, MICE, and the upcoming Accounting / Maintenance task) render loading,
// empty and error states identically without copy-pasting layout.

// SectionTitle now lives in the shared kit (components/ui.tsx, Task #454).
// Re-exported here so existing `from '.../components/department'` imports keep
// working unchanged.
export { SectionTitle } from './ui';

// A tappable entry on the departments hub. `subtitle` describes the screen.
export const DepartmentTile: React.FC<{
  title: string;
  subtitle: string;
  onPress: () => void;
  testID?: string;
  icon?: keyof typeof Ionicons.glyphMap;
  disabled?: boolean;
  statusText?: string;
  grouped?: boolean;
  last?: boolean;
}> = ({ title, subtitle, onPress, testID, icon, disabled, statusText, grouped, last }) => {
  const c = useTheme();
  const content = (
    <View style={{ flexDirection: 'row', alignItems: 'center', gap: spacing.md }}>
      {icon ? (
        <View style={{ width: 40, height: 40, borderRadius: radius.md, backgroundColor: disabled ? c.surfaceAlt : c.primarySoft, alignItems: 'center', justifyContent: 'center' }}>
          <Ionicons name={icon} size={22} color={disabled ? c.textMuted : c.primary} />
        </View>
      ) : null}
      <View style={{ flex: 1, gap: 3 }}>
        <Body style={{ fontWeight: '700' }}>{title}</Body>
        <Muted numberOfLines={2}>{subtitle}</Muted>
        {statusText ? <Muted style={{ color: c.textMuted, fontSize: 12, fontWeight: '600' }}>{statusText}</Muted> : null}
      </View>
      <Ionicons name={disabled ? 'lock-closed-outline' : 'chevron-forward'} size={18} color={disabled ? c.textMuted : c.primary} />
    </View>
  );
  return (
    <Pressable
      onPress={onPress}
      disabled={disabled}
      testID={testID}
      accessibilityRole="button"
      accessibilityLabel={[title, subtitle, statusText].filter(Boolean).join('. ')}
      accessibilityState={{ disabled: !!disabled }}
    >
      {({ pressed }) => grouped ? (
        <View style={{ minHeight: 88, padding: spacing.lg, borderBottomWidth: last ? 0 : 1, borderBottomColor: c.border, opacity: pressed ? 0.75 : 1 }}>{content}</View>
      ) : (
        <Card style={{ opacity: pressed ? 0.75 : 1 }}>{content}</Card>
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
  // Branch order (loading → error → empty → data) lives in `listViewState` so
  // it is unit-tested once and shared identically across department screens.
  const state = listViewState({ loading, error, isEmpty });
  if (state === 'loading') {
    return (
      <View style={{ gap: spacing.sm }}>
        {Array.from({ length: skeletonCount }).map((_, i) => (
          <SkeletonCard key={i} />
        ))}
      </View>
    );
  }
  if (state === 'error') {
    const msg = isOffline(error)
      ? tr.app.offline
      : errorMessage(error, tr.departments.loadError);
    return (
      <Card>
        <Body>{msg}</Body>
      </Card>
    );
  }
  if (state === 'empty') {
    return (
      <Card>
        <Muted>{emptyText ?? tr.app.empty}</Muted>
      </Card>
    );
  }
  return null;
}
