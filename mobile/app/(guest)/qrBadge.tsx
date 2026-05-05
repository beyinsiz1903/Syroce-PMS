import React, { useCallback, useEffect, useMemo, useRef, useState } from 'react';
import {
  ActivityIndicator,
  Alert,
  Pressable,
  RefreshControl,
  ScrollView,
  View,
} from 'react-native';
import { useFocusEffect } from 'expo-router';
import * as Brightness from 'expo-brightness';
import * as LocalAuthentication from 'expo-local-authentication';
import { useKeepAwake } from 'expo-keep-awake';
import { useQuery, useQueryClient } from '@tanstack/react-query';
import QRCode from 'react-native-qrcode-svg';
import { Badge, Body, Button, Card, H1, H2, Muted } from '../../src/components/ui';
import { spacing, useTheme } from '../../src/theme';
import { tr } from '../../src/i18n/tr';
import {
  approveQrCharge,
  fetchMyPendingCharges,
  fetchMyQrToken,
  rejectQrCharge,
  type QrPendingCharge,
} from '../../src/api/guestQrBadge';
import { formatCurrency } from '../../src/utils/format';
import { haptic } from '../../src/hooks/useHaptic';

/**
 * Misafir Otel Rozeti / QR ödeme ekranı (Tur 15 / Hafta 1).
 *
 * Akış:
 *   1) Üst kısımda dönen QR — backend her 60 sn'lik token üretir, biz
 *      30 sn'de bir yeniliyoruz (ortalama 30+ sn headroom).
 *   2) Personel QR'i okuduğunda /api/qr-badge/charge ile pending charge
 *      oluşturur, push gelir.
 *   3) Push'a tıklayan misafir (veya ekranı zaten açık) "Onay Bekleyen
 *      Hesaplar" listesinde görür → biyometrik onaylı approve/reject.
 *
 * Güvenlik:
 *   - Approve butonu LocalAuthentication.authenticateAsync ile
 *     biyometrik (Face ID / parmak izi) gerektirir. Cihazda biyometrik
 *     yoksa tek kullanımlık native Alert onayına düşer.
 *   - Reject ayrıca onay sorar — yanlışlıkla red atılmasın diye.
 *
 * Ekran parlaklığı QR taranırken otomatik %100'e çıkar (digitalKey ile aynı
 * desen) ve ekran uyumaz.
 */

const TOKEN_REFRESH_INTERVAL_MS = 30_000;
const PENDING_REFRESH_INTERVAL_MS = 5_000;

export default function GuestQrBadgeScreen() {
  const c = useTheme();
  const qc = useQueryClient();
  useKeepAwake();
  const previousBrightnessRef = useRef<number | null>(null);

  // ── Token (refresh every 30s) ──
  const tokenQ = useQuery({
    queryKey: ['guest-qr-token'],
    queryFn: fetchMyQrToken,
    refetchInterval: TOKEN_REFRESH_INTERVAL_MS,
    refetchIntervalInBackground: false,
  });

  // ── Pending charges (refresh every 5s while screen is focused) ──
  const pendingQ = useQuery({
    queryKey: ['guest-qr-pending'],
    queryFn: fetchMyPendingCharges,
    refetchInterval: PENDING_REFRESH_INTERVAL_MS,
    refetchIntervalInBackground: false,
  });

  // ── Brightness boost while focused ──
  useFocusEffect(
    useCallback(() => {
      let cancelled = false;
      (async () => {
        try {
          const perms = await Brightness.requestPermissionsAsync();
          if (!perms.granted || cancelled) return;
          const current = await Brightness.getBrightnessAsync();
          if (cancelled) return;
          previousBrightnessRef.current = current;
          await Brightness.setBrightnessAsync(1);
        } catch {
          // Platform hasn't got Brightness API → ignore.
        }
      })();
      return () => {
        cancelled = true;
        const prev = previousBrightnessRef.current;
        if (prev != null) {
          Brightness.setBrightnessAsync(prev).catch(() => {});
        }
      };
    }, []),
  );

  // ── Countdown to next rotation (visual hint) ──
  const [secondsLeft, setSecondsLeft] = useState<number>(TOKEN_REFRESH_INTERVAL_MS / 1000);
  useEffect(() => {
    if (!tokenQ.data?.expires_at) return;
    setSecondsLeft(TOKEN_REFRESH_INTERVAL_MS / 1000);
    const t = setInterval(() => {
      setSecondsLeft((s) => (s > 0 ? s - 1 : 0));
    }, 1000);
    return () => clearInterval(t);
  }, [tokenQ.data?.token]);

  const qrPayload = useMemo(() => {
    if (!tokenQ.data?.token) return '';
    return JSON.stringify({
      v: 1,
      kind: 'syroce_qr_badge',
      token: tokenQ.data.token,
      booking_id: tokenQ.data.booking_id,
    });
  }, [tokenQ.data]);

  // ── Approve / reject handlers ──
  async function handleApprove(charge: QrPendingCharge) {
    const auth = await LocalAuthentication.hasHardwareAsync().catch(() => false);
    const enrolled = auth ? await LocalAuthentication.isEnrolledAsync().catch(() => false) : false;

    if (auth && enrolled) {
      const r = await LocalAuthentication.authenticateAsync({
        promptMessage: tr.guest.qrBadgeBiometricPrompt,
        cancelLabel: tr.guest.qrBadgeBiometricCancel,
      });
      if (!r.success) return;
    } else {
      // Biyometrik yok → en azından native Alert onayı al.
      const ok = await new Promise<boolean>((resolve) => {
        Alert.alert(
          tr.guest.qrBadgeApproveConfirm,
          `${charge.outlet_name} • ${formatCurrency(charge.amount, charge.currency)}`,
          [
            { text: tr.guest.qrBadgeBiometricCancel, style: 'cancel', onPress: () => resolve(false) },
            { text: tr.guest.qrBadgeApprove, onPress: () => resolve(true) },
          ],
        );
      });
      if (!ok) return;
    }

    try {
      await approveQrCharge(charge.id);
      haptic.success();
      Alert.alert(tr.guest.qrBadgeTitle, tr.guest.qrBadgeApproved);
      qc.invalidateQueries({ queryKey: ['guest-qr-pending'] });
    } catch (e: unknown) {
      const msg = (e as Error)?.message || tr.guest.qrBadgeError;
      haptic.error();
      Alert.alert(tr.guest.qrBadgeTitle, msg);
    }
  }

  async function handleReject(charge: QrPendingCharge) {
    const ok = await new Promise<boolean>((resolve) => {
      Alert.alert(
        tr.guest.qrBadgeRejectConfirm,
        `${charge.outlet_name} • ${formatCurrency(charge.amount, charge.currency)}`,
        [
          { text: tr.guest.qrBadgeBiometricCancel, style: 'cancel', onPress: () => resolve(false) },
          { text: tr.guest.qrBadgeReject, style: 'destructive', onPress: () => resolve(true) },
        ],
      );
    });
    if (!ok) return;

    try {
      await rejectQrCharge(charge.id);
      haptic.warning();
      Alert.alert(tr.guest.qrBadgeTitle, tr.guest.qrBadgeRejected);
      qc.invalidateQueries({ queryKey: ['guest-qr-pending'] });
    } catch (e: unknown) {
      const msg = (e as Error)?.message || tr.guest.qrBadgeError;
      haptic.error();
      Alert.alert(tr.guest.qrBadgeTitle, msg);
    }
  }

  const tokenError = tokenQ.isError || (tokenQ.isSuccess && !tokenQ.data);
  const isNoBookingError =
    !tokenQ.isLoading &&
    !tokenQ.data &&
    tokenError; // generic — backend returns 404 for both no-active-booking and missing guest record

  const charges: QrPendingCharge[] = pendingQ.data?.charges || [];
  const pendingCount = pendingQ.data?.pending_count || 0;

  return (
    <View style={{ flex: 1, backgroundColor: c.bg }}>
      <ScrollView
        contentContainerStyle={{ padding: spacing.lg, gap: spacing.md, paddingBottom: 120 }}
        refreshControl={
          <RefreshControl
            refreshing={tokenQ.isFetching || pendingQ.isFetching}
            onRefresh={() => {
              tokenQ.refetch();
              pendingQ.refetch();
            }}
          />
        }
      >
        <H1>{tr.guest.qrBadgeTitle}</H1>
        <Muted>{tr.guest.qrBadgeIntro}</Muted>

        {/* QR card */}
        <Card>
          {tokenQ.isLoading ? (
            <View style={{ alignItems: 'center', padding: spacing.lg }}>
              <ActivityIndicator size="large" color={c.primary} />
              <Body style={{ marginTop: spacing.sm }}>{tr.guest.qrBadgeRefreshing}</Body>
            </View>
          ) : isNoBookingError ? (
            <View style={{ padding: spacing.md, gap: spacing.sm }}>
              <Body style={{ color: c.danger || c.text }}>{tr.guest.qrBadgeNoBooking}</Body>
              <Button title="Tekrar dene" onPress={() => tokenQ.refetch()} variant="ghost" />
            </View>
          ) : qrPayload ? (
            <View style={{ alignItems: 'center', padding: spacing.md, gap: spacing.sm }}>
              <View
                style={{
                  padding: spacing.md,
                  backgroundColor: '#ffffff',
                  borderRadius: 12,
                }}
              >
                <QRCode value={qrPayload} size={260} backgroundColor="#ffffff" color="#000000" />
              </View>
              <View style={{ flexDirection: 'row', gap: spacing.sm, alignItems: 'center' }}>
                <Muted>{tr.guest.qrBadgeExpiresIn}:</Muted>
                <Body style={{ color: c.primary, fontWeight: '600' }}>
                  {secondsLeft} {tr.guest.qrBadgeSeconds}
                </Body>
              </View>
            </View>
          ) : (
            <Body>{tr.guest.qrBadgeError}</Body>
          )}
        </Card>

        {/* Pending charges */}
        <View style={{ flexDirection: 'row', alignItems: 'center', gap: spacing.sm }}>
          <H2 style={{ flex: 1 }}>{tr.guest.qrBadgePendingTitle}</H2>
          {pendingCount > 0 ? <Badge label={String(pendingCount)} tone="warning" /> : null}
        </View>

        {charges.length === 0 ? (
          <Card>
            <Muted>{tr.guest.qrBadgePendingEmpty}</Muted>
          </Card>
        ) : (
          charges.map((ch) => (
            <PendingChargeCard
              key={ch.id}
              charge={ch}
              onApprove={() => handleApprove(ch)}
              onReject={() => handleReject(ch)}
            />
          ))
        )}
      </ScrollView>
    </View>
  );
}

function PendingChargeCard({
  charge,
  onApprove,
  onReject,
}: {
  charge: QrPendingCharge;
  onApprove: () => void;
  onReject: () => void;
}) {
  const c = useTheme();
  const isPending = charge.status === 'pending_approval';

  const statusBadge = (() => {
    switch (charge.status) {
      case 'approved':
        return <Badge label={tr.guest.qrBadgeStatusApproved} tone="success" />;
      case 'rejected':
        return <Badge label={tr.guest.qrBadgeStatusRejected} tone="danger" />;
      case 'expired':
        return <Badge label={tr.guest.qrBadgeStatusExpired} tone="default" />;
      case 'failed':
        return <Badge label={tr.guest.qrBadgeStatusFailed} tone="danger" />;
      case 'pending_approval':
        return <Badge label={tr.guest.qrBadgeStatusPending} tone="warning" />;
      default:
        return null;
    }
  })();

  return (
    <Card>
      <View style={{ gap: spacing.sm }}>
        <View style={{ flexDirection: 'row', alignItems: 'center' }}>
          <Body style={{ flex: 1, fontWeight: '600' }}>{charge.outlet_name}</Body>
          {statusBadge}
        </View>
        {charge.description ? <Muted>{charge.description}</Muted> : null}
        <Body style={{ fontSize: 22, fontWeight: '700', color: c.text }}>
          {formatCurrency(charge.amount, charge.currency)}
        </Body>

        {isPending ? (
          <View style={{ flexDirection: 'row', gap: spacing.sm, marginTop: spacing.sm }}>
            <Pressable
              onPress={onReject}
              style={{
                flex: 1,
                paddingVertical: spacing.md,
                borderRadius: 8,
                borderWidth: 1,
                borderColor: c.danger || c.border,
                alignItems: 'center',
              }}
            >
              <Body style={{ color: c.danger || c.text, fontWeight: '600' }}>
                {tr.guest.qrBadgeReject}
              </Body>
            </Pressable>
            <Pressable
              onPress={onApprove}
              style={{
                flex: 1,
                paddingVertical: spacing.md,
                borderRadius: 8,
                backgroundColor: c.primary,
                alignItems: 'center',
              }}
            >
              <Body style={{ color: '#ffffff', fontWeight: '600' }}>
                {tr.guest.qrBadgeApprove}
              </Body>
            </Pressable>
          </View>
        ) : null}
      </View>
    </Card>
  );
}
