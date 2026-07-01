import React from 'react';
import {
  ActivityIndicator,
  Animated,
  DimensionValue,
  Easing,
  GestureResponderEvent,
  Modal,
  Platform,
  Pressable,
  PressableProps,
  ScrollView,
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
import { cardShadow, motion, radius, spacing, useTheme } from '../theme';
import { haptic } from '../hooks/useHaptic';

// Hareket/haptik temelleri tek yerden cagrilabilsin diye kit bunlari yeniden
// ihrac eder (ekranlar `import { haptic, motion } from '../../src/components/ui'`).
export { haptic, motion };

type IoniconName = keyof typeof Ionicons.glyphMap;

// useNativeDriver web'de uyari uretir; transform/opacity icin native'de acik,
// web'de kapali calistir (animasyonlar her iki hedefte de guvenli).
const USE_NATIVE_DRIVER = Platform.OS !== 'web';

// Mobil uygulama web'de (Expo Web) genis masaustu ekranlarda (orn. 1024px+)
// tum genisligi kaplayip gerilir; mockup'lar ise telefon kolonu genisligindedir.
// `webCenter` ekran icerigini sabit bir maks. genislikte ortalar — yalnizca
// web'de etkin (native'de bos, telefonda zaten tam genislik). ScrollView
// `contentContainerStyle` dizisine eklenerek modul-modul yeniden kullanilir.
export const webMaxWidth = 600;
export const webCenter: ViewStyle =
  Platform.OS === 'web'
    ? ({ width: '100%', maxWidth: webMaxWidth, marginHorizontal: 'auto' } as ViewStyle)
    : {};

export const Screen: React.FC<ViewProps> = ({ style, children, ...rest }) => {
  const c = useTheme();
  return (
    <View style={[{ flex: 1, backgroundColor: c.bg, padding: spacing.lg }, style]} {...rest}>
      {children}
    </View>
  );
};

// Premium cam kart: 24px radius, yumusak yukseltili golge, ince beyaz kenarlik
// ve ust kenarda ince isik cizgisi (cam rim hissi) ile zeminden ayrilir.
// `accent` verilirse sol kenarda renkli durum cubugu cizer (status at-a-glance).
// `glass=false` ile rim isik cizgisi kapatilabilir (ic ice kartlar icin).
export const Card: React.FC<
  ViewProps & { accent?: string; elevated?: boolean; padded?: boolean; glass?: boolean }
> = ({ style, children, accent, elevated = true, padded = true, glass = true, ...rest }) => {
  const c = useTheme();
  return (
    <View
      style={[
        {
          backgroundColor: c.surface,
          borderRadius: radius.xl,
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
      {glass ? (
        <View
          pointerEvents="none"
          style={{
            position: 'absolute',
            top: 0,
            left: accent ? 4 : 0,
            right: 0,
            height: 1,
            backgroundColor: c.glassHighlight,
            borderTopLeftRadius: radius.xl,
            borderTopRightRadius: radius.xl,
          }}
        />
      ) : null}
      {children}
    </View>
  );
};

export const H1: React.FC<TextProps> = ({ style, ...rest }) => {
  const c = useTheme();
  return (
    <Text
      accessibilityRole="header"
      style={[
        { color: c.text, fontSize: 30, fontWeight: '800', letterSpacing: -0.6, lineHeight: 36 },
        style,
      ]}
      {...rest}
    />
  );
};

export const H2: React.FC<TextProps> = ({ style, ...rest }) => {
  const c = useTheme();
  return (
    <Text
      style={[
        { color: c.text, fontSize: 20, fontWeight: '700', letterSpacing: -0.3, lineHeight: 26 },
        style,
      ]}
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
  // Dokunusta hafif haptik geri bildirim (varsayilan acik). Web'de no-op.
  haptics?: boolean;
};

export const Button: React.FC<ButtonProps> = ({
  title,
  variant = 'primary',
  loading,
  fullWidth,
  icon,
  style,
  disabled,
  onPress,
  haptics = true,
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
  // Dolu (solid) varyantlarda primary renkten beslenen yumusak premium golge.
  const solid = variant === 'primary' || variant === 'success' || variant === 'danger';
  const glow = solid
    ? {
        shadowColor: p.bg,
        shadowOffset: { width: 0, height: 6 },
        shadowOpacity: 0.35,
        shadowRadius: 12,
        elevation: 4,
      }
    : null;

  const handlePress = (e: GestureResponderEvent) => {
    if (haptics) haptic.tap();
    onPress?.(e);
  };

  return (
    <Pressable
      accessibilityRole="button"
      accessibilityState={{ disabled: !!disabled || !!loading }}
      disabled={disabled || loading}
      onPress={handlePress}
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
          opacity: disabled ? 0.5 : pressed ? 0.9 : 1,
          transform: [{ scale: pressed ? 0.98 : 1 }],
          minHeight: 48,
          width: fullWidth ? '100%' : undefined,
        },
        disabled ? null : glow,
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
            backgroundColor: c.surfaceAlt,
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

// Yukleme iskeletI: surekli yumusak shimmer (opaklik nefesi) ile veri bekleyen
// yuzeyi premium gosterir. RN Animated kullanir (reanimated/babel-plugin'e
// bagimli degil) → Expo Web + native'de guvenli calisir.
export const Skeleton: React.FC<{
  height?: number;
  width?: DimensionValue;
  style?: StyleProp<ViewStyle>;
}> = ({ height = 16, width = '100%', style }) => {
  const c = useTheme();
  const shimmer = React.useRef(new Animated.Value(0)).current;
  React.useEffect(() => {
    const loop = Animated.loop(
      Animated.sequence([
        Animated.timing(shimmer, {
          toValue: 1,
          duration: motion.slow,
          easing: Easing.inOut(Easing.ease),
          useNativeDriver: USE_NATIVE_DRIVER,
        }),
        Animated.timing(shimmer, {
          toValue: 0,
          duration: motion.slow,
          easing: Easing.inOut(Easing.ease),
          useNativeDriver: USE_NATIVE_DRIVER,
        }),
      ]),
    );
    loop.start();
    return () => loop.stop();
  }, [shimmer]);
  const opacity = shimmer.interpolate({ inputRange: [0, 1], outputRange: [0.35, 0.85] });
  return (
    <Animated.View
      style={[
        {
          height,
          width,
          backgroundColor: c.surfaceAlt,
          borderRadius: radius.sm,
          opacity,
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

// Basari animasyonu: yesil daire icinde onay isareti, yumusak yay (spring) ile
// olceklenip belirir. Aksiyon tamamlandiginda (kayit/onay) tek yerden cagrilir.
// `onDone` animasyon bittiginde tetiklenir (ornegin sheet kapatmak icin).
// RN Animated → Expo Web + native'de guvenli.
export const SuccessCheck: React.FC<{
  size?: number;
  label?: string;
  onDone?: () => void;
  testID?: string;
}> = ({ size = 72, label, onDone, testID }) => {
  const c = useTheme();
  const scale = React.useRef(new Animated.Value(0)).current;
  React.useEffect(() => {
    const anim = Animated.spring(scale, {
      toValue: 1,
      friction: 6,
      tension: 90,
      useNativeDriver: USE_NATIVE_DRIVER,
    });
    anim.start(() => onDone?.());
    return () => anim.stop();
  }, [scale]);
  return (
    <View testID={testID} style={{ alignItems: 'center', justifyContent: 'center', gap: spacing.md }}>
      <Animated.View
        style={{
          width: size,
          height: size,
          borderRadius: radius.pill,
          backgroundColor: c.success + '22',
          alignItems: 'center',
          justifyContent: 'center',
          transform: [{ scale }],
        }}
      >
        <View
          style={{
            width: size * 0.66,
            height: size * 0.66,
            borderRadius: radius.pill,
            backgroundColor: c.success,
            alignItems: 'center',
            justifyContent: 'center',
          }}
        >
          <Ionicons name="checkmark" size={size * 0.4} color="#ffffff" />
        </View>
      </Animated.View>
      {label ? (
        <Text style={{ color: c.text, fontSize: 16, fontWeight: '700', textAlign: 'center' }}>
          {label}
        </Text>
      ) : null}
    </View>
  );
};

// Yumusak giris: cocugu hafif asagidan yukari + opaklikla belirtir. Liste/karti
// monte ederken premium "yumusak gecis" hissi verir. RN Animated → web-guvenli.
export const FadeInView: React.FC<ViewProps & { delay?: number; offsetY?: number }> = ({
  delay = 0,
  offsetY = 8,
  style,
  children,
  ...rest
}) => {
  const t = React.useRef(new Animated.Value(0)).current;
  React.useEffect(() => {
    const anim = Animated.timing(t, {
      toValue: 1,
      duration: motion.base,
      delay,
      easing: Easing.out(Easing.cubic),
      useNativeDriver: USE_NATIVE_DRIVER,
    });
    anim.start();
    return () => anim.stop();
  }, [t, delay]);
  const translateY = t.interpolate({ inputRange: [0, 1], outputRange: [offsetY, 0] });
  return (
    <Animated.View style={[{ opacity: t, transform: [{ translateY }] }, style]} {...rest}>
      {children}
    </Animated.View>
  );
};

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

// ── Section header (Task #454) ─────────────────────────────────────────────
// Title for a block of content (a list group, a report section). Optional
// `right` slot for a small action (e.g. "Tümünü gör"). This is the single
// canonical source; `components/department.tsx` re-exports it for back-compat.
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

// ── Section-titled list group (Task #454) ──────────────────────────────────
// Standard "section header + grouped rows" pattern. Wrap `ListRow`s (or any
// rows) as children; they sit inside a single `Card padded={false}` so the
// hairline dividers ListRow draws line up. Pass `last` on the final ListRow to
// drop its trailing divider. Optional `footer` renders below the rows inside
// the same card (e.g. a "load more" affordance).
export const ListGroup: React.FC<{
  title?: string;
  right?: React.ReactNode;
  footer?: React.ReactNode;
  children: React.ReactNode;
  testID?: string;
}> = ({ title, right, footer, children, testID }) => (
  <View testID={testID}>
    {title ? <SectionTitle title={title} right={right} /> : null}
    <Card padded={false}>
      {children}
      {footer ?? null}
    </Card>
  </View>
);

// ── Detail header block (Task #454) ────────────────────────────────────────
// Standard top-of-detail-screen header: big title, optional muted subtitle, an
// optional row of badges (status / tags) and an optional `right` slot for a
// primary affordance. Keeps every detail screen's masthead identical.
export const DetailHeader: React.FC<{
  title: string;
  subtitle?: string;
  badges?: React.ReactNode;
  right?: React.ReactNode;
  testID?: string;
}> = ({ title, subtitle, badges, right, testID }) => (
  <View style={{ marginBottom: spacing.md }} testID={testID}>
    <View style={{ flexDirection: 'row', alignItems: 'flex-start', gap: spacing.md }}>
      <View style={{ flex: 1 }}>
        <H1>{title}</H1>
        {subtitle ? <Muted style={{ marginTop: spacing.xs }}>{subtitle}</Muted> : null}
      </View>
      {right ?? null}
    </View>
    {badges ? (
      <View
        style={{
          flexDirection: 'row',
          flexWrap: 'wrap',
          gap: spacing.xs,
          marginTop: spacing.sm,
        }}
      >
        {badges}
      </View>
    ) : null}
  </View>
);

// ── Detail field row (Task #454) ───────────────────────────────────────────
// A label / value line for detail bodies. Stacks label above value so long
// Turkish values wrap cleanly. Pair several inside a `Card`.
export const DetailRow: React.FC<{
  label: string;
  value?: string | null;
  children?: React.ReactNode;
}> = ({ label, value, children }) => {
  const c = useTheme();
  return (
    <View style={{ paddingVertical: 6 }}>
      <Text style={{ color: c.textMuted, fontSize: 12, fontWeight: '600' }}>{label}</Text>
      {children ?? (
        <Text style={{ color: c.text, fontSize: 15, marginTop: 2 }}>{value ?? '—'}</Text>
      )}
    </View>
  );
};

// ── Thumb-zone action button + segmented bar (Task #454) ───────────────────
// Lifted from the Onaylarım (approvals) screen so every screen shares one
// segmented action control. `ActionButton` is a big (52px) half; pass explicit
// `bg`/`fg` (theme tokens) so callers tune intent. `SegmentedActions` joins N
// buttons edge-to-edge with 1px dividers and rounded outer corners (no gaps).
export const ActionButton: React.FC<{
  label: string;
  icon?: IoniconName;
  onPress: () => void;
  bg: string;
  fg: string;
  loading?: boolean;
  disabled?: boolean;
  testID?: string;
}> = ({ label, icon, onPress, bg, fg, loading, disabled, testID }) => (
  <Pressable
    testID={testID}
    onPress={() => {
      haptic.tap();
      onPress();
    }}
    disabled={disabled || loading}
    accessibilityRole="button"
    accessibilityLabel={label}
    accessibilityState={{ disabled: !!disabled || !!loading }}
    style={({ pressed }) => ({
      flex: 1,
      minHeight: 52,
      flexDirection: 'row',
      alignItems: 'center',
      justifyContent: 'center',
      gap: spacing.xs,
      backgroundColor: bg,
      opacity: disabled ? 0.5 : pressed ? 0.85 : 1,
    })}
  >
    {loading ? (
      <ActivityIndicator color={fg} />
    ) : (
      <>
        {icon ? <Ionicons name={icon} size={18} color={fg} /> : null}
        <Text style={{ color: fg, fontSize: 16, fontWeight: '700' }}>{label}</Text>
      </>
    )}
  </Pressable>
);

export const SegmentedActions: React.FC<{ children: React.ReactNode; testID?: string }> = ({
  children,
  testID,
}) => {
  const c = useTheme();
  const items = React.Children.toArray(children);
  return (
    <View
      testID={testID}
      style={{
        flexDirection: 'row',
        borderRadius: radius.md,
        overflow: 'hidden',
        borderWidth: 1,
        borderColor: c.border,
      }}
    >
      {items.map((child, idx) => (
        <React.Fragment key={idx}>
          {idx > 0 ? <View style={{ width: 1, backgroundColor: c.border }} /> : null}
          {child}
        </React.Fragment>
      ))}
    </View>
  );
};

// ── Action sheet (Task #454) ───────────────────────────────────────────────
// Bottom-anchored modal for a short list of actions or a compact form. Uses
// RN `Modal` (works on Expo Web + native). Tapping the dimmed backdrop closes.
// Put `Button`s / `ListRow`s / `Field`s as children.
export const ActionSheet: React.FC<{
  visible: boolean;
  onClose: () => void;
  title?: string;
  children: React.ReactNode;
  testID?: string;
}> = ({ visible, onClose, title, children, testID }) => {
  const c = useTheme();
  return (
    <Modal
      visible={visible}
      transparent
      animationType="slide"
      onRequestClose={onClose}
      statusBarTranslucent
    >
      <Pressable
        onPress={onClose}
        accessibilityLabel={title}
        style={{ flex: 1, backgroundColor: 'rgba(0,0,0,0.45)', justifyContent: 'flex-end' }}
      >
        {/* Stop the inner press from bubbling to the backdrop dismiss. */}
        <Pressable
          onPress={() => {}}
          testID={testID}
          style={{
            backgroundColor: c.surface,
            borderTopLeftRadius: radius.xl,
            borderTopRightRadius: radius.xl,
            paddingHorizontal: spacing.lg,
            paddingTop: spacing.md,
            paddingBottom: spacing.xl,
            gap: spacing.sm,
          }}
        >
          <View
            style={{
              alignSelf: 'center',
              width: 44,
              height: 5,
              borderRadius: radius.pill,
              backgroundColor: c.border,
              marginBottom: spacing.sm,
            }}
          />
          {title ? <H2 style={{ marginBottom: spacing.xs }}>{title}</H2> : null}
          <ScrollView
            keyboardShouldPersistTaps="handled"
            contentContainerStyle={{ gap: spacing.sm }}
            style={{ maxHeight: 480 }}
          >
            {children}
          </ScrollView>
        </Pressable>
      </Pressable>
    </Modal>
  );
};

// ── Form action row (Task #454) ────────────────────────────────────────────
// A row of buttons for the bottom of a form (e.g. Vazgeç / Kaydet). Children
// share the row width evenly; pass `fullWidth` on each `Button`.
export const FormActions: React.FC<{ children: React.ReactNode }> = ({ children }) => {
  const items = React.Children.toArray(children);
  return (
    <View style={{ flexDirection: 'row', gap: spacing.sm }}>
      {items.map((child, idx) => (
        <View key={idx} style={{ flex: 1 }}>
          {child}
        </View>
      ))}
    </View>
  );
};

export const styles = StyleSheet.create({});
