import React, { useState } from 'react';
import { KeyboardAvoidingView, Platform, ScrollView, View } from 'react-native';
import { SafeAreaView } from 'react-native-safe-area-context';
import { Body, Button, Field, H1, Muted } from '../../src/components/ui';
import { spacing, useTheme } from '../../src/theme';
import { tr } from '../../src/i18n/tr';
import { useAuthStore } from '../../src/state/authStore';
import { haptic } from '../../src/hooks/useHaptic';
import { getApiUrl } from '../../src/api/client';

export default function LoginScreen() {
  const c = useTheme();
  const { login, loading, error } = useAuthStore();
  const [email, setEmail] = useState(__DEV__ ? 'info@syroce.com' : '');
  const [password, setPassword] = useState(__DEV__ ? 'Syroce2026' : '');
  const [submitting, setSubmitting] = useState(false);

  const onSubmit = async () => {
    setSubmitting(true);
    try {
      await login(email.trim(), password);
      haptic.success();
    } catch {
      haptic.error();
    } finally {
      setSubmitting(false);
    }
  };

  return (
    <SafeAreaView style={{ flex: 1, backgroundColor: c.bg }}>
      <KeyboardAvoidingView
        behavior={Platform.OS === 'ios' ? 'padding' : undefined}
        style={{ flex: 1 }}
      >
        <ScrollView
          contentContainerStyle={{ flexGrow: 1, padding: spacing.xl, justifyContent: 'center' }}
          keyboardShouldPersistTaps="handled"
        >
          <View style={{ gap: spacing.md }}>
            <H1>{tr.app.name}</H1>
            <Muted>{tr.auth.title}</Muted>
            <View style={{ height: spacing.lg }} />
            <Field
              label={tr.auth.email}
              autoCapitalize="none"
              autoCorrect={false}
              keyboardType="email-address"
              value={email}
              onChangeText={setEmail}
              accessibilityLabel={tr.auth.email}
              testID="smoke-login-email"
              textContentType="emailAddress"
            />
            <Field
              label={tr.auth.password}
              secureTextEntry
              value={password}
              onChangeText={setPassword}
              accessibilityLabel={tr.auth.password}
              testID="smoke-login-password"
              textContentType="password"
            />
            {error ? (
              <Body style={{ color: c.danger }} accessibilityLiveRegion="polite">
                {error}
              </Body>
            ) : null}
            <View style={{ height: spacing.sm }} />
            <Button
              title={tr.auth.submit}
              loading={submitting || loading}
              onPress={onSubmit}
              testID="smoke-login-submit"
              fullWidth
            />
            <Muted style={{ textAlign: 'center', marginTop: spacing.lg }}>
              API: {getApiUrl()}
            </Muted>
          </View>
        </ScrollView>
      </KeyboardAvoidingView>
    </SafeAreaView>
  );
}
