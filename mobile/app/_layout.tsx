import React, { useEffect, useMemo } from 'react';
import { ActivityIndicator, Pressable, Text, View } from 'react-native';
import { Stack, useRootNavigationState, useRouter, useSegments } from 'expo-router';
import { StatusBar } from 'expo-status-bar';
import { SafeAreaProvider } from 'react-native-safe-area-context';
import { GestureHandlerRootView } from 'react-native-gesture-handler';
import { onlineManager, QueryClient, QueryClientProvider } from '@tanstack/react-query';
import NetInfo from '@react-native-community/netinfo';
import { useAuthStore } from '../src/state/authStore';
import { useSettingsStore } from '../src/state/settingsStore';
import { useTheme, useResolvedScheme } from '../src/theme';
import {
  DEPARTMENTS_SEGMENT,
  GROUP_SEGMENTS,
  HOME_SEGMENT,
  ROUTES,
  groupForRole,
  rootForRole,
} from '../src/navigation/routes';
import { setupOfflineCache } from '../src/cache/persister';
import { markSync } from '../src/cache/offlineMeta';
import { flushPosQueue, refreshPosQueueCount } from '../src/cache/posQueue';
import { BiometricLockGate } from '../src/components/BiometricLockGate';
import { NightScreen } from '../src/components/NightScreen';
import { installCertPinning } from '../src/security/certPinning';

// V3: install the pinned-fetch wrapper before anything else — this swaps
// `globalThis.fetch` so subsequent API calls in client.ts route through
// the SSL-pinning library on production builds. No-op on Expo Go.
installCertPinning();

const queryClient = new QueryClient({
  defaultOptions: {
    queries: {
      retry: 1,
      staleTime: 30_000,
      // V3: when offline we still want the persisted cache to be served
      // immediately. gcTime controls how long unused entries linger in
      // memory; the persister manages on-disk lifetime separately.
      gcTime: 24 * 60 * 60 * 1000,
      refetchOnWindowFocus: false,
      refetchOnReconnect: true,
      networkMode: 'offlineFirst',
    },
    mutations: {
      networkMode: 'offlineFirst',
    },
  },
});

// Mark a successful sync timestamp whenever a query succeeds so the
// OfflineBanner can show "Son güncelleme X dk önce" once we drop offline.
queryClient.getQueryCache().subscribe((event) => {
  if (event.type === 'updated' && event.action.type === 'success') {
    markSync();
  }
});

function AuthGate({ children }: { children: React.ReactNode }) {
  const segments = useSegments();
  const router = useRouter();
  const rootNavigationState = useRootNavigationState();
  const { user, role, allAccess, deptAccess, loading, hydrate } = useAuthStore();
  const hydrateSettings = useSettingsStore((s) => s.hydrate);

  useEffect(() => {
    hydrate();
    hydrateSettings();
  }, [hydrate, hydrateSettings]);

  useEffect(() => {
    // Login/hydration can finish before Expo Router has mounted the root
    // navigator on a cold iOS launch. Navigating in that small window throws
    // and leaves the otherwise-valid session on the generic error screen.
    // Wait for the navigator key before applying the auth redirect.
    if (loading || !rootNavigationState?.key) return;
    const first = segments[0];
    const inAuth = first === '(auth)';

    if (!user) {
      if (!inAuth) router.replace(ROUTES.login);
      return;
    }

    // All-access users (super_admin/admin) may sit inside ANY role group, so
    // we only redirect them out of the auth flow or an unknown segment — never
    // out of a sibling group they intentionally switched into. Single-role
    // users stay pinned to their own group.
    if (allAccess) {
      if (inAuth || !GROUP_SEGMENTS.includes(first as (typeof GROUP_SEGMENTS)[number])) {
        router.replace(rootForRole(role));
      }
      return;
    }

    // Guests keep their dedicated experience, pinned to their own group.
    if (role === 'guest_app') {
      if (inAuth || first !== '(guest)') {
        router.replace(rootForRole(role));
      }
      return;
    }

    // The mobile product is intentionally centred on the shared operational
    // front-desk shell. This only controls navigation: every write remains
    // checked by backend RBAC.
    if (first === '(frontdesk)') return;
    if (first === HOME_SEGMENT) return;
    const inDepartments = first === DEPARTMENTS_SEGMENT;
    if (inDepartments && deptAccess) return;
    if (first === groupForRole(role)) return;

    router.replace(rootForRole(role));
  }, [user, role, allAccess, deptAccess, loading, rootNavigationState?.key, segments, router]);

  return <>{children}</>;
}

function RootShell() {
  const c = useTheme();
  const scheme = useResolvedScheme();
  return (
    <View style={{ flex: 1, backgroundColor: c.bg }}>
      <StatusBar style={scheme === 'dark' ? 'light' : 'dark'} />
      <Stack
        screenOptions={{
          headerStyle: { backgroundColor: c.surface },
          headerTitleStyle: { color: c.text },
          headerTintColor: c.text,
          contentStyle: { backgroundColor: c.bg },
        }}
      >
        <Stack.Screen name="(auth)" options={{ headerShown: false }} />
        <Stack.Screen name="(home)" options={{ headerShown: false }} />
        <Stack.Screen name="(frontdesk)" options={{ headerShown: false }} />
        <Stack.Screen name="(housekeeping)" options={{ headerShown: false }} />
        <Stack.Screen name="(gm)" options={{ headerShown: false }} />
        <Stack.Screen name="(guest)" options={{ headerShown: false }} />
        <Stack.Screen name="(departments)" options={{ headerShown: false }} />
        <Stack.Screen name="index" options={{ headerShown: false }} />
      </Stack>
      <NightScreen />
    </View>
  );
}

export default function RootLayout() {
  // Wire up the offline-cache persister exactly once. The dispose function
  // is captured so HMR updates can release listeners cleanly during dev.
  useEffect(() => {
    const dispose = setupOfflineCache(queryClient);
    // V3 (round 7): drive React Query's onlineManager from NetInfo so
    // queued mutations + `refetchOnReconnect` fire correctly when we
    // come back online. Earlier rounds wired NetInfo into focusManager,
    // which conflated "user is looking" with "we have a network" and
    // produced the wrong refetch semantics (e.g. paused queries on
    // background, refetched on reconnect even when the screen wasn't
    // visible). onlineManager is the canonical hook for connectivity.
    const netSub = NetInfo.addEventListener((state) => {
      const online = !!state.isConnected;
      onlineManager.setOnline(online);
      // Drain the durable POS write queue the moment we come back online so
      // orders entered offline are sent (server-authoritative, exactly once).
      if (online) flushPosQueue().catch(() => {});
    });
    // On cold start: surface any queue persisted before the app was killed and
    // attempt a flush (no-op when empty / still offline).
    refreshPosQueueCount().catch(() => {});
    flushPosQueue().catch(() => {});
    return () => {
      dispose();
      netSub();
    };
  }, []);

  // Memoise so React doesn't recreate the providers on every render.
  const tree = useMemo(
    () => (
      <GestureHandlerRootView style={{ flex: 1 }}>
        <SafeAreaProvider>
          <QueryClientProvider client={queryClient}>
            <BiometricLockGate>
              <AuthGate>
                <RootShell />
              </AuthGate>
            </BiometricLockGate>
          </QueryClientProvider>
        </SafeAreaProvider>
      </GestureHandlerRootView>
    ),
    [],
  );

  return tree;
}

// A screen-level render exception must never look like a native application
// crash to an operator. Expo Router shows this fallback for a broken route and
// keeps the session alive so the operator can retry or navigate back after a
// future diagnostic update.
export function ErrorBoundary({
  error,
  retry,
}: {
  error: Error;
  retry: () => void;
}) {
  // Keep the real error in device logs / TestFlight diagnostics without
  // exposing implementation details to hotel staff.
  console.error('[mobile] route render failed', error);
  return (
    <View
      style={{ flex: 1, alignItems: 'center', justifyContent: 'center', padding: 24, gap: 16 }}
    >
      <Text style={{ fontSize: 20, fontWeight: '700' }}>Ekran açılamadı</Text>
      <Text style={{ textAlign: 'center', color: '#64748b' }}>
        Uygulama oturumunuz açık kaldı. Tekrar deneyin; sorun sürerse destek ekibine bildirin.
      </Text>
      <Pressable
        onPress={retry}
        accessibilityRole="button"
        style={{ backgroundColor: '#2563eb', borderRadius: 10, paddingHorizontal: 18, paddingVertical: 12 }}
      >
        <Text style={{ color: '#fff', fontWeight: '700' }}>Tekrar dene</Text>
      </Pressable>
    </View>
  );
}

export function LoadingScreen() {
  const c = useTheme();
  return (
    <View
      style={{ flex: 1, alignItems: 'center', justifyContent: 'center', backgroundColor: c.bg }}
    >
      <ActivityIndicator color={c.primary} />
    </View>
  );
}
