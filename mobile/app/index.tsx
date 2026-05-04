import React from 'react';
import { ActivityIndicator, View } from 'react-native';
import { useTheme } from '../src/theme';

export default function Index() {
  const c = useTheme();
  return (
    <View style={{ flex: 1, alignItems: 'center', justifyContent: 'center', backgroundColor: c.bg }}>
      <ActivityIndicator color={c.primary} />
    </View>
  );
}
