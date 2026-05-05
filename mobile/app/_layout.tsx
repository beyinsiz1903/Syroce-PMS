import React, { useEffect, useMemo } from 'react';
import { ActivityIndicator, View } from 'react-native';
import { Stack, useRouter, useSegments } from 'expo-router';
import { StatusBar } from 'expo-status-bar';
import { SafeAreaProvider } from 'react-native-safe-area-context';
import { onlineManager, QueryClient, QueryClientProvider } from '@tanstack/react-query';
import NetInfo from '@react-native-community/netinfo';
import { useAuthStore } from '../src/state/authStore';
import { useSettingsStore } from '../src/state/settingsStore';
import { useTheme } from '../src/theme';
import { ROUTES, groupForRole, rootForRole } from '../src/navigation/routes';
import { setupOfflineCache } from '../src/cache/persister';
import { markSync } from '../src/cache/offlineMeta';
import { attachPushListeners, registerForPush } from '../src/notifications/push';
import { BiometricLockGate } from '../src/components/BiometricLockGate';
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
  const { user, role, loading, hydrate } = useAuthStore();
  const hydrateSettings = useSettingsStore((s) => s.hydrate);

  useEffect(() => {
    hydrate();
    hydrateSettings();
  }, [hydrate, hydrateSettings]);

  useEffect(() => {
    if (loading) return;
    const first = segments[0];
    const inAuth = first === '(auth)';

    if (!user) {
      if (!inAuth) router.replace(ROUTES.login);
      return;
    }

    const expectedGroup = groupForRole(role);
    if (inAuth || first !== expectedGroup) {
      router.replace(rootForRole(role));
    }
  }, [user, role, loading, segments, router]);

  // Push registration runs after sign-in; safe to call repeatedly because
  // the backend treats POST /push/register as upsert by device_id.
  useEffect(() => {
    if (!user) return;
    let cancelled = false;
    (async () => {
      try {
        await registerForPush();
      } catch {
        // best-effort; logged inside helper
      }
      if (cancelled) return;
    })();
    const detach = attachPushListeners(router, role);
    return () => {
      cancelled = true;
      detach();
    };
  }, [user, role, router]);

  return <>{children}</>;
}

function RootShell() {
  const c = useTheme();
  return (
    <View style={{ flex: 1, backgroundColor: c.bg }}>
      <StatusBar style="auto" />
      <Stack
        screenOptions={{
          headerStyle: { backgroundColor: c.surface },
          headerTitleStyle: { color: c.text },
          headerTintColor: c.text,
          contentStyle: { backgroundColor: c.bg },
        }}
      >
        <Stack.Screen name="(auth)" options={{ headerShown: false }} />
        <Stack.Screen name="(frontdesk)" options={{ headerShown: false }} />
        <Stack.Screen name="(housekeeping)" options={{ headerShown: false }} />
        <Stack.Screen name="(gm)" options={{ headerShown: false }} />
        <Stack.Screen name="(guest)" options={{ headerShown: false }} />
        <Stack.Screen name="index" options={{ headerShown: false }} />
      </Stack>
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
      onlineManager.setOnline(!!state.isConnected);
    });
    return () => {
      dispose();
      netSub();
    };
  }, []);

  // Memoise so React doesn't recreate the providers on every render.
  const tree = useMemo(
    () => (
      <SafeAreaProvider>
        <QueryClientProvider client={queryClient}>
          <BiometricLockGate>
            <AuthGate>
              <RootShell />
            </AuthGate>
          </BiometricLockGate>
        </QueryClientProvider>
      </SafeAreaProvider>
    ),
    [],
  );

  return tree;
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
