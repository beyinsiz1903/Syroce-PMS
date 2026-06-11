import React from 'react';
import {
  ActivityIndicator,
  DimensionValue,
  Pressable,
  PressableProps,
  StyleProp,
  StyleSheet,
  Text,
  TextInput,
  TextInputProps,
  TextProps,
  View,
  ViewProps,
  ViewStyle,
} from 'react-native';
import { Ionicons } from '@expo/vector-icons';
import { cardShadow, radius, spacing, useTheme } from '../theme';

type IoniconName = keyof typeof Ionicons.glyphMap;

export const Screen: React.FC<ViewProps> = ({ style, children, ...rest }) => {
  const c = useTheme();
  return (
    <View style={[{ flex: 1, backgroundColor: c.bg, padding: spacing.lg }, style]} {...rest}>
      {children}
    </View>
  );
};

// Kart: scannability icin yumusak yukselti + radius.lg. `accent` verilirse sol
// kenarda renkli durum cubugu cizer (urgency / status at-a-glance).
export const Card: React.FC<ViewProps & { accent?: string; elevated?: boolean; padded?: boolean }> = ({
  style,
  children,
  accent,
  elevated = true,
  padded = true,
  ...rest
}) => {
  const c = useTheme();
  return (
    <View
      style={[
        {
          backgroundColor: c.surface,
          borderRadius: radius.lg,
          padding: padded ? spacing.lg : 0,
          borderWidth: 1,
          borderColor: c.border,
        },
        accent ? { borderLeftWidth: 4, borderLeftColor: accent } : null,
        elevated ? cardShadow : null,
        style,
      ]}
      {...rest}
    >
      {children}
    </View>
  );
};

export const H1: React.FC<TextProps> = ({ style, ...rest }) => {
  const c = useTheme();
  return (
    <Text
      accessibilityRole="header"
      style={[{ color: c.text, fontSize: 26, fontWeight: '800', letterSpacing: -0.3 }, style]}
      {...rest}
    />
  );
};

export const H2: React.FC<TextProps> = ({ style, ...rest }) => {
  const c = useTheme();
  return (
    <Text
      style={[{ color: c.text, fontSize: 18, fontWeight: '700', letterSpacing: -0.2 }, style]}
      {...rest}
    />
  );
};

export const Body: React.FC<TextProps> = ({ style, ...rest }) => {
  const c = useTheme();
  return <Text style={[{ color: c.text, fontSize: 15 }, style]} {...rest} />;
};

export const Muted: React.FC<TextProps> = ({ style, ...rest }) => {
  const c = useTheme();
  return <Text style={[{ color: c.textMuted, fontSize: 13 }, style]} {...rest} />;
};

type ButtonVariant = 'primary' | 'secondary' | 'success' | 'danger' | 'outline' | 'ghost';

type ButtonProps = PressableProps & {
  title: string;
  variant?: ButtonVariant;
  loading?: boolean;
  fullWidth?: boolean;
  icon?: IoniconName;
};

export const Button: React.FC<ButtonProps> = ({
  title,
  variant = 'primary',
  loading,
  fullWidth,
  icon,
  style,
  disabled,
  ...rest
}) => {
  const c = useTheme();
  const palette: Record<ButtonVariant, { bg: string; text: string; border: string }> = {
    primary: { bg: c.primary, text: c.primaryText, border: c.primary },
    secondary: { bg: c.surfaceAlt, text: c.text, border: c.border },
    success: { bg: c.success, text: '#ffffff', border: c.success },
    danger: { bg: c.danger, text: '#ffffff', border: c.danger },
    outline: { bg: 'transparent', text: c.text, border: c.border },
    ghost: { bg: 'transparent', text: c.primary, border: 'transparent' },
  };
  const p = palette[variant];

  return (
    <Pressable
      accessibilityRole="button"
      accessibilityState={{ disabled: !!disabled || !!loading }}
      disabled={disabled || loading}
      style={({ pressed }) => [
        {
          backgroundColor: p.bg,
          borderColor: p.border,
          borderWidth: 1,
          paddingVertical: spacing.md,
          paddingHorizontal: spacing.lg,
          borderRadius: radius.md,
          alignItems: 'center',
          justifyContent: 'center',
          opacity: disabled ? 0.5 : pressed ? 0.85 : 1,
          minHeight: 48,
          width: fullWidth ? '100%' : undefined,
        },
        typeof style === 'function' ? style({ pressed }) : style,
      ]}
      {...rest}
    >
      {loading ? (
        <ActivityIndicator color={p.text} />
      ) : (
        <View style={{ flexDirection: 'row', alignItems: 'center', justifyContent: 'center', gap: spacing.xs }}>
          {icon ? <Ionicons name={icon} size={18} color={p.text} /> : null}
          <Text style={{ color: p.text, fontSize: 16, fontWeight: '700' }}>{title}</Text>
        </View>
      )}
    </Pressable>
  );
};

export const Field: React.FC<TextInputProps & { label?: string }> = ({ label, style, ...rest }) => {
  const c = useTheme();
  return (
    <View style={{ gap: spacing.xs }}>
      {label ? <Muted>{label}</Muted> : null}
      <TextInput
        placeholderTextColor={c.textMuted}
        style={[
          {
            backgroundColor: c.surface,
            color: c.text,
            borderColor: c.border,
            borderWidth: 1,
            borderRadius: radius.md,
            padding: spacing.md,
            fontSize: 16,
            minHeight: 48,
          },
          style,
        ]}
        {...rest}
      />
    </View>
  );
};

type BadgeTone = 'default' | 'success' | 'warning' | 'danger' | 'info' | 'vip' | 'primary';

type BadgeProps = {
  label: string;
  tone?: BadgeTone;
  icon?: IoniconName;
};

// Durum rozeti: yuvarlak pill, renkli tint zemin + renkli metin (shadcn hissi).
export const Badge: React.FC<BadgeProps> = ({ label, tone = 'default', icon }) => {
  const c = useTheme();
  const map: Record<BadgeTone, string> = {
    default: c.textMuted,
    success: c.success,
    warning: c.warning,
    danger: c.danger,
    info: c.info,
    vip: c.vip,
    primary: c.primary,
  };
  const color = map[tone];
  return (
    <View
      style={{
        flexDirection: 'row',
        alignItems: 'center',
        gap: 4,
        paddingHorizontal: spacing.sm,
        paddingVertical: 3,
        borderRadius: radius.pill,
        backgroundColor: color + '1f',
        alignSelf: 'flex-start',
      }}
    >
      {icon ? <Ionicons name={icon} size={12} color={color} /> : null}
      <Text style={{ color, fontSize: 11, fontWeight: '700', letterSpacing: 0.2 }}>{label}</Text>
    </View>
  );
};

export const Skeleton: React.FC<{
  height?: number;
  width?: DimensionValue;
  style?: StyleProp<ViewStyle>;
}> = ({ height = 16, width = '100%', style }) => {
  const c = useTheme();
  return (
    <View
      style={[
        {
          height,
          width,
          backgroundColor: c.surfaceAlt,
          borderRadius: radius.sm,
          opacity: 0.7,
        },
        style,
      ]}
    />
  );
};

export const SkeletonCard: React.FC = () => (
  <Card>
    <Skeleton height={18} width="60%" />
    <View style={{ height: spacing.sm }} />
    <Skeleton height={14} width="80%" />
    <View style={{ height: spacing.sm }} />
    <Skeleton height={14} width="40%" />
  </Card>
);

export const Divider: React.FC = () => {
  const c = useTheme();
  return <View style={{ height: 1, backgroundColor: c.border, marginVertical: spacing.md }} />;
};

// Bos durum: ikon (yumusak daire icinde) + neseli Turkce metin. Placeholder
// gorsel KULLANILMAZ (expo doktrini). Istege bagli aksiyon (buton vb.).
export const EmptyState: React.FC<{
  icon?: IoniconName;
  title: string;
  message?: string;
  action?: React.ReactNode;
  testID?: string;
}> = ({ icon = 'sparkles-outline', title, message, action, testID }) => {
  const c = useTheme();
  return (
    <View
      testID={testID}
      style={{
        alignItems: 'center',
        justifyContent: 'center',
        paddingVertical: spacing.xxl,
        paddingHorizontal: spacing.xl,
        gap: spacing.md,
      }}
    >
      <View
        style={{
          width: 88,
          height: 88,
          borderRadius: radius.pill,
          backgroundColor: c.primarySoft,
          alignItems: 'center',
          justifyContent: 'center',
        }}
      >
        <Ionicons name={icon} size={40} color={c.primary} />
      </View>
      <Text style={{ color: c.text, fontSize: 18, fontWeight: '700', textAlign: 'center' }}>{title}</Text>
      {message ? (
        <Text style={{ color: c.textMuted, fontSize: 14, textAlign: 'center', lineHeight: 20 }}>
          {message}
        </Text>
      ) : null}
      {action ? <View style={{ marginTop: spacing.sm }}>{action}</View> : null}
    </View>
  );
};

// Apple "Ayarlar" tarzi liste satiri: solda yumusak tintli daire icinde ikon,
// ortada baslik (+ istege bagli alt baslik), sagda istege bagli deger ile
// chevron (veya `active` ise onay isareti). Bir `Card padded={false}` icine
// dizilir; satirlar arasi ince, ikon hizasindan baslayan ic-girintili ayrac.
export const ListRow: React.FC<{
  icon: IoniconName;
  iconColor?: string;
  label: string;
  sublabel?: string;
  value?: string;
  onPress?: () => void;
  active?: boolean;
  showChevron?: boolean;
  last?: boolean;
  right?: React.ReactNode;
  testID?: string;
  accessibilityLabel?: string;
}> = ({
  icon,
  iconColor,
  label,
  sublabel,
  value,
  onPress,
  active,
  showChevron = true,
  last,
  right,
  testID,
  accessibilityLabel,
}) => {
  const c = useTheme();
  const tint = iconColor ?? c.primary;
  const inner = (
    <>
      <View
        style={{
          flexDirection: 'row',
          alignItems: 'center',
          gap: spacing.md,
          paddingHorizontal: spacing.lg,
          paddingVertical: 14,
          minHeight: 56,
          backgroundColor: active ? c.primarySoft : 'transparent',
        }}
      >
        <View
          style={{
            width: 36,
            height: 36,
            borderRadius: radius.pill,
            backgroundColor: tint + '1f',
            alignItems: 'center',
            justifyContent: 'center',
          }}
        >
          <Ionicons name={icon} size={20} color={tint} />
        </View>
        <View style={{ flex: 1 }}>
          <Text style={{ color: c.text, fontSize: 15, fontWeight: '600' }} numberOfLines={1}>
            {label}
          </Text>
          {sublabel ? (
            <Text style={{ color: c.textMuted, fontSize: 12, marginTop: 1 }} numberOfLines={1}>
              {sublabel}
            </Text>
          ) : null}
        </View>
        {value ? (
          <Text style={{ color: c.textMuted, fontSize: 14 }} numberOfLines={1}>
            {value}
          </Text>
        ) : null}
        {right ?? null}
        {active ? (
          <Ionicons name="checkmark" size={20} color={c.primary} />
        ) : showChevron && onPress ? (
          <Ionicons name="chevron-forward" size={18} color={c.textMuted} />
        ) : null}
      </View>
      {!last ? (
        <View
          style={{
            height: StyleSheet.hairlineWidth,
            backgroundColor: c.border,
            marginLeft: spacing.lg + 36 + spacing.md,
          }}
        />
      ) : null}
    </>
  );

  if (!onPress) return <View testID={testID}>{inner}</View>;
  return (
    <Pressable
      testID={testID}
      onPress={onPress}
      accessibilityRole="button"
      accessibilityLabel={accessibilityLabel ?? label}
      style={({ pressed }) => [{ opacity: pressed ? 0.6 : 1 }]}
    >
      {inner}
    </Pressable>
  );
};

export const styles = StyleSheet.create({});
