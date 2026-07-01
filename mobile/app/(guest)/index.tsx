import React, { useCallback, useMemo } from 'react';
import { Pressable, RefreshControl, ScrollView, View } from 'react-native';
import { useRouter } from 'expo-router';
import { useQuery } from '@tanstack/react-query';
import { Ionicons } from '@expo/vector-icons';
import {
  Badge,
  Body,
  Card,
  EmptyState,
  FadeInView,
  H1,
  H2,
  Muted,
  SectionTitle,
  SkeletonCard,
  webCenter,
} from '../../src/components/ui';
import { OfflineBanner } from '../../src/components/OfflineBanner';
import { radius, spacing, useTheme } from '../../src/theme';
import { tr } from '../../src/i18n/tr';
import { GuestBooking, getGuestBookings } from '../../src/api/guestBookings';
import { useAuthStore } from '../../src/state/authStore';
import { haptic } from '../../src/hooks/useHaptic';
import { formatDate, formatCurrency } from '../../src/utils/format';
import { isOffline } from '../../src/utils/errors';
import { ROUTES } from '../../src/navigation/routes';

type IoniconName = keyof typeof Ionicons.glyphMap;

function statusTone(status?: string): 'success' | 'warning' | 'info' | 'default' {
  switch ((status || '').toLowerCase()) {
    case 'checked_in':
      return 'success';
    case 'confirmed':
    case 'guaranteed':
      return 'info';
    case 'checked_out':
      return 'default';
    default:
      return 'warning';
  }
}

function statusLabel(status?: string): string {
  switch ((status || '').toLowerCase()) {
    case 'checked_in':
      return 'Konaklıyor';
    case 'confirmed':
      return 'Onaylı';
    case 'guaranteed':
      return 'Garantili';
    case 'checked_out':
      return 'Tamamlandı';
    case 'cancelled':
      return 'İptal';
    default:
      return status || '—';
  }
}

function greeting(): string {
  const h = new Date().getHours();
  if (h < 11) return tr.guest.greetingMorning;
  if (h < 18) return tr.guest.greetingAfternoon;
  return tr.guest.greetingEvening;
}

function firstName(name?: string | null, email?: string | null): string {
  const n = (name || '').trim();
  if (n) return n.split(/\s+/)[0];
  const e = (email || '').trim();
  if (e) return e.split('@')[0];
  return tr.guest.greetingGuestFallback;
}

function nightsBetween(checkIn?: string, checkOut?: string): number | null {
  if (!checkIn || !checkOut) return null;
  try {
    const a = new Date(checkIn).getTime();
    const b = new Date(checkOut).getTime();
    const n = Math.round((b - a) / 86_400_000);
    return n > 0 ? n : null;
  } catch {
    return null;
  }
}

// Premium concierge servis kutusu: yumusak tintli daire icinde ikon, baslik,
// kisa aciklama. Iki sutunlu izgarada dizilir. Basinca hafif olcek + haptik.
function ServiceTile({
  icon,
  label,
  desc,
  tint,
  onPress,
}: {
  icon: IoniconName;
  label: string;
  desc: string;
  tint?: string;
  onPress: () => void;
}) {
  const c = useTheme();
  const color = tint ?? c.primary;
  return (
    <Pressable
      onPress={() => {
        haptic.tap();
        onPress();
      }}
      accessibilityRole="button"
      accessibilityLabel={label}
      style={({ pressed }) => ({
        width: '100%',
        transform: [{ scale: pressed ? 0.97 : 1 }],
        opacity: pressed ? 0.92 : 1,
      })}
    >
      <Card style={{ minHeight: 132, justifyContent: 'space-between' }}>
        <View
          style={{
            width: 44,
            height: 44,
            borderRadius: radius.pill,
            backgroundColor: color + '1f',
            alignItems: 'center',
            justifyContent: 'center',
          }}
        >
          <Ionicons name={icon} size={22} color={color} />
        </View>
        <View style={{ marginTop: spacing.md }}>
          <Body style={{ fontWeight: '700' }} numberOfLines={1}>
            {label}
          </Body>
          <Muted style={{ marginTop: 2 }} numberOfLines={2}>
            {desc}
          </Muted>
        </View>
      </Card>
    </Pressable>
  );
}

function BookingCard({ b, onPress }: { b: GuestBooking; onPress: () => void }) {
  const c = useTheme();
  return (
    <Pressable
      onPress={onPress}
      accessibilityRole="button"
      accessibilityLabel={`${b.hotel?.property_name || 'Otel'} ${b.room?.room_number || ''}`}
      style={({ pressed }) => ({ opacity: pressed ? 0.85 : 1 })}
    >
      <Card>
        <View style={{ flexDirection: 'row', justifyContent: 'space-between', gap: spacing.sm }}>
          <View style={{ flex: 1 }}>
            <H2>{b.hotel?.property_name || b.hotel?.hotel_name || 'Otel'}</H2>
            <Muted>
              Oda {b.room?.room_number || 'TBA'} · {b.room?.room_type || ''}
            </Muted>
            <Body style={{ color: c.text, marginTop: 4 }}>
              {formatDate(b.check_in)} → {formatDate(b.check_out)}
            </Body>
            <Muted>
              {tr.guest.confirmation}: {b.confirmation_number || '—'}
            </Muted>
          </View>
          <View style={{ alignItems: 'flex-end', gap: spacing.xs }}>
            <Badge label={statusLabel(b.status)} tone={statusTone(b.status)} />
            {typeof b.total_amount === 'number' ? (
              <Body style={{ color: c.textMuted, fontSize: 13 }}>
                {formatCurrency(b.total_amount)}
              </Body>
            ) : null}
          </View>
        </View>
      </Card>
    </Pressable>
  );
}

export default function GuestConciergeScreen() {
  const c = useTheme();
  const router = useRouter();
  const { user } = useAuthStore();
  const q = useQuery({ queryKey: ['guest-bookings'], queryFn: getGuestBookings });

  const refreshing = q.isFetching && !q.isLoading;
  const onRefresh = useCallback(() => {
    q.refetch();
  }, [q]);
  const offline = q.isError && isOffline(q.error);

  const active = q.data?.active_bookings || [];
  const past = q.data?.past_bookings || [];

  // En alakali rezervasyon: once konaklayan (checked_in), yoksa ilk aktif.
  // Ust kisimdaki hero ozet + concierge hizmetleri bu rezervasyona gore kurulur.
  const focus = useMemo<GuestBooking | null>(() => {
    return active.find((b) => b.status === 'checked_in') || active[0] || null;
  }, [active]);

  const isCheckedIn = focus?.status === 'checked_in';
  const checkinOpen = !!focus?.can_checkin && !isCheckedIn;
  const nights = focus ? nightsBetween(focus.check_in, focus.check_out) : null;

  const noBookings = !q.isLoading && active.length === 0 && past.length === 0;

  // Concierge servis kutulari — sadece gorsel/etkilesim; her biri mevcut akisa
  // yonlendirir. Dijital anahtar yalnizca konaklarken aktif (mevcut kural).
  const services = useMemo(() => {
    const list: { icon: IoniconName; label: string; desc: string; tint?: string; onPress: () => void }[] = [];
    if (checkinOpen && focus) {
      list.push({
        icon: 'create-outline',
        label: tr.guest.onlineCheckinTitle,
        desc: tr.guest.serviceCheckinDesc,
        onPress: () =>
          router.push({ pathname: ROUTES.guestOnlineCheckin, params: { bookingId: focus.id } }),
      });
    }
    if (isCheckedIn && focus) {
      list.push({
        icon: 'key-outline',
        label: tr.guest.digitalKeyTitle,
        desc: tr.guest.serviceDigitalKeyDesc,
        tint: c.success,
        onPress: () => router.push({ pathname: ROUTES.guestDigitalKey, params: { id: focus.id } }),
      });
      list.push({
        icon: 'restaurant-outline',
        label: tr.guest.roomServiceTitle,
        desc: tr.guest.serviceRoomServiceDesc,
        tint: c.warning,
        onPress: () => router.push(ROUTES.guestRoomService),
      });
    }
    list.push({
      icon: 'time-outline',
      label: tr.guest.earlyLateTitle,
      desc: tr.guest.serviceEarlyLateDesc,
      tint: c.info,
      onPress: () =>
        focus
          ? router.push({ pathname: ROUTES.guestEarlyLate, params: { bookingId: focus.id } })
          : router.push(ROUTES.guestEarlyLate),
    });
    list.push({
      icon: 'chatbubbles-outline',
      label: tr.guest.messagesTitle,
      desc: tr.guest.serviceMessagesDesc,
      onPress: () => router.push(ROUTES.guestMessages),
    });
    list.push({
      icon: 'sparkles-outline',
      label: tr.guest.qrBadgeTitle,
      desc: tr.guest.serviceQrBadgeDesc,
      tint: c.vip,
      onPress: () => router.push(ROUTES.guestQrBadge),
    });
    list.push({
      icon: 'ribbon-outline',
      label: tr.guest.loyaltyTitle,
      desc: tr.guest.serviceLoyaltyDesc,
      tint: c.vip,
      onPress: () => router.push(ROUTES.guestLoyalty),
    });
    if (focus) {
      list.push({
        icon: 'receipt-outline',
        label: tr.guest.bookingDetail,
        desc: tr.guest.serviceBookingDesc,
        onPress: () =>
          router.push({ pathname: ROUTES.guestBookingDetail, params: { id: focus.id } }),
      });
    }
    return list;
  }, [checkinOpen, isCheckedIn, focus, router, c]);

  const heroState = isCheckedIn
    ? tr.guest.heroStayingNow
    : checkinOpen
      ? tr.guest.heroCheckinReady
      : tr.guest.heroArrivalSoon;

  return (
    <ScrollView
      style={{ flex: 1, backgroundColor: c.bg }}
      contentContainerStyle={[{ padding: spacing.lg, gap: spacing.md, paddingBottom: spacing.xxl }, webCenter]}
      refreshControl={
        <RefreshControl refreshing={refreshing} onRefresh={onRefresh} tintColor={c.primary} />
      }
    >
      <OfflineBanner visible={offline} />

      {/* Concierge masthead — sicak karsilama, premium hiyerarsi. */}
      <FadeInView>
        <View style={{ marginBottom: spacing.xs }}>
          <Body
            style={{
              color: c.primary,
              fontSize: 12,
              fontWeight: '700',
              letterSpacing: 1.4,
              textTransform: 'uppercase',
            }}
          >
            {tr.guest.conciergeOverline}
          </Body>
          <H1 style={{ marginTop: spacing.xs }}>
            {greeting()}, {firstName(user?.name, user?.email)}
          </H1>
          <Muted style={{ marginTop: spacing.xs }}>{tr.guest.conciergeIntro}</Muted>
        </View>
      </FadeInView>

      {q.isLoading ? (
        <SkeletonCard />
      ) : noBookings ? (
        <Card padded={false}>
          <EmptyState
            icon="bed-outline"
            title={tr.guest.noBookings}
            message={tr.guest.noBookingsMessage}
          />
        </Card>
      ) : (
        <>
          {focus ? (
            <FadeInView delay={60}>
              <Pressable
                onPress={() => {
                  haptic.tap();
                  router.push({ pathname: ROUTES.guestBookingDetail, params: { id: focus.id } });
                }}
                accessibilityRole="button"
                accessibilityLabel={focus.hotel?.property_name || 'Konaklama'}
                style={({ pressed }) => ({ opacity: pressed ? 0.92 : 1 })}
              >
                <Card accent={isCheckedIn ? c.success : c.primary} style={{ padding: spacing.xl }}>
                  <View
                    style={{
                      flexDirection: 'row',
                      justifyContent: 'space-between',
                      alignItems: 'center',
                      gap: spacing.sm,
                    }}
                  >
                    <Badge
                      label={heroState}
                      tone={isCheckedIn ? 'success' : checkinOpen ? 'info' : 'warning'}
                      icon={isCheckedIn ? 'sparkles' : 'time-outline'}
                    />
                    <Badge label={statusLabel(focus.status)} tone={statusTone(focus.status)} />
                  </View>
                  <H1 style={{ marginTop: spacing.md, fontSize: 26, lineHeight: 32 }}>
                    {focus.hotel?.property_name || focus.hotel?.hotel_name || 'Otel'}
                  </H1>
                  <Body style={{ color: c.text, marginTop: spacing.sm }}>
                    {formatDate(focus.check_in)} → {formatDate(focus.check_out)}
                    {nights ? `  ·  ${nights} ${tr.guest.heroNights}` : ''}
                  </Body>
                  <Muted style={{ marginTop: 2 }}>
                    Oda {focus.room?.room_number || 'TBA'}
                    {focus.room?.room_type ? ` · ${focus.room.room_type}` : ''}
                  </Muted>
                  <View
                    style={{
                      flexDirection: 'row',
                      alignItems: 'center',
                      gap: spacing.xs,
                      marginTop: spacing.md,
                    }}
                  >
                    <Muted style={{ flex: 1 }}>
                      {tr.guest.confirmation}: {focus.confirmation_number || '—'}
                    </Muted>
                    <Ionicons name="chevron-forward" size={18} color={c.textMuted} />
                  </View>
                </Card>
              </Pressable>
            </FadeInView>
          ) : null}

          {/* Concierge hizmetleri — premium kart girisleri (izgara). */}
          <View style={{ marginTop: spacing.sm }}>
            <SectionTitle title={tr.guest.conciergeServices} />
            <Muted style={{ marginTop: -spacing.xs, marginBottom: spacing.sm }}>
              {tr.guest.conciergeServicesIntro}
            </Muted>
            <View
              style={{
                flexDirection: 'row',
                flexWrap: 'wrap',
                justifyContent: 'space-between',
                rowGap: spacing.md,
              }}
            >
              {services.map((s, i) => (
                <FadeInView key={s.label} delay={80 + i * 40} style={{ width: '48%' }}>
                  <ServiceTile
                    icon={s.icon}
                    label={s.label}
                    desc={s.desc}
                    tint={s.tint}
                    onPress={s.onPress}
                  />
                </FadeInView>
              ))}
            </View>
          </View>

          {active.length > 0 ? (
            <>
              <SectionTitle title={tr.guest.activeBookings} />
              {active.map((b) => (
                <View key={b.id} style={{ marginBottom: spacing.sm }}>
                  <BookingCard
                    b={b}
                    onPress={() =>
                      router.push({ pathname: ROUTES.guestBookingDetail, params: { id: b.id } })
                    }
                  />
                </View>
              ))}
            </>
          ) : null}

          {past.length > 0 ? (
            <>
              <SectionTitle title={tr.guest.pastBookings} />
              {past.map((b) => (
                <View key={b.id} style={{ marginBottom: spacing.sm }}>
                  <BookingCard
                    b={b}
                    onPress={() =>
                      router.push({ pathname: ROUTES.guestBookingDetail, params: { id: b.id } })
                    }
                  />
                </View>
              ))}
            </>
          ) : null}
        </>
      )}
    </ScrollView>
  );
}
