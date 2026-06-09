import React, { useState } from 'react';
import { Image, KeyboardAvoidingView, Platform, ScrollView, View } from 'react-native';
import { SafeAreaView } from 'react-native-safe-area-context';
import { Body, Button, Card, Field, Muted } from '../../src/components/ui';
import { radius, spacing, useTheme } from '../../src/theme';
import { tr } from '../../src/i18n/tr';
import { useAuthStore } from '../../src/state/authStore';
import { haptic } from '../../src/hooks/useHaptic';

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
          contentContainerStyle={{
            flexGrow: 1,
            padding: spacing.xl,
            justifyContent: 'center',
            alignItems: 'center',
          }}
          keyboardShouldPersistTaps="handled"
        >
          <View style={{ width: '100%', maxWidth: 420, gap: spacing.xl }}>
            <View style={{ alignItems: 'center', gap: spacing.md }}>
              <Image
                source={require('../../assets/syroce-circle.png')}
                style={{ width: 108, height: 108 }}
                resizeMode="contain"
                accessibilityLabel={tr.app.name}
              />
              <Muted style={{ textAlign: 'center' }}>{tr.auth.title}</Muted>
            </View>

            <Card style={{ padding: spacing.xl, borderRadius: radius.lg, gap: spacing.md }}>
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
              <View style={{ height: spacing.xs }} />
              <Button
                title={tr.auth.submit}
                loading={submitting || loading}
                onPress={onSubmit}
                testID="smoke-login-submit"
                fullWidth
              />
            </Card>
          </View>
        </ScrollView>
      </KeyboardAvoidingView>
    </SafeAreaView>
  );
}
