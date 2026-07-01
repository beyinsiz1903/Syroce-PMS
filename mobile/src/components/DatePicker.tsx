import React, { useMemo, useState } from 'react';
import { Modal, Pressable, Text, View } from 'react-native';
import { radius, spacing, useTheme } from '../theme';
import { tr } from '../i18n/tr';
import {
  buildMonthCells,
  isBeforeMinParts,
  parseISO,
  toISO,
  todayParts,
  todayShortcutISO,
} from './datePickerUtils';

type SharedProps = {
  placeholder?: string;
  // Optional inclusive lower bound (ISO) — days before it are disabled.
  minimumDate?: string;
  // Show a "clear" action so an optional filter can be reset to empty.
  allowClear?: boolean;
  testID?: string;
};

type SingleProps = SharedProps & {
  mode?: 'single';
  // ISO date (YYYY-MM-DD) or empty/undefined when nothing selected.
  value?: string;
  onChange: (iso: string | undefined) => void;
};

type RangeProps = SharedProps & {
  mode: 'range';
  // Inclusive range bounds as ISO (YYYY-MM-DD), undefined/empty when unset.
  startValue?: string;
  endValue?: string;
  onRangeChange: (start: string | undefined, end: string | undefined) => void;
};

type DatePickerProps = SingleProps | RangeProps;

const WEEKDAYS = ['Pzt', 'Sal', 'Çar', 'Per', 'Cum', 'Cmt', 'Paz'];

function formatDisplay(iso?: string): string | null {
  const parts = parseISO(iso);
  if (!parts) return null;
  try {
    return new Date(parts.y, parts.m, parts.d).toLocaleDateString('tr-TR', {
      day: '2-digit',
      month: 'short',
      year: 'numeric',
    });
  } catch {
    return iso || null;
  }
}

export const DatePicker: React.FC<DatePickerProps> = (props) => {
  const { placeholder, minimumDate, allowClear, testID } = props;
  const isRange = props.mode === 'range';

  const c = useTheme();
  const [open, setOpen] = useState(false);

  const today = useMemo(() => todayParts(), []);

  const singleValue = isRange ? undefined : props.value;
  const rangeStart = isRange ? props.startValue : undefined;
  const rangeEnd = isRange ? props.endValue : undefined;

  const selected = parseISO(singleValue);
  const startParts = parseISO(rangeStart);
  const endParts = parseISO(rangeEnd);
  const minParts = parseISO(minimumDate);

  // Month currently shown in the calendar grid.
  const [view, setView] = useState(() => {
    const base = selected || startParts || today;
    return { y: base.y, m: base.m };
  });

  const openPicker = () => {
    const base = parseISO(isRange ? rangeStart : singleValue) || today;
    setView({ y: base.y, m: base.m });
    setOpen(true);
  };

  const goMonth = (delta: number) => {
    setView((prev) => {
      const next = new Date(prev.y, prev.m + delta, 1);
      return { y: next.getFullYear(), m: next.getMonth() };
    });
  };

  const isBeforeMin = (y: number, m: number, d: number): boolean =>
    isBeforeMinParts(minParts, y, m, d);

  const pickSingle = (iso: string) => {
    if (props.mode === 'range') return;
    props.onChange(iso);
    setOpen(false);
  };

  // Range selection state machine:
  // - no start, or both bounds set → begin a fresh range at the tapped day.
  // - start set, no end, day ≥ start → complete the range and close.
  // - start set, no end, day < start → restart with the earlier day.
  const pickRange = (iso: string) => {
    if (props.mode !== 'range') return;
    const hasStart = !!rangeStart;
    const hasEnd = !!rangeEnd;
    if (!hasStart || hasEnd) {
      props.onRangeChange(iso, undefined);
      return;
    }
    if (iso >= (rangeStart as string)) {
      props.onRangeChange(rangeStart, iso);
      setOpen(false);
    } else {
      props.onRangeChange(iso, undefined);
    }
  };

  const pick = (d: number) => {
    const iso = toISO(view.y, view.m, d);
    if (isRange) pickRange(iso);
    else pickSingle(iso);
  };

  const display = isRange
    ? (() => {
        const s = formatDisplay(rangeStart);
        const e = formatDisplay(rangeEnd);
        if (s && e) return `${s} → ${e}`;
        if (s) return s;
        return null;
      })()
    : formatDisplay(singleValue);
  const monthLabel = useMemo(() => {
    try {
      return new Date(view.y, view.m, 1).toLocaleDateString('tr-TR', {
        month: 'long',
        year: 'numeric',
      });
    } catch {
      return `${view.m + 1}/${view.y}`;
    }
  }, [view]);

  const cells = useMemo(() => buildMonthCells(view.y, view.m), [view]);

  return (
    <View>
      <Pressable
        onPress={openPicker}
        accessibilityRole="button"
        accessibilityLabel={display || placeholder}
        testID={testID}
        style={({ pressed }) => ({
          backgroundColor: c.surface,
          borderColor: c.border,
          borderWidth: 1,
          borderRadius: radius.md,
          padding: spacing.md,
          minHeight: 48,
          justifyContent: 'center',
          opacity: pressed ? 0.85 : 1,
        })}
      >
        <Text style={{ color: display ? c.text : c.textMuted, fontSize: 16 }}>
          {display || placeholder || tr.datePicker.select}
        </Text>
      </Pressable>

      <Modal
        visible={open}
        transparent
        animationType="fade"
        onRequestClose={() => setOpen(false)}
      >
        <Pressable
          onPress={() => setOpen(false)}
          style={{
            flex: 1,
            backgroundColor: '#00000088',
            justifyContent: 'center',
            padding: spacing.lg,
          }}
        >
          <Pressable
            onPress={() => {}}
            style={{
              backgroundColor: c.surface,
              borderColor: c.border,
              borderWidth: 1,
              borderRadius: radius.lg,
              padding: spacing.lg,
              alignSelf: 'center',
              width: '100%',
              maxWidth: 360,
            }}
          >
            {/* Month navigation */}
            <View
              style={{
                flexDirection: 'row',
                alignItems: 'center',
                justifyContent: 'space-between',
                marginBottom: spacing.md,
              }}
            >
              <Pressable
                onPress={() => goMonth(-1)}
                accessibilityRole="button"
                accessibilityLabel={tr.datePicker.prevMonth}
                hitSlop={8}
                style={{ padding: spacing.sm }}
              >
                <Text style={{ color: c.primary, fontSize: 20, fontWeight: '700' }}>‹</Text>
              </Pressable>
              <Text style={{ color: c.text, fontSize: 16, fontWeight: '600', textTransform: 'capitalize' }}>
                {monthLabel}
              </Text>
              <Pressable
                onPress={() => goMonth(1)}
                accessibilityRole="button"
                accessibilityLabel={tr.datePicker.nextMonth}
                hitSlop={8}
                style={{ padding: spacing.sm }}
              >
                <Text style={{ color: c.primary, fontSize: 20, fontWeight: '700' }}>›</Text>
              </Pressable>
            </View>

            {/* Weekday header */}
            <View style={{ flexDirection: 'row', marginBottom: spacing.xs }}>
              {WEEKDAYS.map((w) => (
                <View key={w} style={{ flex: 1, alignItems: 'center', paddingVertical: spacing.xs }}>
                  <Text style={{ color: c.textMuted, fontSize: 11, fontWeight: '600' }}>{w}</Text>
                </View>
              ))}
            </View>

            {/* Day grid */}
            <View style={{ flexDirection: 'row', flexWrap: 'wrap' }}>
              {cells.map((d, i) => {
                if (d == null) {
                  return <View key={`b${i}`} style={{ width: `${100 / 7}%`, height: 40 }} />;
                }
                const iso = toISO(view.y, view.m, d);
                const isToday = today.y === view.y && today.m === view.m && today.d === d;
                const disabled = isBeforeMin(view.y, view.m, d);

                // Range endpoints + in-between highlighting.
                const startISO = startParts
                  ? toISO(startParts.y, startParts.m, startParts.d)
                  : null;
                const endISO = endParts ? toISO(endParts.y, endParts.m, endParts.d) : null;
                const isRangeStart = isRange && startISO === iso;
                const isRangeEnd = isRange && endISO === iso;
                const isInRange =
                  isRange && !!startISO && !!endISO && iso > startISO && iso < endISO;

                const isSelected = isRange
                  ? isRangeStart || isRangeEnd
                  : !!selected &&
                    selected.y === view.y &&
                    selected.m === view.m &&
                    selected.d === d;

                // Connect the endpoints with a tinted band on the in-between days
                // and on the inner edge of each endpoint.
                const showLeftBand = isInRange || (isRangeEnd && !!startISO);
                const showRightBand = isInRange || (isRangeStart && !!endISO);

                return (
                  <Pressable
                    key={`d${d}`}
                    onPress={() => (disabled ? undefined : pick(d))}
                    disabled={disabled}
                    accessibilityRole="button"
                    accessibilityState={{ selected: isSelected, disabled }}
                    // react-native-web 0.19 drops accessibilityState.selected on
                    // web (it only emits the direct aria-* props), so the selected
                    // day exposed no aria-selected to screen readers or e2e. Emit
                    // it explicitly; on native RN 0.74 maps aria-selected back to
                    // accessibilityState.selected, so there is no native regression.
                    // (aria-selected on role="button" is a pragmatic pairing; a
                    // full calendar grid role is a future a11y refinement.)
                    aria-selected={isSelected}
                    accessibilityLabel={iso}
                    style={{
                      width: `${100 / 7}%`,
                      height: 40,
                      alignItems: 'center',
                      justifyContent: 'center',
                    }}
                  >
                    {/* In-range tint band behind the day */}
                    {(isInRange || showLeftBand || showRightBand) ? (
                      <View
                        pointerEvents="none"
                        style={{
                          position: 'absolute',
                          top: 3,
                          bottom: 3,
                          left: showLeftBand ? 0 : '50%',
                          right: showRightBand ? 0 : '50%',
                          backgroundColor: c.primary + '22',
                        }}
                      />
                    ) : null}
                    <View
                      style={{
                        width: 34,
                        height: 34,
                        borderRadius: 17,
                        alignItems: 'center',
                        justifyContent: 'center',
                        backgroundColor: isSelected ? c.primary : 'transparent',
                        borderWidth: isToday && !isSelected ? 1 : 0,
                        borderColor: c.primary,
                      }}
                    >
                      <Text
                        style={{
                          color: disabled
                            ? c.textMuted
                            : isSelected
                              ? c.primaryText
                              : c.text,
                          fontSize: 14,
                          fontWeight: isSelected ? '700' : '500',
                          opacity: disabled ? 0.4 : 1,
                        }}
                      >
                        {d}
                      </Text>
                    </View>
                  </Pressable>
                );
              })}
            </View>

            {/* Footer actions */}
            <View
              style={{
                flexDirection: 'row',
                justifyContent: 'space-between',
                alignItems: 'center',
                marginTop: spacing.md,
                gap: spacing.sm,
              }}
            >
              <Pressable
                onPress={() => {
                  setView({ y: today.y, m: today.m });
                  const todayISO = todayShortcutISO(today, minimumDate);
                  if (!todayISO) return;
                  if (props.mode === 'range') {
                    // Start a fresh range at today; keep open to pick the end.
                    props.onRangeChange(todayISO, undefined);
                  } else {
                    props.onChange(todayISO);
                    setOpen(false);
                  }
                }}
                // Scoped e2e anchor: the footer "Bugün" label collides with the
                // persistent bottom-tab "Bugün" (tr.tabs.today) rendered behind
                // the modal, so a getByText() match is ambiguous. Derive the id
                // from the trigger testID so each picker's preset is unique.
                testID={testID ? `${testID}-today` : undefined}
                style={{ paddingVertical: spacing.sm, paddingHorizontal: spacing.sm }}
              >
                <Text style={{ color: c.primary, fontSize: 14, fontWeight: '600' }}>
                  {tr.datePicker.today}
                </Text>
              </Pressable>
              <View style={{ flexDirection: 'row', gap: spacing.md }}>
                {allowClear ? (
                  <Pressable
                    onPress={() => {
                      if (props.mode === 'range') props.onRangeChange(undefined, undefined);
                      else props.onChange(undefined);
                      setOpen(false);
                    }}
                    style={{ paddingVertical: spacing.sm, paddingHorizontal: spacing.sm }}
                  >
                    <Text style={{ color: c.danger, fontSize: 14, fontWeight: '600' }}>
                      {tr.datePicker.clear}
                    </Text>
                  </Pressable>
                ) : null}
                <Pressable
                  onPress={() => setOpen(false)}
                  style={{ paddingVertical: spacing.sm, paddingHorizontal: spacing.sm }}
                >
                  <Text style={{ color: c.textMuted, fontSize: 14, fontWeight: '600' }}>
                    {tr.datePicker.close}
                  </Text>
                </Pressable>
              </View>
            </View>
          </Pressable>
        </Pressable>
      </Modal>
    </View>
  );
};
