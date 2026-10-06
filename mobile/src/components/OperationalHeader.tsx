import React from 'react';
import { Text, View } from 'react-native';
import { useQuery } from '@tanstack/react-query';

import { getToday } from '../api/hub';
import { useTheme } from '../theme';

// Compact property context for staff screens. The current task remains the
// dominant line; property + product identity sit below it like a quiet
// navigation breadcrumb and never consume body space.
export function OperationalHeader({ title }: { title: string }) {
  const c = useTheme();
  const today = useQuery({
    queryKey: ['hub-today'],
    queryFn: getToday,
    staleTime: 5 * 60 * 1000,
  });
  const hotelName = String(today.data?.hotel_name || '').trim();
  const context = hotelName ? `${hotelName} · SYROCE PMS` : 'SYROCE PMS';

  return (
    <View style={{ maxWidth: 250, alignItems: 'center', justifyContent: 'center' }}>
      <Text
        numberOfLines={1}
        style={{ color: c.text, fontSize: 15, fontWeight: '700', lineHeight: 18 }}
      >
        {title}
      </Text>
      <Text
        numberOfLines={1}
        style={{ color: c.textMuted, fontSize: 9, fontWeight: '600', letterSpacing: 0.25 }}
      >
        {context}
      </Text>
    </View>
  );
}

