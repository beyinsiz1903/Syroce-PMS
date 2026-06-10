import React, { useMemo, useState } from 'react';
import { Modal, Pressable, Text, View } from 'react-native';
import { radius, spacing, useTheme } from '../theme';
import { tr } from '../i18n/tr';

type DatePickerProps = {
  // ISO date (YYYY-MM-DD) or empty/undefined when nothing selected.
  value?: string;
  onChange: (iso: string | undefined) => void;
  placeholder?: string;
  // Optional inclusive lower bound (ISO) — days before it are disabled.
  minimumDate?: string;
  // Show a "clear" action so an optional filter can be reset to empty.
  allowClear?: boolean;
  testID?: string;
};

const WEEKDAYS = ['Pzt', 'Sal', 'Çar', 'Per', 'Cum', 'Cmt', 'Paz'];

function pad(n: number): string {
  return String(n).padStart(2, '0');
}

function toISO(y: number, m: number, d: number): string {
  return `${y}-${pad(m + 1)}-${pad(d)}`;
}

// Parse a YYYY-MM-DD string into local Y/M/D parts (no timezone shift).
function parseISO(iso?: string): { y: number; m: number; d: number } | null {
  if (!iso) return null;
  const match = iso.match(/^(\d{4})-(\d{2})-(\d{2})$/);
  if (!match) return null;
  const y = Number(match[1]);
  const m = Number(match[2]) - 1;
  const d = Number(match[3]);
  if (m < 0 || m > 11 || d < 1 || d > 31) return null;
  return { y, m, d };
}

function daysInMonth(y: number, m: number): number {
  return new Date(y, m + 1, 0).getDate();
}

// Monday-based weekday index (0 = Monday … 6 = Sunday).
function firstWeekdayIndex(y: number, m: number): number {
  return (new Date(y, m, 1).getDay() + 6) % 7;
}

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

export const DatePicker: React.FC<DatePickerProps> = ({
  value,
  onChange,
  placeholder,
  minimumDate,
  allowClear,
  testID,
}) => {
  const c = useTheme();
  const [open, setOpen] = useState(false);

  const today = useMemo(() => {
    const now = new Date();
    return { y: now.getFullYear(), m: now.getMonth(), d: now.getDate() };
  }, []);

  const selected = parseISO(value);
  const minParts = parseISO(minimumDate);

  // Month currently shown in the calendar grid.
  const [view, setView] = useState(() => {
    const base = selected || today;
    return { y: base.y, m: base.m };
  });

  const openPicker = () => {
    const base = parseISO(value) || today;
    setView({ y: base.y, m: base.m });
    setOpen(true);
  };

  const goMonth = (delta: number) => {
    setView((prev) => {
      const next = new Date(prev.y, prev.m + delta, 1);
      return { y: next.getFullYear(), m: next.getMonth() };
    });
  };

  const isBeforeMin = (y: number, m: number, d: number): boolean => {
    if (!minParts) return false;
    return toISO(y, m, d) < toISO(minParts.y, minParts.m, minParts.d);
  };

  const pick = (d: number) => {
    onChange(toISO(view.y, view.m, d));
    setOpen(false);
  };

  const display = formatDisplay(value);
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

  const cells = useMemo(() => {
    const lead = firstWeekdayIndex(view.y, view.m);
    const total = daysInMonth(view.y, view.m);
    const out: (number | null)[] = [];
    for (let i = 0; i < lead; i += 1) out.push(null);
    for (let d = 1; d <= total; d += 1) out.push(d);
    return out;
  }, [view]);

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
                const isSelected =
                  !!selected && selected.y === view.y && selected.m === view.m && selected.d === d;
                const isToday = today.y === view.y && today.m === view.m && today.d === d;
                const disabled = isBeforeMin(view.y, view.m, d);
                return (
                  <Pressable
                    key={`d${d}`}
                    onPress={() => (disabled ? undefined : pick(d))}
                    disabled={disabled}
                    accessibilityRole="button"
                    accessibilityState={{ selected: isSelected, disabled }}
                    accessibilityLabel={toISO(view.y, view.m, d)}
                    style={{
                      width: `${100 / 7}%`,
                      height: 40,
                      alignItems: 'center',
                      justifyContent: 'center',
                    }}
                  >
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
                  if (!isBeforeMin(today.y, today.m, today.d)) {
                    onChange(toISO(today.y, today.m, today.d));
                    setOpen(false);
                  }
                }}
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
                      onChange(undefined);
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
