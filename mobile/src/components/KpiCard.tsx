import React from 'react';
import { View } from 'react-native';
import { Ionicons } from '@expo/vector-icons';
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
  icon?: keyof typeof Ionicons.glyphMap;
  testID?: string;
}> = ({ label, value, delta, trend, tone = 'default', icon, testID }) => {
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
  const trendIcon: keyof typeof Ionicons.glyphMap =
    trend === 'up' ? 'trending-up' : trend === 'down' ? 'trending-down' : 'remove';

  // Hero (kokpit) modu yalnizca `icon` verildiginde devreye girer: buyuk kalin
  // sayi USTTE, kucuk soluk label ALTTA, sag-altta dusuk-opaklikli watermark
  // ikon. `icon` verilmediginde tum davranis birebir korunur (GM dashboard).
  const hero = !!icon;

  return (
    <Card
      style={{ flex: 1, ...(hero ? { overflow: 'hidden', minHeight: 116 } : null) }}
      testID={testID}
    >
      {icon ? (
        <View
          pointerEvents="none"
          style={{ position: 'absolute', right: -8, bottom: -12, opacity: 0.1 }}
        >
          <Ionicons name={icon} size={92} color={valueColor} />
        </View>
      ) : null}
      {hero ? (
        <>
          <Text
            style={{ color: valueColor, fontSize: 40, fontWeight: '800', letterSpacing: -1 }}
            numberOfLines={1}
            adjustsFontSizeToFit
          >
            {value}
          </Text>
          <Text
            style={{ color: c.textMuted, fontSize: 13, fontWeight: '600', marginTop: spacing.xs }}
            numberOfLines={1}
          >
            {label}
          </Text>
        </>
      ) : (
        <>
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
              <Ionicons name={trendIcon} size={12} color={trendColor} />
              <Text style={{ color: c.textMuted, fontSize: 11 }} numberOfLines={1}>
                {delta}
              </Text>
            </View>
          ) : null}
        </>
      )}
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
