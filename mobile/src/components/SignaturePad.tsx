import React, {
  forwardRef,
  useCallback,
  useImperativeHandle,
  useMemo,
  useRef,
  useState,
} from 'react';
import {
  GestureResponderEvent,
  LayoutChangeEvent,
  PanResponder,
  PanResponderGestureState,
  PanResponderInstance,
  Pressable,
  View,
  ViewStyle,
} from 'react-native';
import Svg, { Path } from 'react-native-svg';
import { radius, spacing, useTheme } from '../theme';
import { tr } from '../i18n/tr';
import { Body, Muted } from './ui';

export type SignaturePadHandle = {
  clear: () => void;
  isEmpty: () => boolean;
  exportSvg: () => string | null;
};

type Point = { x: number; y: number };
type Stroke = Point[];

type SignaturePadProps = {
  onChange?: (svg: string | null) => void;
  height?: number;
  strokeColor?: string;
  strokeWidth?: number;
  clearLabel?: string;
  style?: ViewStyle;
};

function strokeToPath(stroke: Stroke): string {
  if (stroke.length === 0) return '';
  const [first, ...rest] = stroke;
  if (rest.length === 0) {
    // Single tap: render a tiny line so it shows up.
    return `M ${first.x} ${first.y} L ${first.x + 0.1} ${first.y + 0.1}`;
  }
  let d = `M ${first.x} ${first.y}`;
  for (const p of rest) {
    d += ` L ${p.x} ${p.y}`;
  }
  return d;
}

function buildSvg(
  strokes: Stroke[],
  width: number,
  height: number,
  color: string,
  strokeWidth: number,
): string {
  const paths = strokes
    .filter((s) => s.length > 0)
    .map(
      (s) =>
        `<path d="${strokeToPath(s)}" stroke="${color}" stroke-width="${strokeWidth}" stroke-linecap="round" stroke-linejoin="round" fill="none" />`,
    )
    .join('');
  return `<svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 ${width} ${height}" width="${width}" height="${height}">${paths}</svg>`;
}

export const SignaturePad = forwardRef<SignaturePadHandle, SignaturePadProps>(
  function SignaturePad(
    {
      onChange,
      height = 180,
      strokeColor,
      strokeWidth = 2.5,
      clearLabel = tr.guest.signatureClear,
      style,
    },
    ref,
  ) {
    const c = useTheme();
    const ink = strokeColor ?? c.text;
    const [strokes, setStrokes] = useState<Stroke[]>([]);
    const [size, setSize] = useState<{ w: number; h: number }>({ w: 0, h: height });
    const currentStroke = useRef<Stroke | null>(null);

    const emit = useCallback(
      (next: Stroke[]) => {
        if (!onChange) return;
        const nonEmpty = next.filter((s) => s.length > 0);
        if (nonEmpty.length === 0 || size.w === 0) {
          onChange(null);
          return;
        }
        onChange(buildSvg(nonEmpty, size.w, size.h, ink, strokeWidth));
      },
      [onChange, size.w, size.h, ink, strokeWidth],
    );

    const pointFrom = useCallback((evt: GestureResponderEvent): Point => {
      const { locationX, locationY } = evt.nativeEvent;
      return { x: Math.max(0, locationX), y: Math.max(0, locationY) };
    }, []);

    const responder: PanResponderInstance = useMemo(
      () =>
        PanResponder.create({
          onStartShouldSetPanResponder: () => true,
          onMoveShouldSetPanResponder: () => true,
          onPanResponderTerminationRequest: () => false,
          onPanResponderGrant: (evt: GestureResponderEvent) => {
            const p = pointFrom(evt);
            currentStroke.current = [p];
            setStrokes((prev) => [...prev, [p]]);
          },
          onPanResponderMove: (
            evt: GestureResponderEvent,
            _gs: PanResponderGestureState,
          ) => {
            if (!currentStroke.current) return;
            const p = pointFrom(evt);
            currentStroke.current.push(p);
            // Mutate the last stroke in place for performance, then trigger
            // a re-render by replacing the array reference.
            setStrokes((prev) => {
              if (prev.length === 0) return prev;
              const next = prev.slice();
              next[next.length - 1] = currentStroke.current!.slice();
              return next;
            });
          },
          onPanResponderRelease: () => {
            currentStroke.current = null;
            setStrokes((prev) => {
              emit(prev);
              return prev;
            });
          },
          onPanResponderTerminate: () => {
            currentStroke.current = null;
            setStrokes((prev) => {
              emit(prev);
              return prev;
            });
          },
        }),
      [pointFrom, emit],
    );

    const onLayout = useCallback(
      (e: LayoutChangeEvent) => {
        const { width: w, height: h } = e.nativeEvent.layout;
        if (w !== size.w || h !== size.h) {
          setSize({ w, h });
        }
      },
      [size.w, size.h],
    );

    useImperativeHandle(
      ref,
      () => ({
        clear: () => {
          currentStroke.current = null;
          setStrokes([]);
          if (onChange) onChange(null);
        },
        isEmpty: () => strokes.every((s) => s.length === 0),
        exportSvg: () => {
          const nonEmpty = strokes.filter((s) => s.length > 0);
          if (nonEmpty.length === 0 || size.w === 0) return null;
          return buildSvg(nonEmpty, size.w, size.h, ink, strokeWidth);
        },
      }),
      [strokes, size.w, size.h, ink, strokeWidth, onChange],
    );

    const isEmpty = strokes.every((s) => s.length === 0);

    return (
      <View style={style}>
        <View
          accessibilityRole="adjustable"
          accessibilityLabel={tr.guest.signaturePadAreaLabel}
          accessibilityHint={tr.guest.signaturePadAreaHint}
          onLayout={onLayout}
          {...responder.panHandlers}
          style={{
            height,
            width: '100%',
            backgroundColor: c.surface,
            borderRadius: radius.md,
            borderWidth: 1,
            borderColor: c.border,
            overflow: 'hidden',
          }}
        >
          {size.w > 0 ? (
            <Svg width={size.w} height={size.h}>
              {strokes.map((s, i) =>
                s.length === 0 ? null : (
                  <Path
                    key={i}
                    d={strokeToPath(s)}
                    stroke={ink}
                    strokeWidth={strokeWidth}
                    strokeLinecap="round"
                    strokeLinejoin="round"
                    fill="none"
                  />
                ),
              )}
            </Svg>
          ) : null}
          {isEmpty ? (
            <View
              pointerEvents="none"
              style={{
                position: 'absolute',
                left: 0,
                right: 0,
                bottom: spacing.sm,
                alignItems: 'center',
              }}
            >
              <Muted>{tr.guest.signaturePadPlaceholder}</Muted>
            </View>
          ) : null}
        </View>
        <View
          style={{
            flexDirection: 'row',
            justifyContent: 'space-between',
            alignItems: 'center',
            marginTop: spacing.xs,
          }}
        >
          <Muted>{isEmpty ? tr.guest.signaturePadEmpty : tr.guest.signaturePadFilled}</Muted>
          <Pressable
            accessibilityRole="button"
            accessibilityLabel={clearLabel}
            onPress={() => {
              currentStroke.current = null;
              setStrokes([]);
              if (onChange) onChange(null);
            }}
            disabled={isEmpty}
            style={({ pressed }) => ({
              paddingVertical: spacing.xs,
              paddingHorizontal: spacing.sm,
              borderRadius: radius.sm,
              opacity: isEmpty ? 0.4 : pressed ? 0.7 : 1,
            })}
          >
            <Body style={{ color: c.primary, fontWeight: '600' }}>{clearLabel}</Body>
          </Pressable>
        </View>
      </View>
    );
  },
);
