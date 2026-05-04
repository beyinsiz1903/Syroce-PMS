import React from 'react';
import { Text, View } from 'react-native';
import { spacing, useTheme } from '../theme';
import { tr } from '../i18n/tr';

type Props = { visible: boolean };

export const OfflineBanner: React.FC<Props> = ({ visible }) => {
  const c = useTheme();
  if (!visible) return null;
  return (
    <View
      accessibilityLiveRegion="polite"
      style={{
        backgroundColor: c.warning + '22',
        borderColor: c.warning,
        borderWidth: 1,
        padding: spacing.sm,
        borderRadius: 6,
        marginBottom: spacing.sm,
      }}
    >
      <Text style={{ color: c.warning, fontSize: 13, fontWeight: '600' }}>{tr.app.offline}</Text>
    </View>
  );
};
