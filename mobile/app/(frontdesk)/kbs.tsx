import React, { useCallback, useEffect, useState } from 'react';
import { AppState, RefreshControl, ScrollView, View } from 'react-native';
import { useFocusEffect, useLocalSearchParams, useRouter } from 'expo-router';
import { useMutation, useQuery, useQueryClient } from '@tanstack/react-query';
import { Body, Button, Card, EmptyState, H1, H2, Muted, SkeletonCard, webCenter } from '../../src/components/ui';
import { KbsIdentityFields } from '../../src/components/KbsIdentityFields';
import { getKbsNotifications, getKbsReadiness, getKbsStatus, retryKbsNotification, updateKbsIdentity, type KbsGuestReadiness } from '../../src/api/kbs';
import { emptyKbsIdentity, identityPatch, kbsMissingText, kbsStatusLabel, type KbsIdentity } from '../../src/utils/kbs';
import { useAuthStore } from '../../src/state/authStore';
import { mobileOperationAllowed } from '../../src/state/roleAccess';
import { ROUTES } from '../../src/navigation/routes';
import { spacing, useTheme } from '../../src/theme';
import { errorMessage } from '../../src/utils/errors';

export default function KbsScreen() {
  const c = useTheme();
  const router = useRouter();
  const { booking_id } = useLocalSearchParams<{ booking_id?: string }>();
  const [bookingId, setBookingId] = useState(String(booking_id || ''));
  const [skip, setSkip] = useState(0);
  const [group, setGroup] = useState<'sent' | 'not_sent'>('not_sent');
  const [focused, setFocused] = useState(false);
  const [active, setActive] = useState(AppState.currentState === 'active');
  const [editing, setEditing] = useState<KbsGuestReadiness | null>(null);
  const [identity, setIdentity] = useState<KbsIdentity>(emptyKbsIdentity);
  const [message, setMessage] = useState('');
  const user = useAuthStore(s => s.user);
  const scope = `${user?.tenant_id || user?.hotel_id || ''}:${user?.id || user?.user_id || ''}`;
  useEffect(() => { setEditing(null); setIdentity(emptyKbsIdentity()); setMessage(''); setSkip(0); }, [scope]);
  const canEdit = mobileOperationAllowed(user, 'edit_booking');
  const qc = useQueryClient();
  useFocusEffect(useCallback(() => { setFocused(true); return () => { setFocused(false); setEditing(null); setIdentity(emptyKbsIdentity()); }; }, []));
  useEffect(() => { const sub = AppState.addEventListener('change', state => setActive(state === 'active')); return () => sub.remove(); }, []);
  useEffect(() => { setBookingId(String(booking_id || '')); setSkip(0); }, [booking_id]);
  const enabled = focused && active;
  const status = useQuery({ queryKey: ['kbs-cloud-status', scope], queryFn: getKbsStatus, gcTime: 0, enabled, refetchInterval: enabled ? 15000 : false, retry: false });
  const jobs = useQuery({ queryKey: ['kbs-notifications', scope, skip, bookingId, group], queryFn: () => getKbsNotifications(skip, bookingId || undefined, group), gcTime: 0, enabled, refetchInterval: enabled ? 15000 : false, retry: false });
  const readiness = useQuery({ queryKey: ['kbs-readiness', scope, bookingId], queryFn: () => getKbsReadiness(bookingId), gcTime: 0, enabled: enabled && !!bookingId, retry: false });
  const refresh = async () => { await Promise.all([status.refetch(), jobs.refetch(), ...(bookingId ? [readiness.refetch()] : [])]); };
  const retry = useMutation({ mutationFn: retryKbsNotification, retry: false,
    onSuccess: () => { setMessage('Tekrar kuyruğa alındı; kurum kabulü henüz alınmış sayılmaz.'); void jobs.refetch(); },
    onError: e => setMessage(errorMessage(e, 'Kayıt tekrar kuyruğa alınamadı. Sonucu kontrol edin; art arda denemeyin.')) });
  const save = useMutation({ mutationFn: async () => {
    if (!editing || !bookingId) throw new Error('Önce rezervasyon ve misafiri seçin.');
    return updateKbsIdentity(bookingId, editing.guest_id, identityPatch(identity));
  }, retry: false, onSuccess: () => { setEditing(null); setIdentity(emptyKbsIdentity()); setMessage('Kimlik bilgileri tamamlandı. Bekleyen bildirimlerin durumunu takip edin.'); void qc.invalidateQueries({ queryKey: ['kbs-readiness'] }); void jobs.refetch(); },
  onError: e => setMessage(errorMessage(e, 'Bilgiler tamamlanamadı; eksik alanları kontrol edin.')) });
  const workerStale = status.data?.enabled && (!status.data.last_worker_at || Date.now() - Date.parse(status.data.last_worker_at) > 180000);
  return <ScrollView style={{ flex: 1, backgroundColor: c.bg }} contentContainerStyle={[{ padding: spacing.lg, gap: spacing.md, paddingBottom: spacing.xxl }, webCenter]}
    refreshControl={<RefreshControl refreshing={jobs.isRefetching} onRefresh={() => void refresh()} tintColor={c.primary} />}>
    <H1>KBS bildirimleri</H1>
    <Muted>Yalnız kurum kabulü alınanlar gönderilmiş sayılır. Misafirler gerçek çıkışlarından 24 saat sonra bu listeden kalkar; teslim ve denetim kayıtları silinmez.</Muted>
    <View accessibilityRole="tablist" style={{ flexDirection: 'row', gap: spacing.sm }}>
      <Button title={`Gönderilen (${jobs.data?.counts.sent || 0})`} variant={group === 'sent' ? 'primary' : 'secondary'} onPress={() => { setGroup('sent'); setSkip(0); }} />
      <Button title={`Gönderilmeyen (${jobs.data?.counts.not_sent || 0})`} variant={group === 'not_sent' ? 'primary' : 'secondary'} onPress={() => { setGroup('not_sent'); setSkip(0); }} />
    </View>
    {!!jobs.data?.hidden_unresolved_count && <Muted>Görünürlük süresi dolmuş {jobs.data.hidden_unresolved_count} bildirim sonuçlanmamış. Kişi bilgileri ana listede gösterilmez; yönetici denetim kayıtlarından takip etmelidir.</Muted>}
    <Card accent={status.data?.enabled && status.data.verified && !workerStale ? c.success : c.warning}>
      <H2>Sunucu gönderimi</H2>
      <Body>{status.isError ? 'Bağlantı durumu okunamadı; gönderilmiş varsaymayın.' : !status.data ? 'Durum kontrol ediliyor…' : status.data.enabled && status.data.verified ? 'Jandarma bağlantısı etkin' : 'Sunucu bağlantısı etkin/doğrulanmış değil'}</Body>
      <Muted>{workerStale ? 'Gönderici çalışma bilgisi güncel değil; yönetici kontrolü gerekli.' : 'Sunucu gönderimi etkin olduğunda telefonun veya resepsiyon ekranının açık kalması gerekmez.'}</Muted>
      {!status.data?.enabled && <Muted>Bağlantı kurulmadan kuyruk kuruma teslim edilemez. Emniyet/Polis tarayıcı oturumu farklı bir bağlantıdır.</Muted>}
    </Card>
    {!!message && <Card accent={c.warning}><Body accessibilityLiveRegion="polite">{message}</Body></Card>}
    {!!bookingId && <Card>
      <H2>Rezervasyon kimlik kontrolü</H2>
      {readiness.isPending ? <SkeletonCard /> : readiness.isError ? <Body>Misafir bilgileri okunamadı; giriş yapmadan önce yeniden kontrol edin.</Body> : readiness.data?.operational_visible === false ? <Muted>Bu konaklamanın KBS ekranı görünürlük süresi doldu. Kimlik ayrıntıları burada gösterilmez.</Muted> : <>
        <Body>{readiness.data?.ready ? 'Kayıtlı misafirlerin KBS zorunlu alanları hazır.' : 'Eksik bilgileri girişten önce tamamlayın.'}</Body>
        {!!readiness.data?.unregistered_occupants && <Body>{readiness.data.unregistered_occupants} konaklayan için ayrı misafir kaydı eklenmeli.</Body>}
        {readiness.data?.guests.map(g => <View key={g.guest_id} style={{ gap: spacing.xs, paddingVertical: spacing.sm }}>
          <Body>{g.guest_name}</Body><Muted>{g.ready ? 'Zorunlu alanlar tamam' : kbsMissingText(g.missing_fields)}</Muted>
          {canEdit && <Button title="Kimlik bilgilerini tamamla / düzelt" variant="secondary" onPress={() => { setEditing(g); setIdentity({ ...emptyKbsIdentity(), name: g.guest_name }); setMessage(''); }} />}
        </View>)}
        {canEdit && <Button title="Konaklayan ekle / kimlik tara" variant="secondary" onPress={() => router.push({ pathname: ROUTES.checkin, params: { booking_id: bookingId } })} />}
      </>}
      {editing && canEdit && <View style={{ gap: spacing.sm }}>
        <KbsIdentityFields value={identity} onChange={setIdentity} />
        <Button title="Bilgileri kaydet" onPress={() => save.mutate()} loading={save.isPending} disabled={save.isPending} />
        <Button title="Vazgeç" variant="ghost" onPress={() => { setEditing(null); setIdentity(emptyKbsIdentity()); }} disabled={save.isPending} />
      </View>}
      <Button title="Tüm bildirimleri göster" variant="ghost" onPress={() => { setBookingId(''); setSkip(0); setEditing(null); setIdentity(emptyKbsIdentity()); }} />
    </Card>}
    {jobs.isPending ? <SkeletonCard /> : jobs.isError ? <Card accent={c.danger}><Body>Bildirim listesi okunamadı; boş veya gönderilmiş sayılmadı.</Body><Button title="Yeniden kontrol et" onPress={() => void refresh()} /></Card>
      : !jobs.data?.items.length ? <EmptyState icon="shield-checkmark-outline" title="Bu görünümde bildirim yok" message="Kayıt olmaması bildirimlerin tamamlandığını göstermez. Rezervasyonun kimlik ve bağlantı durumunu kontrol edin." />
      : jobs.data.items.map(job => <Card key={job.id} accent={job.delivery_uncertain ? c.danger : job.status === 'done' && !job.kbs_test ? c.success : c.warning}>
        <H2>{job.guest_name}</H2><Muted>Oda {job.room_number || '—'} · {job.action === 'checkout' ? 'Çıkış' : 'Giriş'}</Muted>
        <Body>{kbsStatusLabel(job)}</Body>
        {job.delivery_uncertain && <Muted>Kurum kaydı uzlaştırılmadan tekrar gönderilemez. Diğer misafirler kuyrukta ilerlemeye devam eder.</Muted>}
        <Button title="Rezervasyon / eksik bilgiler" variant="secondary" onPress={() => { setBookingId(job.booking_id); setEditing(null); setIdentity(emptyKbsIdentity()); }} />
        {canEdit && job.can_retry && <Button title="Düzeltilen kaydı yeniden kuyruğa al" variant="secondary" onPress={() => retry.mutate(job.id)} disabled={retry.isPending} />}
      </Card>)}
    <View style={{ flexDirection: 'row', gap: spacing.sm }}>
      <Button title="Önceki" variant="secondary" disabled={!skip} onPress={() => setSkip(Math.max(0, skip - 50))} />
      <Button title="Sonraki" variant="secondary" disabled={!jobs.data?.has_more} onPress={() => setSkip(skip + 50)} />
    </View>
  </ScrollView>;
}
