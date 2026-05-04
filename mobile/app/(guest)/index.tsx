import React from 'react';
import { ScrollView } from 'react-native';
import { Body, Card, H1, H2, Muted } from '../../src/components/ui';
import { spacing, useTheme } from '../../src/theme';

export default function GuestHome() {
  const c = useTheme();
  return (
    <ScrollView contentContainerStyle={{ padding: spacing.lg, gap: spacing.md, backgroundColor: c.bg, flexGrow: 1 }}>
      <H1>Misafir Uygulaması</H1>
      <Card>
        <H2>Yakında</H2>
        <Muted>
          Misafir uygulaması (rezervasyon, online check-in, oda servisi, mesajlaşma, sadakat)
          V2 sürümünde aktifleşecek. Bu MVP yalnızca personel akışlarını içerir.
        </Muted>
      </Card>
    </ScrollView>
  );
}
