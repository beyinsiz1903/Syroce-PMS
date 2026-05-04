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
import { radius, spacing, useTheme } from '../theme';

export const Screen: React.FC<ViewProps> = ({ style, children, ...rest }) => {
  const c = useTheme();
  return (
    <View style={[{ flex: 1, backgroundColor: c.bg, padding: spacing.lg }, style]} {...rest}>
      {children}
    </View>
  );
};

export const Card: React.FC<ViewProps> = ({ style, children, ...rest }) => {
  const c = useTheme();
  return (
    <View
      style={[
        {
          backgroundColor: c.surface,
          borderRadius: radius.md,
          padding: spacing.lg,
          borderWidth: 1,
          borderColor: c.border,
        },
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
      style={[{ color: c.text, fontSize: 24, fontWeight: '700' }, style]}
      {...rest}
    />
  );
};

export const H2: React.FC<TextProps> = ({ style, ...rest }) => {
  const c = useTheme();
  return (
    <Text
      style={[{ color: c.text, fontSize: 18, fontWeight: '600' }, style]}
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

type ButtonProps = PressableProps & {
  title: string;
  variant?: 'primary' | 'secondary' | 'danger' | 'ghost';
  loading?: boolean;
  fullWidth?: boolean;
};

export const Button: React.FC<ButtonProps> = ({
  title,
  variant = 'primary',
  loading,
  fullWidth,
  style,
  disabled,
  ...rest
}) => {
  const c = useTheme();
  const palette = {
    primary: { bg: c.primary, text: c.primaryText, border: c.primary },
    secondary: { bg: c.surfaceAlt, text: c.text, border: c.border },
    danger: { bg: c.danger, text: c.primaryText, border: c.danger },
    ghost: { bg: 'transparent', text: c.primary, border: 'transparent' },
  }[variant];

  return (
    <Pressable
      accessibilityRole="button"
      accessibilityState={{ disabled: !!disabled || !!loading }}
      disabled={disabled || loading}
      style={({ pressed }) => [
        {
          backgroundColor: palette.bg,
          borderColor: palette.border,
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
        <ActivityIndicator color={palette.text} />
      ) : (
        <Text style={{ color: palette.text, fontSize: 16, fontWeight: '600' }}>{title}</Text>
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

type BadgeProps = {
  label: string;
  tone?: 'default' | 'success' | 'warning' | 'danger' | 'info' | 'vip' | 'primary';
};

export const Badge: React.FC<BadgeProps> = ({ label, tone = 'default' }) => {
  const c = useTheme();
  const map = {
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

export const styles = StyleSheet.create({});
