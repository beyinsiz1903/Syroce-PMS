import React from 'react';
import { Pressable, ScrollView, Text, View } from 'react-native';
import { radius, spacing, useTheme } from '../theme';

export type FilterChipOption = {
  value: string;
  label: string;
};

type FilterChipsProps = {
  options: FilterChipOption[];
  value: string;
  onChange: (value: string) => void;
  testID?: string;
};

// Horizontally-scrolling single-select chip row. Used for the reservation
// status filter and the availability day-count selector.
export const FilterChips: React.FC<FilterChipsProps> = ({ options, value, onChange, testID }) => {
  const c = useTheme();
  return (
    <ScrollView
      horizontal
      showsHorizontalScrollIndicator={false}
      contentContainerStyle={{ gap: spacing.sm, paddingVertical: spacing.xs }}
      testID={testID}
    >
      {options.map((opt) => {
        const active = opt.value === value;
        return (
          <Pressable
            key={opt.value}
            onPress={() => onChange(opt.value)}
            accessibilityRole="button"
            accessibilityState={{ selected: active }}
            style={({ pressed }) => ({
              opacity: pressed ? 0.85 : 1,
              backgroundColor: active ? c.primary : c.surface,
              borderColor: active ? c.primary : c.border,
              borderWidth: 1,
              borderRadius: radius.lg,
              paddingHorizontal: spacing.md,
              paddingVertical: spacing.sm,
              minHeight: 36,
              justifyContent: 'center',
            })}
          >
            <Text
              style={{
                color: active ? c.primaryText : c.text,
                fontSize: 13,
                fontWeight: '600',
              }}
            >
              {opt.label}
            </Text>
          </Pressable>
        );
      })}
    </ScrollView>
  );
};
