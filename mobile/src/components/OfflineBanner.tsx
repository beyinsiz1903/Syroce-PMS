import React from 'react';
import { Text, View } from 'react-native';
import { spacing, useTheme } from '../theme';
import { tr } from '../i18n/tr';
import { formatAgo, useLastSync } from '../cache/offlineMeta';

type Props = { visible: boolean };

/**
 * Shown across every screen at the top to signal "you're seeing cached
 * data". When we know the last successful sync timestamp (set by query
 * hooks via `markSync`), surface "X dk önce" so the user can decide
 * whether the cache is fresh enough to act on.
 */
export const OfflineBanner: React.FC<Props> = ({ visible }) => {
  const c = useTheme();
  const lastSync = useLastSync();
  if (!visible) return null;
  const ago = formatAgo(lastSync);
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
      {ago ? (
        <Text style={{ color: c.warning, fontSize: 12, marginTop: 2 }}>
          {tr.app.lastUpdate}: {ago}
        </Text>
      ) : null}
    </View>
  );
};
