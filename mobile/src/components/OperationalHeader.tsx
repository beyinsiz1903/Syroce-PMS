import React from 'react';
import { Text, View } from 'react-native';
import { useQuery } from '@tanstack/react-query';

import { getToday } from '../api/hub';
import { useTheme } from '../theme';
import { demoPreviewEnabled } from '../utils/previewMode';

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
  const demoPreview = demoPreviewEnabled(__DEV__, process.env.EXPO_PUBLIC_PREVIEW_MODE, process.env.EXPO_PUBLIC_API_URL);
  const context = demoPreview ? 'DEMO · Örnek veriler · SYROCE PMS' : hotelName ? `${hotelName} · SYROCE PMS` : 'SYROCE PMS';

  return (
    <View accessibilityLabel={`${title} · ${context}`} style={{ maxWidth: 250, flexShrink: 1, alignItems: 'center', justifyContent: 'center' }}>
      <Text
        numberOfLines={1}
        style={{ color: c.text, fontSize: 15, fontWeight: '700', lineHeight: 18 }}
      >
        {title}
      </Text>
      <Text
        numberOfLines={1}
        style={{ color: c.textMuted, fontSize: 12, lineHeight: 17, fontWeight: '500' }}
      >
        {context}
      </Text>
    </View>
  );
}
