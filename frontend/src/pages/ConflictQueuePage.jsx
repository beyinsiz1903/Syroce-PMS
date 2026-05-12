/**
 * Conflict Queue Page (CM-Hardening Turu #1c, May 2026)
 * ======================================================
 *
 * Front-desk facing UI for resolving OTA-driven `pending_assignment`
 * bookings (rooms that could not be claimed atomically when imported
 * from Exely / HotelRunner / B2B / agency portals).
 *
 * Backed by `routers/cm_conflict_queue.py` (Turu #1b):
 *   GET    /channel-manager/conflict-queue          → list
 *   GET    /channel-manager/conflict-queue/count    → KPI
 *   POST   /channel-manager/conflict-queue/{id}/resolve {"room_id"}
 *
 * Renders embedded inside <ChannelHub> as the "Çakışmalar" tab — so this
 * component does NOT include its own Layout or PageHeader (Hub owns the
 * page chrome). Standalone usage would need a wrapping route.
 */
import { useMemo, useState } from 'react';
import { useQuery, useMutation, useQueryClient } from '@tanstack/react-query';
import axios from 'axios';
import { toast } from 'sonner';
import {
  AlertTriangle, RefreshCw, CheckCircle, Inbox, Loader2, Building2,
} from 'lucide-react';

import { Card, CardContent, CardHeader, CardTitle, CardDescription } from '@/components/ui/card';
import { Button } from '@/components/ui/button';
import { KpiCard } from '@/components/ui/kpi-card';
import { StatusBadge } from '@/components/ui/status-badge';
import {
  Dialog, DialogContent, DialogHeader, DialogTitle, DialogDescription, DialogFooter,
} from '@/components/ui/dialog';
import {
  Select, SelectContent, SelectItem, SelectTrigger, SelectValue,
} from '@/components/ui/select';
import { formatCurrency } from '@/lib/currency';

const QK_LIST = ['cm-conflict-queue', 'list'];
const QK_ROOMS = ['cm-conflict-queue', 'rooms'];

function fmtDate(iso) {
  if (!iso) return '—';
  return String(iso).slice(0, 10);
}

function ChannelChip({ channel }) {
  if (!channel) return <StatusBadge intent="neutral">Doğrudan</StatusBadge>;
  const lower = String(channel).toLowerCase();
  let intent = 'info';
  if (lower.includes('exely')) intent = 'info';
  else if (lower.includes('hotelrunner') || lower.includes('hr')) intent = 'success';
  else if (lower.includes('b2b') || lower.includes('agency')) intent = 'warning';
  return <StatusBadge intent={intent}>{channel}</StatusBadge>;
}

export default function ConflictQueuePage({ user, tenant, embedded = false }) { // eslint-disable-line no-unused-vars
  const qc = useQueryClient();
  const [resolveTarget, setResolveTarget] = useState(null);
  const [selectedRoomId, setSelectedRoomId] = useState('');

  const listQuery = useQuery({
    queryKey: QK_LIST,
    queryFn: async () => {
      const { data } = await axios.get('/channel-manager/conflict-queue', {
        params: { limit: 200 },
      });
      return data;
    },
    refetchInterval: 30_000,
  });

  // Available rooms — fetched once, filtered client-side per room_type when
  // the resolve dialog opens. Acceptable since /pms/rooms is cached server-
  // side and the typical hotel has < 1k rooms.
  const roomsQuery = useQuery({
    queryKey: QK_ROOMS,
    queryFn: async () => {
      const { data } = await axios.get('/pms/rooms', {
        params: { status: 'available', limit: 2000 },
      });
      return Array.isArray(data) ? data : (data?.items || []);
    },
    enabled: !!resolveTarget,
    staleTime: 60_000,
  });

  const resolveMutation = useMutation({
    mutationFn: async ({ bookingId, roomId }) => {
      const { data } = await axios.post(
        `/channel-manager/conflict-queue/${bookingId}/resolve`,
        { room_id: roomId },
      );
      return data;
    },
    onSuccess: (data) => {
      toast.success(`Oda atandı (${data.room_id})`, {
        description: `Rezervasyon ${data.booking_id} kuyruktan çıkarıldı.`,
      });
      qc.invalidateQueries({ queryKey: QK_LIST });
      qc.invalidateQueries({ queryKey: QK_ROOMS });
      // Cross-page refresh — queryKeys.pms namespace covers Arrivals/Calendar/etc.
      qc.invalidateQueries({ queryKey: ['pms'] });
      setResolveTarget(null);
      setSelectedRoomId('');
    },
    onError: (err) => {
      // Architect follow-up: any error path may indicate stale local view
      // (another front-desk user may have grabbed the room or already resolved
      // the pending booking). Refresh both to avoid retry loops on stale data.
      qc.invalidateQueries({ queryKey: QK_LIST });
      qc.invalidateQueries({ queryKey: QK_ROOMS });
      const detail = err?.response?.data?.detail;
      // Backend 409 body: {error, message, conflict_night, conflicting_booking_id}
      if (err?.response?.status === 409 && detail?.error === 'room_not_available') {
        toast.error('Oda bu tarih aralığı için müsait değil', {
          description: `Çakışan gece: ${detail.conflict_night} · Mevcut rezervasyon: ${detail.conflicting_booking_id || '—'}`,
          duration: 8000,
        });
        return;
      }
      const msg = typeof detail === 'string' ? detail : (detail?.message || err?.message || 'Atama başarısız');
      toast.error(msg);
    },
  });

  const items = listQuery.data?.items || [];
  const total = listQuery.data?.total ?? items.length;

  const candidateRooms = useMemo(() => {
    if (!resolveTarget) return [];
    const all = roomsQuery.data || [];
    const wantedType = resolveTarget.room_type;
    if (!wantedType) return all;
    const sameType = all.filter((r) => (r.room_type || '').toLowerCase() === String(wantedType).toLowerCase());
    return sameType.length ? sameType : all; // fallback: show all if no type match
  }, [resolveTarget, roomsQuery.data]);

  const handleSuggestRoom = () => {
    if (candidateRooms.length === 0) {
      toast.warning('Bu oda tipi için müsait oda bulunamadı');
      return;
    }
    setSelectedRoomId(candidateRooms[0].id);
  };

  const handleResolve = () => {
    if (!resolveTarget || !selectedRoomId) {
      toast.warning('Lütfen bir oda seçin');
      return;
    }
    resolveMutation.mutate({ bookingId: resolveTarget.id, roomId: selectedRoomId });
  };

  const refreshing = listQuery.isFetching && !listQuery.isLoading;

  return (
    <div className="space-y-4" data-testid="conflict-queue-page">
      {/* Header strip — Hub provides the page H1, we just label the section. */}
      <div className="flex items-center justify-between gap-3">
        <div className="flex items-center gap-3">
          <div className="w-10 h-10 rounded-lg bg-amber-50 flex items-center justify-center">
            <AlertTriangle className="w-5 h-5 text-amber-600" />
          </div>
          <div>
            <h2 className="text-lg font-semibold text-gray-900">
              Atama Bekleyen OTA Rezervasyonları
            </h2>
            <p className="text-sm text-gray-500">
              Kanal üzerinden gelip oda atanamayan rezervasyonları manuel olarak çözün.
            </p>
          </div>
        </div>
        <Button
          variant="outline"
          size="sm"
          onClick={() => listQuery.refetch()}
          disabled={refreshing}
          data-testid="conflict-queue-refresh"
        >
          <RefreshCw className={`w-4 h-4 mr-1.5 ${refreshing ? 'animate-spin' : ''}`} />
          Yenile
        </Button>
      </div>

      {/* KPI strip */}
      <div className="grid grid-cols-1 md:grid-cols-3 gap-4">
        <KpiCard
          icon={Inbox}
          label="Bekleyen Rezervasyon"
          value={total}
          sub={total === 0 ? 'Tüm OTA atamaları güncel' : 'Manuel çözüm gerekli'}
          intent={total === 0 ? 'success' : 'warning'}
        />
        <KpiCard
          icon={Building2}
          label="Etkilenen Kanallar"
          value={new Set(items.map((b) => b.channel || b.source || 'unknown')).size}
          sub="Farklı kanal kaynağı"
          intent="info"
        />
        <KpiCard
          icon={CheckCircle}
          label="Bu Sayfa Otomatik"
          value="30sn"
          sub="Yenileme periyodu"
          intent="neutral"
        />
      </div>

      {/* List */}
      <Card>
        <CardHeader>
          <CardTitle className="text-base">Kuyruk</CardTitle>
          <CardDescription>
            En yeni kayıt önce. Atama, oda-gece kilit indeksi üzerinden atomik olarak yapılır;
            başka bir rezervasyonla çakışırsa atama reddedilir ve hata bildirilir.
          </CardDescription>
        </CardHeader>
        <CardContent>
          {listQuery.isLoading ? (
            <div className="flex items-center justify-center py-12">
              <Loader2 className="w-6 h-6 animate-spin text-amber-600" />
            </div>
          ) : listQuery.isError ? (
            <div className="text-sm text-red-600 py-4">
              Liste yüklenemedi: {listQuery.error?.message || 'bilinmeyen hata'}
            </div>
          ) : items.length === 0 ? (
            <div className="text-center py-12 text-gray-500">
              <Inbox className="w-10 h-10 mx-auto mb-3 text-gray-300" />
              <p className="text-sm">Atama bekleyen rezervasyon yok.</p>
              <p className="text-xs mt-1">Kanal entegrasyonları sorunsuz çalışıyor.</p>
            </div>
          ) : (
            <div className="overflow-x-auto">
              <table className="w-full text-sm">
                <thead className="text-xs uppercase text-gray-500 border-b">
                  <tr>
                    <th className="text-left py-2 px-2">Misafir</th>
                    <th className="text-left py-2 px-2">Kanal</th>
                    <th className="text-left py-2 px-2">Oda Tipi</th>
                    <th className="text-left py-2 px-2">Giriş</th>
                    <th className="text-left py-2 px-2">Çıkış</th>
                    <th className="text-right py-2 px-2">Tutar</th>
                    <th className="text-left py-2 px-2">Onay No</th>
                    <th className="text-right py-2 px-2">İşlem</th>
                  </tr>
                </thead>
                <tbody>
                  {items.map((b) => (
                    <tr
                      key={b.id}
                      className="border-b last:border-b-0 hover:bg-gray-50"
                      data-testid={`conflict-row-${b.id}`}
                    >
                      <td className="py-2 px-2 font-medium text-gray-900">{b.guest_name || 'Misafir'}</td>
                      <td className="py-2 px-2"><ChannelChip channel={b.channel || b.source} /></td>
                      <td className="py-2 px-2 text-gray-700">{b.room_type || '—'}</td>
                      <td className="py-2 px-2 text-gray-700">{fmtDate(b.check_in)}</td>
                      <td className="py-2 px-2 text-gray-700">{fmtDate(b.check_out)}</td>
                      <td className="py-2 px-2 text-right text-gray-700">
                        {b.total_amount != null ? formatCurrency(b.total_amount, b.currency || 'TRY') : '—'}
                      </td>
                      <td className="py-2 px-2 text-xs text-gray-500 font-mono">{b.external_confirmation || '—'}</td>
                      <td className="py-2 px-2 text-right">
                        <Button
                          size="sm"
                          onClick={() => { setResolveTarget(b); setSelectedRoomId(''); }}
                          data-testid={`conflict-resolve-${b.id}`}
                        >
                          Oda Ata
                        </Button>
                      </td>
                    </tr>
                  ))}
                </tbody>
              </table>
            </div>
          )}
        </CardContent>
      </Card>

      {/* Resolve dialog */}
      <Dialog
        open={!!resolveTarget}
        onOpenChange={(open) => {
          if (!open) {
            setResolveTarget(null);
            setSelectedRoomId('');
          }
        }}
      >
        <DialogContent className="sm:max-w-lg" data-testid="conflict-resolve-dialog">
          <DialogHeader>
            <DialogTitle>Oda Ataması</DialogTitle>
            <DialogDescription>
              {resolveTarget?.guest_name || 'Misafir'} · {fmtDate(resolveTarget?.check_in)} → {fmtDate(resolveTarget?.check_out)}
              {resolveTarget?.room_type ? ` · ${resolveTarget.room_type}` : ''}
            </DialogDescription>
          </DialogHeader>

          <div className="space-y-3 py-2">
            <div className="flex items-center justify-between gap-2">
              <label className="text-sm font-medium text-gray-700">Müsait Oda</label>
              <Button
                type="button"
                variant="outline"
                size="sm"
                onClick={handleSuggestRoom}
                disabled={roomsQuery.isLoading || candidateRooms.length === 0}
                data-testid="conflict-suggest-room"
              >
                {roomsQuery.isLoading ? (
                  <Loader2 className="w-3.5 h-3.5 animate-spin" />
                ) : (
                  'İlk Müsaiti Öner'
                )}
              </Button>
            </div>

            <Select value={selectedRoomId} onValueChange={setSelectedRoomId}>
              <SelectTrigger data-testid="conflict-room-select">
                <SelectValue placeholder={
                  roomsQuery.isLoading
                    ? 'Odalar yükleniyor…'
                    : candidateRooms.length === 0
                      ? 'Bu oda tipi için müsait oda yok'
                      : 'Oda seçin'
                } />
              </SelectTrigger>
              <SelectContent>
                {candidateRooms.map((r) => (
                  <SelectItem key={r.id} value={r.id}>
                    Oda {r.room_number} · {r.room_type || 'tip yok'}
                    {r.floor != null ? ` · K:${r.floor}` : ''}
                  </SelectItem>
                ))}
              </SelectContent>
            </Select>

            {resolveTarget?.special_requests ? (
              <div className="text-xs text-gray-500 border-l-2 border-amber-300 pl-2 py-1">
                <strong>Misafir notu:</strong> {resolveTarget.special_requests}
              </div>
            ) : null}
          </div>

          <DialogFooter>
            <Button
              variant="outline"
              onClick={() => { setResolveTarget(null); setSelectedRoomId(''); }}
              disabled={resolveMutation.isPending}
            >
              İptal
            </Button>
            <Button
              onClick={handleResolve}
              disabled={!selectedRoomId || resolveMutation.isPending}
              data-testid="conflict-confirm-assign"
            >
              {resolveMutation.isPending ? (
                <><Loader2 className="w-4 h-4 mr-2 animate-spin" />Atanıyor…</>
              ) : (
                'Atamayı Onayla'
              )}
            </Button>
          </DialogFooter>
        </DialogContent>
      </Dialog>
    </div>
  );
}
