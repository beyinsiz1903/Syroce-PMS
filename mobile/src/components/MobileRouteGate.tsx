import React from 'react';
import { ActivityIndicator, View } from 'react-native';
import { Redirect, useRouter, useSegments } from 'expo-router';
import { useQuery } from '@tanstack/react-query';
import { useAuthStore } from '../state/authStore';
import { mobileHome, mobileRouteAllowed, paidDepartmentForSegments } from '../navigation/routeAccess';
import { ROUTES } from '../navigation/routes';
import { getCurrentSubscription } from '../api/subscription';
import { hubModuleState } from '../utils/departmentScreens';
import { Button, Card, Muted } from './ui';

export function MobileRouteGate({ children }: { children: React.ReactNode }) {
  const { user, loading } = useAuthStore();
  const segments = useSegments();
  const router = useRouter();
  const allowed = !!user && mobileRouteAllowed(user, segments);
  const paidTile = paidDepartmentForSegments(segments);
  const subscription = useQuery({
    queryKey: ['current-subscription', user?.tenant_id || user?.hotel_id],
    queryFn: getCurrentSubscription, enabled: !loading && allowed && !!paidTile,
    staleTime: 5 * 60 * 1000, retry: false,
  });
  if (loading) return <View style={{ flex: 1, justifyContent: 'center' }}><ActivityIndicator accessibilityLabel="Oturum doğrulanıyor" /></View>;
  if (!user) return <Redirect href={ROUTES.login} />;
  if (!allowed) return <Redirect href={mobileHome(user)} />;
  if (paidTile) {
    if (subscription.isPending && subscription.fetchStatus === 'fetching') return <ActivityIndicator accessibilityLabel="Modül erişimi doğrulanıyor" />;
    const state = hubModuleState(paidTile, subscription.data);
    if (subscription.isError || state !== 'enabled') return <View style={{ padding: 20, flex: 1 }}><Card>
      <Muted>{state === 'disabled' ? 'Bu modül tesisinizin aboneliğinde etkin değil.' : 'Modül erişimi doğrulanamadı. Bağlantınızı kontrol edip yeniden deneyin.'}</Muted>
      <Button title="Yeniden dene" variant="secondary" onPress={() => { void subscription.refetch(); }} />
      <Button title="Profil ve yetkili modüllere dön" onPress={() => router.replace(ROUTES.homeProfile)} />
    </Card></View>;
  }
  return <>{children}</>;
}
