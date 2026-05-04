import React, { useEffect } from 'react';
import { ActivityIndicator, View } from 'react-native';
import { Stack, useRouter, useSegments } from 'expo-router';
import { StatusBar } from 'expo-status-bar';
import { SafeAreaProvider } from 'react-native-safe-area-context';
import { QueryClient, QueryClientProvider } from '@tanstack/react-query';
import { useAuthStore } from '../src/state/authStore';
import { useTheme } from '../src/theme';
import { ROUTES, groupForRole, rootForRole } from '../src/navigation/routes';

const queryClient = new QueryClient({
  defaultOptions: {
    queries: {
      retry: 1,
      staleTime: 30_000,
      refetchOnWindowFocus: false,
    },
  },
});

function AuthGate({ children }: { children: React.ReactNode }) {
  const segments = useSegments();
  const router = useRouter();
  const { user, role, loading, hydrate } = useAuthStore();

  useEffect(() => {
    hydrate();
  }, [hydrate]);

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
  return (
    <SafeAreaProvider>
      <QueryClientProvider client={queryClient}>
        <AuthGate>
          <RootShell />
        </AuthGate>
      </QueryClientProvider>
    </SafeAreaProvider>
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
