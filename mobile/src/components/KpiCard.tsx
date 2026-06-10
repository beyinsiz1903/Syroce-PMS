import React from 'react';
import { View } from 'react-native';
import { Card } from './ui';
import { radius, spacing, useTheme } from '../theme';
import { Text } from 'react-native';

export type KpiTone = 'default' | 'success' | 'warning' | 'danger' | 'info';
export type KpiTrend = 'up' | 'down' | 'flat';

// A single live KPI tile for the manager dashboard. Designed for a 2-column
// grid: callers wrap pairs in a flex row. `delta` shows an at-a-glance
// comparison (e.g. vs. yesterday) with a coloured up/down marker.
export const KpiCard: React.FC<{
  label: string;
  value: string;
  delta?: string;
  trend?: KpiTrend;
  tone?: KpiTone;
  testID?: string;
}> = ({ label, value, delta, trend, tone = 'default', testID }) => {
  const c = useTheme();
  const valueColor = {
    default: c.text,
    success: c.success,
    warning: c.warning,
    danger: c.danger,
    info: c.info,
  }[tone];
  const trendColor =
    trend === 'up' ? c.success : trend === 'down' ? c.danger : c.textMuted;
  const marker = trend === 'up' ? '▲' : trend === 'down' ? '▼' : '•';

  return (
    <Card style={{ flex: 1 }} testID={testID}>
      <Text style={{ color: c.textMuted, fontSize: 12, fontWeight: '600' }} numberOfLines={1}>
        {label}
      </Text>
      <Text
        style={{ color: valueColor, fontSize: 22, fontWeight: '700', marginTop: spacing.xs }}
        numberOfLines={1}
        adjustsFontSizeToFit
      >
        {value}
      </Text>
      {delta ? (
        <View
          style={{
            flexDirection: 'row',
            alignItems: 'center',
            gap: 4,
            marginTop: spacing.xs,
          }}
        >
          <Text style={{ color: trendColor, fontSize: 11 }}>{marker}</Text>
          <Text style={{ color: c.textMuted, fontSize: 11 }} numberOfLines={1}>
            {delta}
          </Text>
        </View>
      ) : null}
    </Card>
  );
};

// Two KPI cards side by side. Keeps the grid math in one place.
export const KpiRow: React.FC<{ children: React.ReactNode }> = ({ children }) => (
  <View style={{ flexDirection: 'row', gap: spacing.md }}>{children}</View>
);

// Compact pill used to label aging / segment breakdown buckets.
export const KpiPill: React.FC<{ label: string; tone?: KpiTone }> = ({ label, tone = 'default' }) => {
  const c = useTheme();
  const color = {
    default: c.textMuted,
    success: c.success,
    warning: c.warning,
    danger: c.danger,
    info: c.info,
  }[tone];
  return (
    <View
      style={{
        paddingHorizontal: spacing.sm,
        paddingVertical: 2,
        borderRadius: radius.sm,
        backgroundColor: color + '22',
        borderWidth: 1,
        borderColor: color,
        alignSelf: 'flex-start',
      }}
    >
      <Text style={{ color, fontSize: 11, fontWeight: '600' }}>{label}</Text>
    </View>
  );
};
