import { t } from "i18next";
/**
 * Conflict Queue Page (CM-Hardening Turu #1c, May 2026)
 * ======================================================
 *
 * Front-desk facing UI for resolving OTA-driven `pending_assignment`
 * bookings (rooms that could not be claimed atomically when imported
 * from Exely / HotelRunner / B2B / agency portals).
 *
 * Backed by `routers/cm_conflict_queue.py`:
 *   GET    /channel-manager/conflict-queue            → list                (Turu #1b)
 *   GET    /channel-manager/conflict-queue/count      → KPI                 (Turu #1b)
 *   POST   /channel-manager/conflict-queue/{id}/resolve {"room_id"}         (Turu #1b)
 *   POST   /channel-manager/conflict-queue/bulk-resolve {"items":[...]}     (Turu #2)
 *
 * Renders embedded inside <ChannelHub> as the "Çakışmalar" tab — so this
 * component does NOT include its own Layout or PageHeader (Hub owns the
 * page chrome). Standalone usage would need a wrapping route.
 */
import { useMemo, useState, useEffect } from 'react';
import { useQuery, useMutation, useQueryClient } from '@tanstack/react-query';
import axios from 'axios';
import { toast } from 'sonner';
import { AlertTriangle, RefreshCw, CheckCircle, Inbox, Loader2, Building2, Layers } from 'lucide-react';
import { Card, CardContent, CardHeader, CardTitle, CardDescription } from '@/components/ui/card';
import { Button } from '@/components/ui/button';
import { KpiCard } from '@/components/ui/kpi-card';
import { StatusBadge } from '@/components/ui/status-badge';
import { Checkbox } from '@/components/ui/checkbox';
import { Dialog, DialogContent, DialogHeader, DialogTitle, DialogDescription, DialogFooter } from '@/components/ui/dialog';
import { Select, SelectContent, SelectItem, SelectTrigger, SelectValue } from '@/components/ui/select';
import { formatCurrency } from '@/lib/currency';
const QK_LIST = ['cm-conflict-queue', 'list'];
const QK_ROOMS = ['cm-conflict-queue', 'rooms'];
// Server enforces this cap on /bulk-resolve (BulkResolveRequest.max_length).
// Mirror it in the UI so "Tümünü Seç" + a 200-row queue doesn't trigger a 422.
const BULK_LIMIT = 50;
function fmtDate(iso) {
  if (!iso) return '—';
  return String(iso).slice(0, 10);
}
function ChannelChip({
  channel
}) {
  if (!channel) return <StatusBadge intent="neutral">{t("cm.pages_ConflictQueuePage.do\u011Frudan")}</StatusBadge>;
  const lower = String(channel).toLowerCase();
  let intent = 'info';
  if (lower.includes('exely')) intent = 'info';else if (lower.includes('hotelrunner') || lower.includes('hr')) intent = 'success';else if (lower.includes('b2b') || lower.includes('agency')) intent = 'warning';
  return <StatusBadge intent={intent}>{channel}</StatusBadge>;
}
export default function ConflictQueuePage({
  user,
  tenant,
  embedded = false
}) {
  // eslint-disable-line no-unused-vars
  const qc = useQueryClient();
  const [resolveTarget, setResolveTarget] = useState(null);
  const [selectedRoomId, setSelectedRoomId] = useState('');
  // Bulk-resolve state (Turu #2)
  const [selectedIds, setSelectedIds] = useState(() => new Set());
  const [bulkOpen, setBulkOpen] = useState(false);
  const [bulkAssignments, setBulkAssignments] = useState({}); // booking_id -> room_id

  const listQuery = useQuery({
    queryKey: QK_LIST,
    queryFn: async () => {
      const {
        data
      } = await axios.get('/channel-manager/conflict-queue', {
        params: {
          limit: 200
        }
      });
      return data;
    },
    refetchInterval: 30_000
  });

  // Available rooms — fetched once, filtered client-side per room_type when
  // the resolve dialog opens. Acceptable since /pms/rooms is cached server-
  // side and the typical hotel has < 1k rooms.
  const roomsQuery = useQuery({
    queryKey: QK_ROOMS,
    queryFn: async () => {
      const {
        data
      } = await axios.get('/pms/rooms', {
        params: {
          status: 'available',
          limit: 2000
        }
      });
      return Array.isArray(data) ? data : data?.items || [];
    },
    enabled: !!resolveTarget || bulkOpen,
    staleTime: 60_000
  });
  const resolveMutation = useMutation({
    mutationFn: async ({
      bookingId,
      roomId
    }) => {
      const {
        data
      } = await axios.post(`/channel-manager/conflict-queue/${bookingId}/resolve`, {
        room_id: roomId
      });
      return data;
    },
    onSuccess: data => {
      toast.success(`Oda atandı (${data.room_id})`, {
        description: `Rezervasyon ${data.booking_id} kuyruktan çıkarıldı.`
      });
      qc.invalidateQueries({
        queryKey: QK_LIST
      });
      qc.invalidateQueries({
        queryKey: QK_ROOMS
      });
      // Cross-page refresh — queryKeys.pms namespace covers Arrivals/Calendar/etc.
      qc.invalidateQueries({
        queryKey: ['pms']
      });
      setResolveTarget(null);
      setSelectedRoomId('');
    },
    onError: err => {
      // Architect follow-up: any error path may indicate stale local view
      // (another front-desk user may have grabbed the room or already resolved
      // the pending booking). Refresh both to avoid retry loops on stale data.
      qc.invalidateQueries({
        queryKey: QK_LIST
      });
      qc.invalidateQueries({
        queryKey: QK_ROOMS
      });
      const detail = err?.response?.data?.detail;
      // Backend 409 body: {error, message, conflict_night, conflicting_booking_id}
      if (err?.response?.status === 409 && detail?.error === 'room_not_available') {
        toast.error('Oda bu tarih aralığı için müsait değil', {
          description: `Çakışan gece: ${detail.conflict_night} · Mevcut rezervasyon: ${detail.conflicting_booking_id || '—'}`,
          duration: 8000
        });
        return;
      }
      const msg = typeof detail === 'string' ? detail : detail?.message || err?.message || 'Atama başarısız';
      toast.error(msg);
    }
  });
  const items = listQuery.data?.items || [];
  const total = listQuery.data?.total ?? items.length;

  // Drop selections that no longer appear in the latest list (resolved by
  // someone else, paginated out, etc.) so the toolbar count stays honest.
  useEffect(() => {
    if (selectedIds.size === 0) return;
    const visible = new Set(items.map(b => b.id));
    let changed = false;
    const next = new Set();
    selectedIds.forEach(id => {
      if (visible.has(id)) next.add(id);else changed = true;
    });
    if (changed) setSelectedIds(next);
  }, [items, selectedIds]);
  const allSelected = items.length > 0 && items.every(b => selectedIds.has(b.id));
  const toggleAll = () => {
    if (allSelected) {
      setSelectedIds(new Set());
    } else {
      // Cap at server's bulk limit; warn the operator if we had to truncate.
      const ids = items.slice(0, BULK_LIMIT).map(b => b.id);
      setSelectedIds(new Set(ids));
      if (items.length > BULK_LIMIT) {
        toast.warning(`İlk ${BULK_LIMIT} satır seçildi`, {
          description: `Toplu atama tek seferde en fazla ${BULK_LIMIT} satır işler.`
        });
      }
    }
  };
  const toggleOne = id => {
    const next = new Set(selectedIds);
    if (next.has(id)) {
      next.delete(id);
    } else {
      if (next.size >= BULK_LIMIT) {
        toast.warning(`En fazla ${BULK_LIMIT} satır seçilebilir`);
        return;
      }
      next.add(id);
    }
    setSelectedIds(next);
  };
  const bulkMutation = useMutation({
    mutationFn: async assignments => {
      const {
        data
      } = await axios.post('/channel-manager/conflict-queue/bulk-resolve', {
        items: assignments
      });
      return data;
    },
    onSettled: () => {
      qc.invalidateQueries({
        queryKey: QK_LIST
      });
      qc.invalidateQueries({
        queryKey: QK_ROOMS
      });
      qc.invalidateQueries({
        queryKey: ['pms']
      });
    },
    onSuccess: data => {
      const okCount = data.succeeded?.length || 0;
      const failCount = data.failed?.length || 0;
      if (okCount > 0 && failCount === 0) {
        toast.success(`${okCount} rezervasyon atandı`);
      } else if (okCount > 0 && failCount > 0) {
        toast.warning(`${okCount} başarılı, ${failCount} başarısız`, {
          description: 'Başarısız satırlar kuyrukta kalmaya devam ediyor.',
          duration: 8000
        });
      } else {
        toast.error(`${failCount} atama başarısız oldu`, {
          description: data.failed?.[0]?.error || 'Detaylar konsolda',
          duration: 8000
        });
      }
      // Drop only successful selections; keep failures so user can retry.
      const okIds = new Set((data.succeeded || []).map(r => r.booking_id));
      const remaining = new Set();
      selectedIds.forEach(id => {
        if (!okIds.has(id)) remaining.add(id);
      });
      setSelectedIds(remaining);
      // Same for assignments map.
      const nextAssign = {};
      Object.entries(bulkAssignments).forEach(([bid, rid]) => {
        if (!okIds.has(bid)) nextAssign[bid] = rid;
      });
      setBulkAssignments(nextAssign);
      if (failCount === 0) setBulkOpen(false);
    },
    onError: err => {
      const detail = err?.response?.data?.detail;
      const msg = typeof detail === 'string' ? detail : detail?.message || err?.message || 'Toplu atama başarısız';
      toast.error(msg);
    }
  });
  const openBulkDialog = () => {
    if (selectedIds.size === 0) {
      toast.warning('Önce en az bir rezervasyon seçin');
      return;
    }
    setBulkAssignments({}); // reset
    setBulkOpen(true);
  };
  const autoAssignBulk = () => {
    const all = roomsQuery.data || [];
    const used = new Set();
    const next = {
      ...bulkAssignments
    };
    items.filter(b => selectedIds.has(b.id)).forEach(b => {
      if (next[b.id] && !used.has(next[b.id])) {
        used.add(next[b.id]);
        return;
      }
      const sameType = all.filter(r => !used.has(r.id) && (!b.room_type || (r.room_type || '').toLowerCase() === String(b.room_type).toLowerCase()));
      const candidate = sameType[0] || all.find(r => !used.has(r.id));
      if (candidate) {
        next[b.id] = candidate.id;
        used.add(candidate.id);
      }
    });
    setBulkAssignments(next);
  };
  const handleBulkSubmit = () => {
    const assignments = items.filter(b => selectedIds.has(b.id) && bulkAssignments[b.id]).map(b => ({
      booking_id: b.id,
      room_id: bulkAssignments[b.id]
    }));
    if (assignments.length === 0) {
      toast.warning('En az bir satır için oda seçin');
      return;
    }
    bulkMutation.mutate(assignments);
  };

  // Open the rooms query when the bulk dialog opens too (not only single dialog).
  // Achieved by toggling enabled via a derived condition reused below.

  const candidateRooms = useMemo(() => {
    if (!resolveTarget) return [];
    const all = roomsQuery.data || [];
    const wantedType = resolveTarget.room_type;
    if (!wantedType) return all;
    const sameType = all.filter(r => (r.room_type || '').toLowerCase() === String(wantedType).toLowerCase());
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
    resolveMutation.mutate({
      bookingId: resolveTarget.id,
      roomId: selectedRoomId
    });
  };
  const refreshing = listQuery.isFetching && !listQuery.isLoading;
  return <div className="space-y-4" data-testid="conflict-queue-page">
      {/* Header strip — Hub provides the page H1, we just label the section. */}
      <div className="flex items-center justify-between gap-3">
        <div className="flex items-center gap-3">
          <div className="w-10 h-10 rounded-lg bg-amber-50 flex items-center justify-center">
            <AlertTriangle className="w-5 h-5 text-amber-600" />
          </div>
          <div>
            <h2 className="text-lg font-semibold text-gray-900">{t("cm.pages_ConflictQueuePage.atama_bekleyen_ota_rezervasyon")}</h2>
            <p className="text-sm text-gray-500">{t("cm.pages_ConflictQueuePage.kanal_\xFCzerinden_gelip_oda_atan")}</p>
          </div>
        </div>
        <div className="flex items-center gap-2">
          {selectedIds.size > 0 ? <Button size="sm" onClick={openBulkDialog} data-testid="conflict-bulk-open">
              <Layers className="w-4 h-4 mr-1.5" />{t("cm.pages_ConflictQueuePage.toplu_ata")}{selectedIds.size})
            </Button> : null}
          <Button variant="outline" size="sm" onClick={() => listQuery.refetch()} disabled={refreshing} data-testid="conflict-queue-refresh">
            <RefreshCw className={`w-4 h-4 mr-1.5 ${refreshing ? 'animate-spin' : ''}`} />{t("cm.pages_ConflictQueuePage.yenile")}</Button>
        </div>
      </div>

      {/* KPI strip */}
      <div className="grid grid-cols-1 md:grid-cols-3 gap-4">
        <KpiCard icon={Inbox} label={t("cm.pages_ConflictQueuePage.bekleyen_rezervasyon")} value={total} sub={total === 0 ? 'Tüm OTA atamaları güncel' : 'Manuel çözüm gerekli'} intent={total === 0 ? 'success' : 'warning'} />
        <KpiCard icon={Building2} label={t("cm.pages_ConflictQueuePage.etkilenen_kanallar")} value={new Set(items.map(b => b.channel || b.source || 'unknown')).size} sub="Farklı kanal kaynağı" intent="info" />
        <KpiCard icon={CheckCircle} label={t("cm.pages_ConflictQueuePage.bu_sayfa_otomatik")} value="30sn" sub="Yenileme periyodu" intent="neutral" />
      </div>

      {/* List */}
      <Card>
        <CardHeader>
          <CardTitle className="text-base">{t("cm.pages_ConflictQueuePage.kuyruk")}</CardTitle>
          <CardDescription>{t("cm.pages_ConflictQueuePage.en_yeni_kay\u0131t_\xF6nce_atama_oda_g")}</CardDescription>
        </CardHeader>
        <CardContent>
          {listQuery.isLoading ? <div className="flex items-center justify-center py-12">
              <Loader2 className="w-6 h-6 animate-spin text-amber-600" />
            </div> : listQuery.isError ? <div className="text-sm text-red-600 py-4">{t("cm.pages_ConflictQueuePage.liste_y\xFCklenemedi")}{listQuery.error?.message || 'bilinmeyen hata'}
            </div> : items.length === 0 ? <div className="text-center py-12 text-gray-500">
              <Inbox className="w-10 h-10 mx-auto mb-3 text-gray-300" />
              <p className="text-sm">{t("cm.pages_ConflictQueuePage.atama_bekleyen_rezervasyon_yok")}</p>
              <p className="text-xs mt-1">{t("cm.pages_ConflictQueuePage.kanal_entegrasyonlar\u0131_sorunsuz")}</p>
            </div> : <div className="overflow-x-auto">
              <table className="w-full text-sm">
                <thead className="text-xs uppercase text-gray-500 border-b">
                  <tr>
                    <th className="py-2 px-2 w-8">
                      <Checkbox checked={allSelected} onCheckedChange={toggleAll} aria-label="Tümünü seç" data-testid="conflict-select-all" />
                    </th>
                    <th className="text-left py-2 px-2">{t("cm.pages_ConflictQueuePage.misafir")}</th>
                    <th className="text-left py-2 px-2">{t("cm.pages_ConflictQueuePage.kanal")}</th>
                    <th className="text-left py-2 px-2">{t("cm.pages_ConflictQueuePage.oda_tipi")}</th>
                    <th className="text-left py-2 px-2">{t("cm.pages_ConflictQueuePage.giri\u015F")}</th>
                    <th className="text-left py-2 px-2">{t("cm.pages_ConflictQueuePage.\xE7\u0131k\u0131\u015F")}</th>
                    <th className="text-right py-2 px-2">{t("cm.pages_ConflictQueuePage.tutar")}</th>
                    <th className="text-left py-2 px-2">{t("cm.pages_ConflictQueuePage.onay_no")}</th>
                    <th className="text-right py-2 px-2">{t("cm.pages_ConflictQueuePage.i_\u015Flem")}</th>
                  </tr>
                </thead>
                <tbody>
                  {items.map(b => <tr key={b.id} className={`border-b last:border-b-0 hover:bg-gray-50 ${selectedIds.has(b.id) ? 'bg-amber-50/40' : ''}`} data-testid={`conflict-row-${b.id}`}>
                      <td className="py-2 px-2">
                        <Checkbox checked={selectedIds.has(b.id)} onCheckedChange={() => toggleOne(b.id)} aria-label={`Seç: ${b.guest_name || b.id}`} data-testid={`conflict-select-${b.id}`} />
                      </td>
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
                        <Button size="sm" onClick={() => {
                    setResolveTarget(b);
                    setSelectedRoomId('');
                  }} data-testid={`conflict-resolve-${b.id}`}>{t("cm.pages_ConflictQueuePage.oda_ata")}</Button>
                      </td>
                    </tr>)}
                </tbody>
              </table>
            </div>}
        </CardContent>
      </Card>

      {/* Resolve dialog */}
      <Dialog open={!!resolveTarget} onOpenChange={open => {
      if (!open) {
        setResolveTarget(null);
        setSelectedRoomId('');
      }
    }}>
        <DialogContent className="sm:max-w-lg" data-testid="conflict-resolve-dialog">
          <DialogHeader>
            <DialogTitle>{t("cm.pages_ConflictQueuePage.oda_atamas\u0131")}</DialogTitle>
            <DialogDescription>
              {resolveTarget?.guest_name || 'Misafir'} · {fmtDate(resolveTarget?.check_in)} → {fmtDate(resolveTarget?.check_out)}
              {resolveTarget?.room_type ? ` · ${resolveTarget.room_type}` : ''}
            </DialogDescription>
          </DialogHeader>

          <div className="space-y-3 py-2">
            <div className="flex items-center justify-between gap-2">
              <label className="text-sm font-medium text-gray-700">{t("cm.pages_ConflictQueuePage.m\xFCsait_oda")}</label>
              <Button type="button" variant="outline" size="sm" onClick={handleSuggestRoom} disabled={roomsQuery.isLoading || candidateRooms.length === 0} data-testid="conflict-suggest-room">
                {roomsQuery.isLoading ? <Loader2 className="w-3.5 h-3.5 animate-spin" /> : 'İlk Müsaiti Öner'}
              </Button>
            </div>

            <Select value={selectedRoomId} onValueChange={setSelectedRoomId}>
              <SelectTrigger data-testid="conflict-room-select">
                <SelectValue placeholder={roomsQuery.isLoading ? 'Odalar yükleniyor…' : candidateRooms.length === 0 ? 'Bu oda tipi için müsait oda yok' : 'Oda seçin'} />
              </SelectTrigger>
              <SelectContent>
                {candidateRooms.map(r => <SelectItem key={r.id} value={r.id}>{t("cm.pages_ConflictQueuePage.oda")}{r.room_number} · {r.room_type || 'tip yok'}
                    {r.floor != null ? ` · K:${r.floor}` : ''}
                  </SelectItem>)}
              </SelectContent>
            </Select>

            {resolveTarget?.special_requests ? <div className="text-xs text-gray-500 border-l-2 border-amber-300 pl-2 py-1">
                <strong>{t("cm.pages_ConflictQueuePage.misafir_notu")}</strong> {resolveTarget.special_requests}
              </div> : null}
          </div>

          <DialogFooter>
            <Button variant="outline" onClick={() => {
            setResolveTarget(null);
            setSelectedRoomId('');
          }} disabled={resolveMutation.isPending}>{t("cm.pages_ConflictQueuePage.i_ptal")}</Button>
            <Button onClick={handleResolve} disabled={!selectedRoomId || resolveMutation.isPending} data-testid="conflict-confirm-assign">
              {resolveMutation.isPending ? <><Loader2 className="w-4 h-4 mr-2 animate-spin" />{t("cm.pages_ConflictQueuePage.atan\u0131yor")}</> : 'Atamayı Onayla'}
            </Button>
          </DialogFooter>
        </DialogContent>
      </Dialog>

      {/* Bulk resolve dialog (Turu #2) */}
      <Dialog open={bulkOpen} onOpenChange={open => {
      if (!open && !bulkMutation.isPending) {
        setBulkOpen(false);
      }
    }}>
        <DialogContent className="sm:max-w-2xl" data-testid="conflict-bulk-dialog">
          <DialogHeader>
            <DialogTitle>{t("cm.pages_ConflictQueuePage.toplu_oda_atamas\u0131")}</DialogTitle>
            <DialogDescription>{t("cm.pages_ConflictQueuePage.se\xE7ili")}{selectedIds.size}{t("cm.pages_ConflictQueuePage.rezervasyon_i\xE7in_her_sat\u0131ra_bi")}</DialogDescription>
          </DialogHeader>

          <div className="space-y-3 py-2 max-h-[60vh] overflow-y-auto">
            <div className="flex justify-end">
              <Button type="button" variant="outline" size="sm" onClick={autoAssignBulk} disabled={roomsQuery.isLoading || (roomsQuery.data || []).length === 0} data-testid="conflict-bulk-autoassign">
                {roomsQuery.isLoading ? <Loader2 className="w-3.5 h-3.5 animate-spin mr-1.5" /> : null}{t("cm.pages_ConflictQueuePage.t\xFCm\xFCn\xFC_otomatik_ata")}</Button>
            </div>

            <table className="w-full text-sm">
              <thead className="text-xs uppercase text-gray-500 border-b">
                <tr>
                  <th className="text-left py-1.5 px-2">{t("cm.pages_ConflictQueuePage.misafir")}</th>
                  <th className="text-left py-1.5 px-2">{t("cm.pages_ConflictQueuePage.tip_tarih")}</th>
                  <th className="text-left py-1.5 px-2 w-64">{t("cm.pages_ConflictQueuePage.atanacak_oda")}</th>
                </tr>
              </thead>
              <tbody>
                {items.filter(b => selectedIds.has(b.id)).map(b => {
                const all = roomsQuery.data || [];
                const wantedType = b.room_type;
                const filtered = wantedType ? all.filter(r => (r.room_type || '').toLowerCase() === String(wantedType).toLowerCase()).length ? all.filter(r => (r.room_type || '').toLowerCase() === String(wantedType).toLowerCase()) : all : all;
                return <tr key={b.id} className="border-b last:border-b-0">
                      <td className="py-2 px-2 font-medium text-gray-900">
                        {b.guest_name || 'Misafir'}
                        <div className="text-xs text-gray-500">{b.external_confirmation || b.id.slice(0, 8)}</div>
                      </td>
                      <td className="py-2 px-2 text-gray-700">
                        {b.room_type || '—'}
                        <div className="text-xs text-gray-500">
                          {fmtDate(b.check_in)} → {fmtDate(b.check_out)}
                        </div>
                      </td>
                      <td className="py-2 px-2">
                        <Select value={bulkAssignments[b.id] || ''} onValueChange={v => setBulkAssignments({
                      ...bulkAssignments,
                      [b.id]: v
                    })}>
                          <SelectTrigger data-testid={`conflict-bulk-room-${b.id}`}>
                            <SelectValue placeholder={roomsQuery.isLoading ? 'Yükleniyor…' : filtered.length === 0 ? 'Müsait oda yok' : 'Oda seçin'} />
                          </SelectTrigger>
                          <SelectContent>
                            {filtered.map(r => <SelectItem key={r.id} value={r.id}>{t("cm.pages_ConflictQueuePage.oda")}{r.room_number} · {r.room_type || 'tip yok'}
                              </SelectItem>)}
                          </SelectContent>
                        </Select>
                      </td>
                    </tr>;
              })}
              </tbody>
            </table>
          </div>

          <DialogFooter>
            <Button variant="outline" onClick={() => setBulkOpen(false)} disabled={bulkMutation.isPending}>{t("cm.pages_ConflictQueuePage.i_ptal")}</Button>
            <Button onClick={handleBulkSubmit} disabled={bulkMutation.isPending || Object.keys(bulkAssignments).length === 0} data-testid="conflict-bulk-submit">
              {bulkMutation.isPending ? <><Loader2 className="w-4 h-4 mr-2 animate-spin" />{t("cm.pages_ConflictQueuePage.atan\u0131yor")}</> : `Atamayı Onayla (${Object.keys(bulkAssignments).length})`}
            </Button>
          </DialogFooter>
        </DialogContent>
      </Dialog>
    </div>;
}