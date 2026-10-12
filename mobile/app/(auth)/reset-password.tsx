import React, { useState } from 'react';
import { KeyboardAvoidingView, Platform, ScrollView, View } from 'react-native';
import { SafeAreaView } from 'react-native-safe-area-context';
import { useLocalSearchParams, useRouter } from 'expo-router';
import { Body, Button, Card, Field, H1, Muted } from '../../src/components/ui';
import { requestPasswordReset, resetPasswordWithToken } from '../../src/api/auth';
import { spacing, useTheme } from '../../src/theme';

/** Password recovery deliberately keeps the request response generic. */
export default function ResetPasswordScreen() {
  const c = useTheme();
  const router = useRouter();
  const { token } = useLocalSearchParams<{ token?: string }>();
  const [email, setEmail] = useState('');
  const [password, setPassword] = useState('');
  const [status, setStatus] = useState('');
  const [busy, setBusy] = useState(false);

  const request = async () => {
    setBusy(true); setStatus('');
    try {
      await requestPasswordReset(email.trim());
      setStatus('E-posta kayıtlıysa güvenli sıfırlama bağlantısı gönderildi.');
    } catch { setStatus('İstek gönderilemedi. Birkaç dakika sonra tekrar deneyin.'); }
    finally { setBusy(false); }
  };
  const reset = async () => {
    if (!token) return;
    setBusy(true); setStatus('');
    try {
      await resetPasswordWithToken(token, password);
      setStatus('Şifreniz güncellendi. Yeni şifrenizle giriş yapabilirsiniz.');
    } catch { setStatus('Bağlantı geçersiz, süresi dolmuş veya şifre koşulları karşılanmıyor.'); }
    finally { setBusy(false); }
  };
  const viaLink = typeof token === 'string' && token.length > 0;
  return <SafeAreaView style={{ flex: 1, backgroundColor: c.bg }}><KeyboardAvoidingView behavior={Platform.OS === 'ios' ? 'padding' : undefined} style={{ flex: 1 }}><ScrollView contentContainerStyle={{ flexGrow: 1, justifyContent: 'center', padding: spacing.xl }} keyboardShouldPersistTaps="handled"><View style={{ gap: spacing.lg }}><H1>{viaLink ? 'Yeni şifre oluştur' : 'Şifre sıfırlama'}</H1><Card style={{ gap: spacing.md }}>{viaLink ? <><Field label="Yeni şifre" secureTextEntry value={password} onChangeText={setPassword} textContentType="newPassword" /><Button title="Şifreyi güncelle" loading={busy} onPress={reset} fullWidth /></> : <><Muted>Kayıtlı e-posta adresinizi yazın. Hesap varlığını açıklamayan güvenli bir bağlantı göndereceğiz.</Muted><Field label="E-posta" keyboardType="email-address" autoCapitalize="none" value={email} onChangeText={setEmail} textContentType="emailAddress" /><Button title="Bağlantı gönder" loading={busy} onPress={request} fullWidth /></>}{status ? <Body accessibilityLiveRegion="polite">{status}</Body> : null}<Button title="Girişe dön" variant="secondary" onPress={() => router.replace('/(auth)/login')} fullWidth /></Card></View></ScrollView></KeyboardAvoidingView></SafeAreaView>;
}
