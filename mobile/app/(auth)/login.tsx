import React, { useState } from 'react';
import { Image, KeyboardAvoidingView, Platform, ScrollView, View } from 'react-native';
import { SafeAreaView } from 'react-native-safe-area-context';
import { useRouter } from 'expo-router';
import { Body, Button, Card, Field, Muted } from '../../src/components/ui';
import { radius, spacing, useTheme } from '../../src/theme';
import { tr } from '../../src/i18n/tr';
import { useAuthStore } from '../../src/state/authStore';
import { haptic } from '../../src/hooks/useHaptic';
import { demoPreviewEnabled } from '../../src/utils/previewMode';

export default function LoginScreen() {
  const c = useTheme();
  const { login, verifyTwoFactor, cancelTwoFactor, pendingTwoFactorToken, loading, error } = useAuthStore();
  const router = useRouter();
  const [email, setEmail] = useState('');
  const [password, setPassword] = useState('');
  const [twoFactorCode, setTwoFactorCode] = useState('');
  const [submitting, setSubmitting] = useState(false);
  // Development-only preview is explicitly isolated from the live PMS.
  const demoPreview = demoPreviewEnabled(__DEV__, process.env.EXPO_PUBLIC_PREVIEW_MODE, process.env.EXPO_PUBLIC_API_URL);
  const onDemoSignIn = async () => {
    setPassword('');
    setSubmitting(true);
    try { await login('demo@syroce.local', 'demo-mobile'); }
    catch { haptic.error(); }
    finally { setSubmitting(false); }
  };

  const onSubmit = async () => {
    setSubmitting(true);
    try {
      if (pendingTwoFactorToken) await verifyTwoFactor(twoFactorCode);
      else await login(email.trim(), password);
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

            {demoPreview ? (
              <Card style={{ gap: spacing.lg }}>
                <Body style={{ fontWeight: '700', fontSize: 20 }}>Mobil tasarım önizlemesi</Body>
                <Muted>Salt okunur demo · Tüm misafirler, tutarlar ve rezervasyonlar örnektir.</Muted>
                <Muted>Canlı PMS kullanıcı bilgilerinizi girmeniz gerekmez. Bu önizleme canlı sisteme veri göndermez.</Muted>
                {error ? <Body style={{ color: c.danger }} accessibilityLiveRegion="polite">{error}</Body> : null}
                <Button title="Demo ile önizle" onPress={onDemoSignIn} loading={submitting || loading} testID="preview-demo-login" fullWidth />
              </Card>
            ) : (
            <Card style={{ padding: spacing.xl, borderRadius: radius.lg, gap: spacing.md }}>
              {pendingTwoFactorToken ? (
                <>
                  <Muted>{tr.auth.twoFactorHint}</Muted>
                  <Field
                    label={tr.auth.twoFactorCode}
                    autoCapitalize="characters"
                    autoCorrect={false}
                    value={twoFactorCode}
                    onChangeText={setTwoFactorCode}
                    accessibilityLabel={tr.auth.twoFactorCode}
                    testID="smoke-login-2fa-code"
                  />
                  <Button
                    title={tr.auth.backToPassword}
                    variant="secondary"
                    onPress={() => { cancelTwoFactor(); setTwoFactorCode(''); }}
                    fullWidth
                  />
                </>
              ) : (
                <>
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
                </>
              )}
              {error ? (
                <Body
                  style={{ color: c.danger }}
                  accessibilityLiveRegion="polite"
                  testID="smoke-login-error"
                >
                  {error}
                </Body>
              ) : null}
              <View style={{ height: spacing.xs }} />
              <Button
                title={pendingTwoFactorToken ? tr.auth.verifyCode : tr.auth.submit}
                loading={submitting || loading}
                disabled={!!pendingTwoFactorToken && twoFactorCode.trim().length === 0}
                onPress={onSubmit}
                testID="smoke-login-submit"
                fullWidth
              />
              <Button
                title="Şifremi unuttum"
                variant="secondary"
                onPress={() => router.push('/(auth)/reset-password')}
                fullWidth
              />
            </Card>
            )}
          </View>
        </ScrollView>
      </KeyboardAvoidingView>
    </SafeAreaView>
  );
}
