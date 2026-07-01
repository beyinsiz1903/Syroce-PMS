import React from 'react';
import { Text, View } from 'react-native';
import { spacing, useTheme } from '../theme';

export type StatTone = 'default' | 'success' | 'warning' | 'danger' | 'info';

// A label / value row used inside report cards (finance snapshot, aging
// buckets, segment stats). Keeps spacing + colour consistent across reports.
export const StatRow: React.FC<{
  label: string;
  value: string;
  tone?: StatTone;
  strong?: boolean;
}> = ({ label, value, tone = 'default', strong }) => {
  const c = useTheme();
  const valueColor = {
    default: c.text,
    success: c.success,
    warning: c.warning,
    danger: c.danger,
    info: c.info,
  }[tone];
  return (
    <View
      style={{
        flexDirection: 'row',
        justifyContent: 'space-between',
        alignItems: 'center',
        gap: spacing.md,
        paddingVertical: 6,
      }}
    >
      <Text style={{ color: c.textMuted, fontSize: 14, flex: 1 }} numberOfLines={2}>
        {label}
      </Text>
      <Text
        style={{
          color: valueColor,
          fontSize: strong ? 16 : 14,
          fontWeight: strong ? '700' : '600',
          textAlign: 'right',
        }}
      >
        {value}
      </Text>
    </View>
  );
};
