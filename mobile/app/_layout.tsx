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
  const { user, role, allAccess, deptAccess, loading, hydrate } = useAuthStore();
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

    // Task #327 — all other staff land in the unified common shell `(home)`
    // (Tier-1 backbone) and may stay there. They may ALSO browse into:
    //   * their native Tier-2 group (e.g. front_desk → (frontdesk)), and
    //   * the shared (departments) area when they hold department entitlement.
    // Anything else ejects them back to the shell. This is navigation gating
    // only — backend RBAC still enforces every action inside each surface.
    if (first === HOME_SEGMENT) return;
    const inDepartments = first === DEPARTMENTS_SEGMENT;
    if (inDepartments && deptAccess) return;
    if (first === groupForRole(role)) return;

    router.replace(rootForRole(role));
  }, [user, role, allAccess, deptAccess, loading, segments, router]);

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
        <Stack.Screen name="(home)" options={{ headerShown: false }} />
        <Stack.Screen name="(frontdesk)" options={{ headerShown: false }} />
        <Stack.Screen name="(housekeeping)" options={{ headerShown: false }} />
        <Stack.Screen name="(gm)" options={{ headerShown: false }} />
        <Stack.Screen name="(guest)" options={{ headerShown: false }} />
        <Stack.Screen name="(departments)" options={{ headerShown: false }} />
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
