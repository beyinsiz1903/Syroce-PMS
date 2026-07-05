import { useCallback, useEffect, useMemo, useState } from 'react';
import axios from 'axios';
import { toast } from 'sonner';

import { Card, CardContent } from '@/components/ui/card';
import { Button } from '@/components/ui/button';
import { Input } from '@/components/ui/input';
import { Label } from '@/components/ui/label';
import { PageHeader } from '@/components/ui/page-header';
import { KpiCard } from '@/components/ui/kpi-card';
import { StatusBadge } from '@/components/ui/status-badge';
import {
  Dialog, DialogContent, DialogDescription, DialogFooter, DialogHeader, DialogTitle,
} from '@/components/ui/dialog';
import {
  AlertTriangle, UserX, Calendar, RefreshCw, Loader2, Search, Phone, MessageSquare,
  Clock, FileText, X,
} from 'lucide-react';
import { confirmDialog } from '@/lib/dialogs';
import { useTranslation } from 'react-i18next';

const localISODate = (d) => {
  const y = d.getFullYear();
  const m = String(d.getMonth() + 1).padStart(2, '0');
  const day = String(d.getDate()).padStart(2, '0');
  return `${y}-${m}-${day}`;
};

const fmtTRY = (v) =>
  new Intl.NumberFormat('tr-TR', { style: 'currency', currency: 'TRY' }).format(Number(v || 0));

// tel:/sms: URI'larında XSS önlemek için telefonu sadece rakam ve + ile sınırla
const sanitizePhone = (raw) => (raw ? String(raw).replace(/[^\d+]/g, '') : '');

const STATUS_TR = {
  confirmed: 'Onaylı',
  guaranteed: 'Garantili',
  pending: 'Beklemede',
};
const STATUS_INTENT = {
  confirmed: 'info',
  guaranteed: 'warning',
  pending: 'neutral',
};

// ETA aşımı kontrolü — "HH:MM" + verilen tarihi local timezone'da kıyaslar
const minutesPastETA = (dateISO, etaHHMM) => {
  if (!etaHHMM) return null;
  const m = /^(\d{1,2}):(\d{2})$/.exec(etaHHMM);
  if (!m) return null;
  const eta = new Date(`${dateISO}T${m[1].padStart(2, '0')}:${m[2]}:00`);
  if (Number.isNaN(eta.getTime())) return null;
  return Math.floor((Date.now() - eta.getTime()) / 60000);
};

// No-show ceza tahmini: garanti varsa total_amount * 100% (ilk gece varsayımı)
const estimatedPenalty = (b) => {
  const status = (b.status || '').toLowerCase();
  if (status !== 'guaranteed') return 0;
  // Eğer ilk gece tutarı yoksa total üzerinden tahmin et
  return Number(b.first_night_amount || b.deposit_amount || b.total_amount || 0);
};

const PRIMARY_LABEL = (b) =>
  b.confirmation_number || (b.id || '').substring(0, 8).toUpperCase();

const NoShowToday = () => {
  const { t, i18n } = useTranslation();
  const [date, setDate] = useState(() => localISODate(new Date()));
  const [items, setItems] = useState([]);
  const [loading, setLoading] = useState(false);
  const [busyId, setBusyId] = useState(null);
  const [search, setSearch] = useState('');
  const [statusFilter, setStatusFilter] = useState('all'); // all | guaranteed | confirmed | pending
  const [otaOnly, setOtaOnly] = useState(false);
  const [selected, setSelected] = useState(new Set());
  const [bulkBusy, setBulkBusy] = useState(false);

  const [confirmTarget, setConfirmTarget] = useState(null);
  const [detail, setDetail] = useState(null);

  // Saatlik tikleme — ETA badge'leri canlı güncellensin
  const [tick, setTick] = useState(0);
  useEffect(() => {
    const t = setInterval(() => setTick((v) => v + 1), 60000);
    return () => clearInterval(t);
  }, []);

  const load = useCallback(async () => {
    setLoading(true);
    setSelected(new Set());
    try {
      const res = await axios.get(`/pms/arrivals?start_date=${date}&end_date=${date}&limit=500`);
      const list = res.data?.bookings || [];
      const pending = list.filter((b) =>
        ['confirmed', 'guaranteed', 'pending'].includes((b.status || '').toLowerCase()),
      );
      setItems(pending);
    } catch (e) {
      toast.error('Liste yüklenemedi');
      setItems([]);
    } finally {
      setLoading(false);
    }
  }, [date]);

  useEffect(() => { load(); }, [load]);

  // Filter + sort by ETA asc (en eski beklenen önce → en kritik üstte)
  const visible = useMemo(() => {
    void tick; // re-evaluate on minute tick
    const q = search.trim().toLowerCase();
    let arr = items.filter((b) => {
      const st = (b.status || '').toLowerCase();
      if (statusFilter !== 'all' && st !== statusFilter) return false;
      if (otaOnly && !(b.source && b.source !== 'direct')) return false;
      if (!q) return true;
      return String(b.room_number || '').includes(search)
        || (b.guest_name || '').toLowerCase().includes(q)
        || (b.confirmation_number || '').toLowerCase().includes(q);
    });
    arr = [...arr].sort((a, b) => {
      const ea = a.estimated_arrival_time || '14:00';
      const eb = b.estimated_arrival_time || '14:00';
      return ea.localeCompare(eb);
    });
    return arr;
  }, [items, search, statusFilter, otaOnly, tick]);

  const totalLoss = items.reduce((s, b) => s + (b.total_amount || 0), 0);
  const guaranteedCount = items.filter((b) => (b.status || '').toLowerCase() === 'guaranteed').length;
  const overdueCount = items.filter((b) => {
    const m = minutesPastETA(date, b.estimated_arrival_time);
    return m != null && m > 60;
  }).length;

  // Tek no-show
  const askNoShow = (b) => setConfirmTarget(b);
  const submitNoShow = async () => {
    if (!confirmTarget) return;
    setBusyId(confirmTarget.id);
    try {
      await axios.post('/pms-core/no-show', { booking_id: confirmTarget.id });
      toast.success('No-show işaretlendi');
      setConfirmTarget(null);
      load();
    } catch (e) {
      const detail = e.response?.data?.detail;
      const msg = typeof detail === 'string' ? detail : (detail?.message || detail?.error || 'No-show işaretlenemedi');
      toast.error(msg);
    } finally {
      setBusyId(null);
    }
  };

  const toggleSelect = (id) => {
    setSelected((prev) => {
      const n = new Set(prev);
      if (n.has(id)) n.delete(id); else n.add(id);
      return n;
    });
  };
  const toggleSelectAll = () => {
    if (selected.size === visible.length) setSelected(new Set());
    else setSelected(new Set(visible.map((b) => b.id)));
  };
  const bulkNoShow = async () => {
    if (selected.size === 0) return;
    const list = visible.filter((b) => selected.has(b.id));
    const totalPen = list.reduce((s, b) => s + estimatedPenalty(b), 0);
    const ok = await confirmDialog({
      message: `${list.length} rezervasyon no-show işaretlensin mi?` + (totalPen > 0 ? `\nToplam tahmini ceza: ${fmtTRY(totalPen)} folio'ya post edilecek.` : ''),
      variant: 'danger',
    });
    if (!ok) return;
    setBulkBusy(true);
    let ok_n = 0;
    const errors = [];
    for (const b of list) {
      try {
        await axios.post('/pms-core/no-show', { booking_id: b.id });
        ok_n += 1;
      } catch (e) {
        errors.push({ id: b.id, msg: e.response?.data?.detail?.message || e.response?.data?.detail || e.message });
      }
    }
    if (ok_n > 0) toast.success(`${ok_n} no-show işaretlendi`);
    if (errors.length > 0) {
      toast.error(`${errors.length} hata`, {
        description: errors.slice(0, 5).map((e) => `• ${(e.id || '').slice(0, 8)} — ${e.msg}`).join('\n'),
        duration: 8000,
      });
    }
    setBulkBusy(false);
    load();
  };

  return (
    <div className="p-4 md:p-6 space-y-5 max-w-6xl mx-auto">
      <PageHeader
        icon={UserX}
        title={t('cm.pages_NoShowToday.bekleyen_no_show_adaylari')}
        subtitle={t('cm.pages_NoShowToday.bugun_gelmesi_gereken_ama_henuz_check_in')}
        actions={
          <Button variant="outline" size="sm" onClick={load} disabled={loading}>
            <RefreshCw className={`w-4 h-4 mr-1.5 ${loading ? 'animate-spin' : ''}`} /> {t('cm.pages_NoShowToday.yenile')}
          </Button>
        }
      />

      <div className="grid grid-cols-1 sm:grid-cols-4 gap-3">
        <KpiCard icon={Calendar} label={t('cm.pages_NoShowToday.bekleyen_varis')} value={items.length} intent="info" />
        <KpiCard icon={AlertTriangle} label="Garantili Bekleyen" value={guaranteedCount} intent="warning" highlight={guaranteedCount > 0} />
        <KpiCard icon={Clock} label={t('cm.pages_NoShowToday.eta_60dk_gecen')} value={overdueCount} intent="danger" highlight={overdueCount > 0} />
        <KpiCard icon={UserX} label={t('cm.pages_NoShowToday.potansiyel_kayip')} value={fmtTRY(totalLoss)} intent="danger" />
      </div>

      {/* Filtre çubuğu */}
      <Card>
        <CardContent className="pt-4">
          <div className="flex flex-wrap items-end gap-3">
            <div>
              <Label className="text-xs text-slate-500">{t('cm.pages_NoShowToday.tarih')}</Label>
              <Input type="date" value={date} onChange={(e) => setDate(e.target.value)} className="h-9 w-40" />
            </div>
            <div className="flex-1 min-w-[200px]">
              <Label className="text-xs text-slate-500">{t('cm.pages_NoShowToday.ara')}</Label>
              <div className="relative">
                <Search className="absolute left-2 top-2.5 w-4 h-4 text-slate-400" />
                <Input value={search} onChange={(e) => setSearch(e.target.value)}
                  placeholder={t('cm.pages_NoShowToday.misafir_oda_kod')} className="pl-8 h-9" />
              </div>
            </div>
            <div>
              <Label className="text-xs text-slate-500">{t('cm.pages_NoShowToday.statu')}</Label>
              <select value={statusFilter} onChange={(e) => setStatusFilter(e.target.value)}
                className="h-9 border rounded-md px-2 text-sm bg-white w-40">
                <option value="all">{t('cm.pages_NoShowToday.tumu')}</option>
                <option value="guaranteed">Garantili</option>
                <option value="confirmed">{t('cm.pages_NoShowToday.onayli')}</option>
                <option value="pending">{t('cm.pages_NoShowToday.beklemede')}</option>
              </select>
            </div>
            <label className="inline-flex items-center gap-2 text-sm text-slate-700 h-9 cursor-pointer">
              <input type="checkbox" checked={otaOnly} onChange={(e) => setOtaOnly(e.target.checked)} className="w-4 h-4" />
              Sadece OTA
            </label>
            {selected.size > 0 && (
              <div className="flex items-center gap-2">
                <span className="text-xs text-slate-500">{selected.size} {t('cm.pages_NoShowToday.secili')}</span>
                <Button size="sm" variant="outline" onClick={() => setSelected(new Set())}>
                  <X className="w-3.5 h-3.5 mr-1" /> Temizle
                </Button>
                <Button size="sm" variant="destructive" onClick={bulkNoShow} disabled={bulkBusy}>
                  {bulkBusy && <Loader2 className="w-3.5 h-3.5 mr-1 animate-spin" />}
                  Toplu No-Show ({selected.size})
                </Button>
              </div>
            )}
          </div>
        </CardContent>
      </Card>

      {/* Liste */}
      <div className="space-y-3">
        {loading ? (
          <div className="text-center py-12">
            <Loader2 className="w-10 h-10 animate-spin text-sky-500 mx-auto" />
          </div>
        ) : visible.length === 0 ? (
          <Card>
            <CardContent className="pt-12 pb-12 text-center text-slate-500">
              <UserX className="w-12 h-12 mx-auto mb-3 text-slate-300" />
              {items.length === 0
                ? 'Bu tarih için bekleyen varış yok — tüm misafirler check-in yapmış görünüyor.'
                : 'Filtreyle eşleşen bekleyen varış yok.'}
            </CardContent>
          </Card>
        ) : (
          <>
            <div className="flex items-center gap-2 text-xs text-slate-500 px-1">
              <input type="checkbox" className="w-4 h-4"
                checked={selected.size === visible.length && visible.length > 0}
                onChange={toggleSelectAll} />
              <span>{t('cm.pages_NoShowToday.tumunu_sec')}{visible.length}{t('cm.pages_NoShowToday.eta_ya_gore_sirali')}</span>
            </div>
            {visible.map((b) => {
              const status = (b.status || '').toLowerCase();
              const guaranteed = status === 'guaranteed';
              const isSel = selected.has(b.id);
              const overdueMin = minutesPastETA(date, b.estimated_arrival_time);
              const isOverdue = overdueMin != null && overdueMin > 0;
              const isCritical = overdueMin != null && overdueMin > 60;
              const penalty = estimatedPenalty(b);
              const phone = b.guest_phone || b.phone;

              const borderClass = isCritical
                ? 'border-rose-500 bg-rose-50/40'
                : guaranteed
                  ? 'border-amber-500 bg-amber-50/40'
                  : isOverdue
                    ? 'border-amber-300'
                    : 'border-slate-300';

              return (
                <Card key={b.id} className={`border-l-4 ${borderClass} ${isSel ? 'ring-2 ring-sky-300' : ''}`}>
                  <CardContent className="pt-4">
                    <div className="flex items-start gap-3">
                      <input type="checkbox" checked={isSel} onChange={() => toggleSelect(b.id)}
                        className="w-4 h-4 mt-1.5" onClick={(e) => e.stopPropagation()} />
                      <div className="flex-1 cursor-pointer" onClick={() => setDetail(b)}>
                        <div className="flex items-center gap-2 mb-2 flex-wrap">
                          <h3 className="text-lg font-bold text-slate-800">{PRIMARY_LABEL(b)}</h3>
                          {b.guest_name && <span className="text-slate-700">— {b.guest_name}</span>}
                          <StatusBadge intent={STATUS_INTENT[status] || 'default'}>
                            {STATUS_TR[status] || status}
                          </StatusBadge>
                          {isCritical && (
                            <StatusBadge intent="danger" icon={Clock}>
                              ETA +{Math.floor(overdueMin / 60)}sa{overdueMin % 60}{t('cm.pages_NoShowToday.dk_gecti')}
                            </StatusBadge>
                          )}
                          {isOverdue && !isCritical && (
                            <StatusBadge intent="warning" icon={Clock}>
                              ETA +{overdueMin}dk
                            </StatusBadge>
                          )}
                          {b.source && b.source !== 'direct' && (
                            <StatusBadge intent="info">{b.source}</StatusBadge>
                          )}
                          {phone && (
                            <a href={`tel:${sanitizePhone(phone)}`} onClick={(e) => e.stopPropagation()}
                              className="inline-flex items-center gap-1 text-xs text-sky-700 hover:underline">
                              <Phone className="w-3 h-3" /> {phone}
                            </a>
                          )}
                        </div>
                        <div className="grid grid-cols-2 sm:grid-cols-5 gap-4 text-sm">
                          <div>
                            <p className="text-slate-500 text-xs">{t('cm.pages_NoShowToday.oda')}</p>
                            <p className="font-semibold">{b.room_number || '—'}</p>
                          </div>
                          <div>
                            <p className="text-slate-500 text-xs">ETA</p>
                            <p className={`font-semibold ${isCritical ? 'text-rose-700' : isOverdue ? 'text-amber-700' : ''}`}>
                              {b.estimated_arrival_time || '14:00'}
                            </p>
                          </div>
                          <div>
                            <p className="text-slate-500 text-xs">{t('cm.pages_NoShowToday.konuk')}</p>
                            <p className="font-semibold">{b.adults || 1}/{b.children || 0}</p>
                          </div>
                          <div>
                            <p className="text-slate-500 text-xs">{t('cm.pages_NoShowToday.tutar')}</p>
                            <p className="font-semibold">{fmtTRY(b.total_amount)}</p>
                          </div>
                          <div>
                            <p className="text-slate-500 text-xs">Ceza (tahmini)</p>
                            <p className={`font-semibold ${penalty > 0 ? 'text-rose-700' : 'text-slate-400'}`}>
                              {penalty > 0 ? fmtTRY(penalty) : '—'}
                            </p>
                          </div>
                        </div>
                      </div>
                      <div className="flex flex-col gap-2 items-end">
                        {phone && (
                          <div className="flex gap-1">
                            <a href={`tel:${sanitizePhone(phone)}`} className="inline-flex items-center px-2 h-8 rounded-md border text-xs hover:bg-sky-50">
                              <Phone className="w-3.5 h-3.5" />
                            </a>
                            <a href={`sms:${sanitizePhone(phone)}`} className="inline-flex items-center px-2 h-8 rounded-md border text-xs hover:bg-sky-50">
                              <MessageSquare className="w-3.5 h-3.5" />
                            </a>
                          </div>
                        )}
                        <Button size="sm" variant="destructive" disabled={busyId === b.id}
                          onClick={() => askNoShow(b)}>
                          <UserX className="w-4 h-4 mr-1" />
                          {busyId === b.id ? 'İşleniyor…' : 'No-Show'}
                        </Button>
                      </div>
                    </div>
                  </CardContent>
                </Card>
              );
            })}
          </>
        )}
      </div>

      {/* No-Show Confirmation Dialog (penalty preview ile) */}
      <Dialog open={!!confirmTarget} onOpenChange={(o) => !o && setConfirmTarget(null)}>
        <DialogContent>
          <DialogHeader>
            <DialogTitle className="flex items-center gap-2 text-rose-700">
              <UserX className="w-5 h-5" /> {t('cm.pages_NoShowToday.no_show_isaretle')}
            </DialogTitle>
            <DialogDescription>
              {t('cm.pages_NoShowToday.bu_islem_geri_alinamaz_oda_bosaltilir_st')} <strong>no_show</strong>{t('cm.pages_NoShowToday.a_cevrilir_audit_log_a_yazilir')}
            </DialogDescription>
          </DialogHeader>
          {confirmTarget && (
            <div className="space-y-3 py-2">
              <div className="bg-slate-50 p-3 rounded-md text-sm">
                <div className="flex justify-between"><span className="text-slate-500">{t('cm.pages_NoShowToday.misafir')}</span><strong>{confirmTarget.guest_name || '—'}</strong></div>
                <div className="flex justify-between"><span className="text-slate-500">{t('cm.pages_NoShowToday.oda_e4b47')}</span><strong>{confirmTarget.room_number || '—'}</strong></div>
                <div className="flex justify-between"><span className="text-slate-500">{t('cm.pages_NoShowToday.statu_ee6e2')}</span><strong>{STATUS_TR[(confirmTarget.status || '').toLowerCase()] || confirmTarget.status}</strong></div>
                <div className="flex justify-between"><span className="text-slate-500">ETA</span><strong>{confirmTarget.estimated_arrival_time || '14:00'}</strong></div>
                <div className="flex justify-between"><span className="text-slate-500">{t('cm.pages_NoShowToday.toplam_tutar')}</span><strong>{fmtTRY(confirmTarget.total_amount)}</strong></div>
              </div>
              {estimatedPenalty(confirmTarget) > 0 ? (
                <div className="bg-rose-50 border border-rose-200 p-3 rounded-md text-sm">
                  <strong className="text-rose-700">{t('cm.pages_NoShowToday.ceza_onizlemesi')}</strong>{' '}
                  {fmtTRY(estimatedPenalty(confirmTarget))} {t('cm.pages_NoShowToday.folio_ya_no_show_cezasi_olarak_post_edil')}
                  <p className="text-xs text-slate-600 mt-1">
                    Hesaplama: {confirmTarget.first_night_amount ? 'ilk gece tutarı' : confirmTarget.deposit_amount ? 'depozit tutarı' : 'toplam rezervasyon tutarı'}{t('cm.pages_NoShowToday.otelinizin_politikasina_gore_degisebilir')}
                  </p>
                </div>
              ) : (
                <div className="bg-slate-50 border border-slate-200 p-3 rounded-md text-xs text-slate-600">
                  {t('cm.pages_NoShowToday.ceza_yok_rezervasyon_garantili_degil_vey')}
                </div>
              )}
            </div>
          )}
          <DialogFooter>
            <Button variant="outline" onClick={() => setConfirmTarget(null)} disabled={!!busyId}>{t('cm.pages_NoShowToday.vazgec')}</Button>
            <Button variant="destructive" onClick={submitNoShow} disabled={!!busyId}>
              {busyId && <Loader2 className="w-4 h-4 mr-1 animate-spin" />} {t('cm.pages_NoShowToday.no_show_isaretle_57813')}
            </Button>
          </DialogFooter>
        </DialogContent>
      </Dialog>

      {/* Detail Dialog */}
      <Dialog open={!!detail} onOpenChange={(o) => !o && setDetail(null)}>
        <DialogContent className="max-w-2xl">
          <DialogHeader>
            <DialogTitle className="flex items-center gap-2">
              <FileText className="w-5 h-5" />
              {detail && PRIMARY_LABEL(detail)} {detail?.guest_name ? `· ${detail.guest_name}` : ''}
            </DialogTitle>
          </DialogHeader>
          {detail && (
            <div className="space-y-4">
              <div className="grid grid-cols-2 gap-3 text-sm">
                <div><span className="text-slate-500">{t('cm.pages_NoShowToday.statu_8db46')}</span> <strong>{STATUS_TR[(detail.status || '').toLowerCase()] || detail.status}</strong></div>
                <div><span className="text-slate-500">ETA:</span> <strong>{detail.estimated_arrival_time || '14:00'}</strong></div>
                <div><span className="text-slate-500">{t('cm.pages_NoShowToday.giris')}</span> <strong>{(detail.check_in || '').slice(0, 10)}</strong></div>
                <div><span className="text-slate-500">{t('cm.pages_NoShowToday.cikis')}</span> <strong>{(detail.check_out || '').slice(0, 10)}</strong></div>
                <div><span className="text-slate-500">{t('cm.pages_NoShowToday.konuk_e5c88')}</span> <strong>{detail.adults || 1}/{detail.children || 0}</strong></div>
                <div><span className="text-slate-500">{t('cm.pages_NoShowToday.tutar_64d2c')}</span> <strong>{fmtTRY(detail.total_amount)}</strong></div>
                {detail.source && <div><span className="text-slate-500">Kanal:</span> <strong>{detail.source}</strong></div>}
                {detail.deposit_amount > 0 && (
                  <div><span className="text-slate-500">Depozit:</span> <strong>{fmtTRY(detail.deposit_amount)}</strong></div>
                )}
                {(detail.guest_phone || detail.phone) && (
                  <div className="col-span-2 flex items-center gap-2">
                    <span className="text-slate-500">Telefon:</span>
                    <a href={`tel:${sanitizePhone(detail.guest_phone || detail.phone)}`} className="text-sky-700 hover:underline font-semibold">
                      {detail.guest_phone || detail.phone}
                    </a>
                    <a href={`sms:${sanitizePhone(detail.guest_phone || detail.phone)}`}
                      className="inline-flex items-center px-2 h-7 rounded-md border text-xs hover:bg-sky-50">
                      <MessageSquare className="w-3 h-3 mr-1" /> SMS
                    </a>
                  </div>
                )}
                {detail.notes && (
                  <div className="col-span-2 bg-slate-50 p-2 rounded text-xs text-slate-700">
                    <strong>Notlar:</strong> {detail.notes}
                  </div>
                )}
              </div>

              <div className="flex gap-2 pt-2 border-t">
                <Button size="sm" variant="destructive"
                  onClick={() => { setConfirmTarget(detail); setDetail(null); }}>
                  <UserX className="w-4 h-4 mr-1" /> {t('cm.pages_NoShowToday.no_show_isaretle_57813')}
                </Button>
              </div>
            </div>
          )}
        </DialogContent>
      </Dialog>
    </div>
  );
};

export default NoShowToday;
