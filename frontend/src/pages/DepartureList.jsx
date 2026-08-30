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
  LogOut, AlertCircle, Wallet, Clock, RefreshCw, Loader2, Search, ArrowUpDown,
  CreditCard, Phone, FileText, X,
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

// Şifreli/depolama biçimindeki PII hiçbir koşulda kullanıcı arayüzüne taşınmamalı.
export const displayableGuestPhone = (raw) => {
  const value = String(raw || '').trim();
  if (!value || /^SYR\d+:/i.test(value) || value.length > 32) return '';
  const sanitized = sanitizePhone(value);
  return sanitized.length >= 7 ? value : '';
};

const PRIMARY_LABEL = (b) =>
  b.room_number ? `Oda ${b.room_number}` : (b.confirmation_number || (b.id || '').substring(0, 8).toUpperCase());

export const normalizeDepartureResponse = (payload) => {
  const rows = payload?.departures || payload?.bookings || payload?.items || payload || [];
  return Array.isArray(rows) ? rows : [];
};

export const partitionDeparturesForBulkCheckout = (rows) => ({
  eligible: rows.filter((row) => Number(row.balance || 0) <= 0),
  blocked: rows.filter((row) => Number(row.balance || 0) > 0),
});

const DepartureList = () => {
  const { t } = useTranslation();
  const [date, setDate] = useState(() => localISODate(new Date()));
  const [departures, setDepartures] = useState([]);
  const [loading, setLoading] = useState(false);
  const [busyId, setBusyId] = useState(null);
  const [search, setSearch] = useState('');
  const [sortBy, setSortBy] = useState('balance_desc'); // balance_desc | room_asc | guest_asc
  const [onlyDebt, setOnlyDebt] = useState(false);
  const [selected, setSelected] = useState(new Set());
  const [bulkBusy, setBulkBusy] = useState(false);

  // Dialogs
  const [payTarget, setPayTarget] = useState(null);
  const [payAmount, setPayAmount] = useState('');
  const [payMethod, setPayMethod] = useState('cash');
  const [payRef, setPayRef] = useState('');
  const [paySubmitting, setPaySubmitting] = useState(false);

  const [lateTarget, setLateTarget] = useState(null);
  const [lateTime, setLateTime] = useState('14:00');
  const [lateCharge, setLateCharge] = useState('');
  const [lateSubmitting, setLateSubmitting] = useState(false);

  const [detail, setDetail] = useState(null);
  const [detailFolio, setDetailFolio] = useState(null);
  const [detailLoading, setDetailLoading] = useState(false);

  const load = useCallback(async () => {
    setLoading(true);
    setSelected(new Set());
    try {
      const res = await axios.get(`/frontdesk/departures?date=${encodeURIComponent(date)}`);
      setDepartures(normalizeDepartureResponse(res.data));
    } catch (e) {
      toast.error('Çıkış listesi yüklenemedi');
      setDepartures([]);
    } finally {
      setLoading(false);
    }
  }, [date]);

  useEffect(() => { load(); }, [load]);

  useEffect(() => {
    let active = true;
    axios.get('/night-audit/business-date')
      .then(({ data }) => {
        if (active && data?.business_date) setDate(data.business_date);
      })
      .catch(() => {});
    return () => { active = false; };
  }, []);

  // ── Filter + sort
  const visible = useMemo(() => {
    const q = search.trim().toLowerCase();
    let arr = departures.filter((b) => {
      if (onlyDebt && (b.balance || 0) <= 0) return false;
      if (!q) return true;
      return String(b.room_number || '').includes(search)
        || (b.guest_name || '').toLowerCase().includes(q)
        || (b.confirmation_number || '').toLowerCase().includes(q);
    });
    arr = [...arr];
    if (sortBy === 'balance_desc') arr.sort((a, b) => (b.balance || 0) - (a.balance || 0));
    else if (sortBy === 'room_asc') arr.sort((a, b) => String(a.room_number || '').localeCompare(String(b.room_number || ''), 'tr', { numeric: true }));
    else if (sortBy === 'guest_asc') arr.sort((a, b) => (a.guest_name || '').localeCompare(b.guest_name || '', 'tr'));
    return arr;
  }, [departures, search, sortBy, onlyDebt]);

  const totalBalance = departures.reduce((s, b) => s + (b.balance || 0), 0);
  const withDebt = departures.filter((b) => (b.balance || 0) > 0).length;

  // ── Checkout (single)
  const checkout = async (booking, force = false) => {
    if (busyId) return;
    if (!force && (booking.balance || 0) > 0) {
      toast.error('Normal çıkış için önce folio bakiyesini kapatın.');
      openPay(booking);
      return;
    }

    const ok = await confirmDialog({
      message: force
        ? `${PRIMARY_LABEL(booking)} için ${fmtTRY(booking.balance)} açık bakiye varken zorla çıkış yapılacak. Bu işlem yalnızca yetkili istisna durumlarında kullanılmalıdır. Devam edilsin mi?`
        : `${booking.guest_name || PRIMARY_LABEL(booking)} için çıkış yapılsın mı?`,
      variant: force ? 'danger' : 'default',
    });
    if (!ok) return;

    setBusyId(booking.id);
    try {
      await axios.post('/pms-core/checkout', { booking_id: booking.id, force });
      toast.success('Çıkış tamamlandı');
      load();
    } catch (e) {
      const detail = e.response?.data?.detail;
      const msg = typeof detail === 'string' ? detail : (detail?.message || detail?.error || 'Çıkış başarısız');
      toast.error(msg);
    } finally {
      setBusyId(null);
    }
  };

  // ── Bulk checkout
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

  const bulkCheckout = async () => {
    if (selected.size === 0) return;
    const list = visible.filter((b) => selected.has(b.id));
    const { eligible, blocked } = partitionDeparturesForBulkCheckout(list);
    const debtCount = blocked.length;
    if (eligible.length === 0) {
      toast.error('Seçili rezervasyonların bakiyesi kapanmadan toplu çıkış yapılamaz.');
      return;
    }
    const ok = await confirmDialog({
      message: `${eligible.length} bakiyesiz rezervasyon için toplu çıkış yapılsın mı?`
        + (debtCount > 0 ? `\nBakiyesi bulunan ${debtCount} rezervasyon güvenlik nedeniyle atlanacak.` : ''),
      variant: 'default',
    });
    if (!ok) return;
    setBulkBusy(true);
    let ok_n = 0;
    const errors = [];
    for (const b of eligible) {
      try {
        await axios.post('/pms-core/checkout', { booking_id: b.id, force: false });
        ok_n += 1;
      } catch (e) {
        errors.push({ id: b.id, msg: e.response?.data?.detail?.message || e.response?.data?.detail || e.message });
      }
    }
    if (ok_n > 0) toast.success(`${ok_n} çıkış tamamlandı`);
    if (errors.length > 0) {
      toast.error(`${errors.length} hata`, {
        description: errors.slice(0, 5).map((e) => `• ${(e.id || '').slice(0, 8)} — ${e.msg}`).join('\n'),
        duration: 8000,
      });
    }
    setBulkBusy(false);
    load();
  };

  // ── Quick payment
  const openPay = (b) => {
    setPayTarget(b);
    setPayAmount(String(b.balance || 0));
    setPayMethod('cash');
    setPayRef('');
  };
  const submitPay = async () => {
    if (!payTarget) return;
    const n = Number(payAmount);
    if (!(n > 0)) { toast.error('Tutar 0\'dan büyük olmalı'); return; }
    setPaySubmitting(true);
    try {
      await axios.post(`/frontdesk/folio/${payTarget.id}/payment`, {
        amount: n,
        method: payMethod,
        payment_type: 'final',
        reference: payRef.trim() || null,
        notes: 'Çıkış tahsilatı (DepartureList)',
      });
      const remaining = (payTarget.balance || 0) - n;
      toast.success(`Tahsilat alındı: ${fmtTRY(n)}`);
      setPayTarget(null);
      // Bakiye sıfırlanır sıfırlanmaz otomatik çıkış öner
      if (remaining <= 0.001) {
        const auto = await confirmDialog({
          message: 'Bakiye kapandı. Çıkış işlemi şimdi yapılsın mı?',
          variant: 'default',
        });
        if (auto) await checkout({ ...payTarget, balance: 0 }, false);
        else load();
      } else {
        toast(`Kalan bakiye: ${fmtTRY(remaining)}`);
        load();
      }
    } catch (e) {
      const detail = e.response?.data?.detail;
      toast.error(typeof detail === 'string' ? detail : (detail?.message || 'Tahsilat başarısız'));
    } finally {
      setPaySubmitting(false);
    }
  };

  // ── Late checkout
  const openLate = (b) => {
    setLateTarget(b);
    setLateTime('14:00');
    setLateCharge('');
  };
  const submitLate = async () => {
    if (!lateTarget) return;
    const charge = Number(lateCharge) || 0;
    if (charge < 0) { toast.error('Ücret negatif olamaz'); return; }
    setLateSubmitting(true);
    try {
      await axios.post(`/pms/reservations/${lateTarget.id}/late-checkout`, {
        checkout_time: lateTime || null,
        extra_charge: charge,
      });
      toast.success(`Geç çıkış kaydedildi (${lateTime}${charge > 0 ? `, +${fmtTRY(charge)}` : ''})`);
      setLateTarget(null);
      load();
    } catch (e) {
      const detail = e.response?.data?.detail;
      toast.error(typeof detail === 'string' ? detail : (detail?.message || 'Geç çıkış başarısız'));
    } finally {
      setLateSubmitting(false);
    }
  };

  // ── Detail dialog (lightweight + folio summary)
  const openDetail = async (b) => {
    setDetail(b);
    setDetailFolio(null);
    setDetailLoading(true);
    try {
      const res = await axios.get(`/frontdesk/folio/${b.id}`).catch(() => null);
      if (res?.data) setDetailFolio(res.data);
    } finally {
      setDetailLoading(false);
    }
  };

  return (
    <div className="p-4 md:p-6 space-y-5 max-w-7xl mx-auto">
      <PageHeader
        icon={LogOut}
        title="Çıkış Operasyonları"
        subtitle="PMS iş günündeki çıkışları, açık folyo bakiyelerini, tahsilat ve geç çıkış işlemlerini tek yerden yönetin."
        actions={
          <Button variant="outline" size="sm" onClick={load} disabled={loading}>
            <RefreshCw className={`w-4 h-4 mr-1.5 ${loading ? 'animate-spin' : ''}`} /> {t('cm.pages_DepartureList.yenile')}
          </Button>
        }
      />

      <div className="grid grid-cols-1 sm:grid-cols-3 gap-3">
        <KpiCard icon={LogOut} label="Planlanan çıkış" value={departures.length} intent="info" />
        <KpiCard icon={AlertCircle} label="Tahsilat bekleyen" value={withDebt} intent="warning" highlight={withDebt > 0} />
        <KpiCard icon={Wallet} label="Açık folyo toplamı" value={fmtTRY(totalBalance)} intent={totalBalance > 0 ? 'warning' : 'success'} highlight={totalBalance > 0} />
      </div>

      {/* Filtre çubuğu */}
      <Card>
        <CardContent className="pt-4">
          <div className="flex flex-wrap items-end gap-3">
            <div>
              <Label className="text-xs text-slate-500">{t('cm.pages_DepartureList.tarih')}</Label>
              <Input type="date" value={date} onChange={(e) => setDate(e.target.value)} className="h-9 w-40" />
            </div>
            <div className="flex-1 min-w-[200px]">
              <Label className="text-xs text-slate-500">{t('cm.pages_DepartureList.ara')}</Label>
              <div className="relative">
                <Search className="absolute left-2 top-2.5 w-4 h-4 text-slate-400" />
                <Input value={search} onChange={(e) => setSearch(e.target.value)}
                  placeholder={t('cm.pages_DepartureList.misafir_oda_no_rezervasyon_kodu')} className="pl-8 h-9" />
              </div>
            </div>
            <div>
              <Label className="text-xs text-slate-500">{t('cm.pages_DepartureList.sirala')}</Label>
              <select value={sortBy} onChange={(e) => setSortBy(e.target.value)}
                className="h-9 border rounded-md px-2 text-sm bg-white w-44">
                <option value="balance_desc">{t('cm.pages_DepartureList.bakiye_yuksek_dusuk')}</option>
                <option value="room_asc">{t('cm.pages_DepartureList.oda_no_artan')}</option>
                <option value="guest_asc">{t('cm.pages_DepartureList.misafir_a_z')}</option>
              </select>
            </div>
            <label className="inline-flex items-center gap-2 text-sm text-slate-700 h-9 cursor-pointer">
              <input type="checkbox" checked={onlyDebt} onChange={(e) => setOnlyDebt(e.target.checked)} className="w-4 h-4" />
              Sadece bakiyeli
            </label>
            {selected.size > 0 && (
              <div className="flex items-center gap-2">
                <span className="text-xs text-slate-500">{selected.size} {t('cm.pages_DepartureList.secili')}</span>
                <Button size="sm" variant="outline" onClick={() => setSelected(new Set())}>
                  <X className="w-3.5 h-3.5 mr-1" /> Temizle
                </Button>
                <Button size="sm" onClick={bulkCheckout} disabled={bulkBusy}>
                  {bulkBusy && <Loader2 className="w-3.5 h-3.5 mr-1 animate-spin" />}
                  Toplu çıkış ({selected.size})
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
              <LogOut className="w-12 h-12 mx-auto mb-3 text-slate-300" />
              {departures.length === 0 ? 'Bu tarih için çıkış yok.' : 'Filtreyle eşleşen çıkış yok.'}
            </CardContent>
          </Card>
        ) : (
          <>
            <div className="flex items-center gap-2 text-xs text-slate-500 px-1">
              <input type="checkbox" className="w-4 h-4"
                checked={selected.size === visible.length && visible.length > 0}
                onChange={toggleSelectAll}
              />
              <span>Tümünü seç ({visible.length})</span>
              <ArrowUpDown className="w-3 h-3 ml-2" />
              <span>{sortBy === 'balance_desc' ? 'Bakiyeye göre' : sortBy === 'room_asc' ? 'Oda no' : 'Misafir'}</span>
            </div>
            {visible.map((b) => {
              const debt = (b.balance || 0) > 0;
              const isSel = selected.has(b.id);
              const guestPhone = displayableGuestPhone(b.guest_phone);
              return (
                <Card key={b.id}
                  className={`border-l-4 ${debt ? 'border-amber-500 bg-amber-50/40' : 'border-sky-500'} ${isSel ? 'ring-2 ring-sky-300' : ''}`}>
                  <CardContent className="pt-4">
                    <div className="grid gap-4 lg:grid-cols-[minmax(0,1fr)_auto]">
                      <div className="flex min-w-0 items-start gap-3">
                        <input type="checkbox" checked={isSel} onChange={() => toggleSelect(b.id)}
                          className="w-4 h-4 mt-1.5" onClick={(e) => e.stopPropagation()} />
                        <div className="min-w-0 flex-1 cursor-pointer" onClick={() => openDetail(b)}>
                          <div className="flex items-center gap-2 mb-2 flex-wrap">
                          <h3 className="text-lg font-bold text-slate-800">{PRIMARY_LABEL(b)}</h3>
                          {b.guest_name && <span className="text-slate-700">— {b.guest_name}</span>}
                          {debt && <StatusBadge intent="warning">Bakiyeli</StatusBadge>}
                          {b.late_checkout && (
                            <StatusBadge intent="warning" icon={Clock}>{t('cm.pages_DepartureList.gec_cikis')}</StatusBadge>
                          )}
                          {guestPhone && (
                            <a href={`tel:${sanitizePhone(guestPhone)}`} onClick={(e) => e.stopPropagation()}
                              className="inline-flex max-w-full items-center gap-1 text-xs text-sky-700 hover:underline">
                              <Phone className="w-3 h-3 shrink-0" /> <span className="truncate">{guestPhone}</span>
                            </a>
                          )}
                          </div>
                          <div className="grid grid-cols-2 sm:grid-cols-4 gap-4 text-sm">
                          <div>
                            <p className="text-slate-500 text-xs">{t('cm.pages_DepartureList.oda')}</p>
                            <p className="font-semibold">{b.room_number || '—'}</p>
                          </div>
                          <div>
                            <p className="text-slate-500 text-xs">{t('cm.pages_DepartureList.cikis_saati')}</p>
                            <p className="font-semibold">{b.check_out_time || '12:00'}</p>
                          </div>
                          <div>
                            <p className="text-slate-500 text-xs">{t('cm.pages_DepartureList.toplam')}</p>
                            <p className="font-semibold">{fmtTRY(b.total_amount)}</p>
                          </div>
                          <div>
                            <p className="text-slate-500 text-xs">Folyo bakiyesi</p>
                            <p className={`font-semibold ${debt ? 'text-amber-700' : 'text-emerald-700'}`}>
                              {fmtTRY(b.balance || 0)}
                            </p>
                          </div>
                          </div>
                        </div>
                      </div>
                      <div className="flex flex-wrap gap-2 lg:w-36 lg:flex-col lg:items-stretch">
                        {debt && (
                          <Button size="sm" className="justify-center" onClick={() => openPay(b)} disabled={busyId === b.id}>
                            <CreditCard className="w-4 h-4 mr-1" /> Tahsil Et
                          </Button>
                        )}
                        <Button size="sm" variant="outline" className="justify-center" disabled={busyId === b.id || debt}
                          onClick={() => checkout(b, false)}>
                          <LogOut className="w-4 h-4 mr-1" />
                          {busyId === b.id ? 'İşleniyor…' : 'Çıkış Yap'}
                        </Button>
                        <Button size="sm" variant="outline" className="justify-center" onClick={() => openLate(b)} disabled={busyId === b.id}>
                          <Clock className="w-4 h-4 mr-1" /> {t('cm.pages_DepartureList.gec_cikis_9e19e')}
                        </Button>
                        {debt && (
                          <Button size="sm" variant="ghost" className="justify-center text-rose-600 hover:text-rose-700"
                            onClick={() => checkout(b, true)} disabled={busyId === b.id}>
                            {t('cm.pages_DepartureList.zorla_cikis')}
                          </Button>
                        )}
                      </div>
                    </div>
                  </CardContent>
                </Card>
              );
            })}
          </>
        )}
      </div>

      {/* Quick Payment Dialog */}
      <Dialog open={!!payTarget} onOpenChange={(o) => !o && setPayTarget(null)}>
        <DialogContent>
          <DialogHeader>
            <DialogTitle>Tahsilat — {payTarget && PRIMARY_LABEL(payTarget)}</DialogTitle>
            <DialogDescription>
              {t('cm.pages_DepartureList.acik_bakiye')} <strong>{fmtTRY(payTarget?.balance || 0)}</strong>
            </DialogDescription>
          </DialogHeader>
          <div className="space-y-3 py-2">
            <div>
              <Label>{t('cm.pages_DepartureList.tutar_tl')}</Label>
              <Input type="number" min="0" step="0.01" value={payAmount}
                onChange={(e) => setPayAmount(e.target.value)} />
            </div>
            <div>
              <Label>{t('cm.pages_DepartureList.yontem')}</Label>
              <div className="grid grid-cols-3 gap-2 mt-1">
                {[
                  { v: 'cash', l: 'Nakit', i: 'success' },
                  { v: 'card', l: 'Kart', i: 'info' },
                  { v: 'bank_transfer', l: 'Havale', i: 'neutral' },
                ].map((m) => (
                  <button key={m.v} type="button" onClick={() => setPayMethod(m.v)}
                    className={`h-10 rounded-md border text-sm font-medium transition ${payMethod === m.v ? 'border-slate-800 bg-slate-900 text-white' : 'border-slate-200 hover:border-slate-400 bg-white'}`}>
                    {m.l}
                  </button>
                ))}
              </div>
            </div>
            <div>
              <Label>Referans (opsiyonel)</Label>
              <Input value={payRef} onChange={(e) => setPayRef(e.target.value)}
                placeholder={t('cm.pages_DepartureList.fis_no_banka_referansi')} />
            </div>
          </div>
          <DialogFooter>
            <Button variant="outline" onClick={() => setPayTarget(null)} disabled={paySubmitting}>{t('cm.pages_DepartureList.vazgec')}</Button>
            <Button onClick={submitPay} disabled={paySubmitting}>
              {paySubmitting && <Loader2 className="w-4 h-4 mr-1 animate-spin" />} Tahsil Et
            </Button>
          </DialogFooter>
        </DialogContent>
      </Dialog>

      {/* Late Checkout Dialog */}
      <Dialog open={!!lateTarget} onOpenChange={(o) => !o && setLateTarget(null)}>
        <DialogContent>
          <DialogHeader>
            <DialogTitle>{t('cm.pages_DepartureList.gec_cikis_505a3')} {lateTarget && PRIMARY_LABEL(lateTarget)}</DialogTitle>
            <DialogDescription>
              {t('cm.pages_DepartureList.misafire_ek_cikis_saati_ve_opsiyonel_ek_')} {lateTarget?.check_out_time || '12:00'}.
            </DialogDescription>
          </DialogHeader>
          <div className="space-y-3 py-2">
            <div>
              <Label>{t('cm.pages_DepartureList.yeni_cikis_saati')}</Label>
              <Input type="time" value={lateTime} onChange={(e) => setLateTime(e.target.value)} />
              <div className="flex gap-1 mt-2">
                {['13:00', '14:00', '16:00', '18:00'].map((h) => (
                  <Button key={h} type="button" size="sm" variant="outline" className="h-7 text-xs"
                    onClick={() => setLateTime(h)}>{h}</Button>
                ))}
              </div>
            </div>
            <div>
              <Label>{t('cm.pages_DepartureList.ek_ucret_tl')}</Label>
              <Input type="number" min="0" step="0.01" value={lateCharge}
                onChange={(e) => setLateCharge(e.target.value)} placeholder={t('cm.pages_DepartureList.0_ucretsiz')} />
              <p className="text-xs text-slate-500 mt-1">
                {t('cm.pages_DepartureList.girilen_tutar_folio_ya_gec_cikis_ucreti_')}
              </p>
            </div>
          </div>
          <DialogFooter>
            <Button variant="outline" onClick={() => setLateTarget(null)} disabled={lateSubmitting}>{t('cm.pages_DepartureList.vazgec_bf814')}</Button>
            <Button onClick={submitLate} disabled={lateSubmitting}>
              {lateSubmitting && <Loader2 className="w-4 h-4 mr-1 animate-spin" />} {t('cm.pages_DepartureList.kaydet')}
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
                <div><span className="text-slate-500">{t('cm.pages_DepartureList.giris')}</span> <strong>{(detail.check_in || '').slice(0, 10)}</strong></div>
                <div><span className="text-slate-500">{t('cm.pages_DepartureList.cikis')}</span> <strong>{(detail.check_out || '').slice(0, 10)} {detail.check_out_time || '12:00'}</strong></div>
                <div><span className="text-slate-500">{t('cm.pages_DepartureList.yetiskin_cocuk')}</span> <strong>{detail.adults || 1}/{detail.children || 0}</strong></div>
                <div><span className="text-slate-500">{t('cm.pages_DepartureList.toplam_68af4')}</span> <strong>{fmtTRY(detail.total_amount)}</strong></div>
                <div><span className="text-slate-500">{t('cm.pages_DepartureList.odenen')}</span> <strong>{fmtTRY(detail.paid_amount)}</strong></div>
                <div>
                  <span className="text-slate-500">{t('cm.pages_DepartureList.bakiye')}</span>{' '}
                  <strong className={(detail.balance || 0) > 0 ? 'text-amber-700' : 'text-emerald-700'}>
                    {fmtTRY(detail.balance || 0)}
                  </strong>
                </div>
                {displayableGuestPhone(detail.guest_phone) && (
                  <div className="col-span-2">
                    <span className="text-slate-500">Telefon:</span>{' '}
                    <a href={`tel:${sanitizePhone(displayableGuestPhone(detail.guest_phone))}`} className="text-sky-700 hover:underline font-semibold">
                      {displayableGuestPhone(detail.guest_phone)}
                    </a>
                  </div>
                )}
                {detail.notes && (
                  <div className="col-span-2 bg-slate-50 p-2 rounded text-xs text-slate-700">
                    <strong>Notlar:</strong> {detail.notes}
                  </div>
                )}
              </div>

              <div className="border-t pt-3">
                <div className="text-xs text-slate-500 mb-2">Folyo özeti</div>
                {detailLoading ? (
                  <div className="flex items-center gap-2 text-sm text-slate-500">
                    <Loader2 className="w-4 h-4 animate-spin" /> {t('cm.pages_DepartureList.folio_yukleniyor')}
                  </div>
                ) : detailFolio ? (
                  <div className="text-sm space-y-1">
                    <div className="flex justify-between"><span>Toplam harcama</span><strong>{fmtTRY(detailFolio.charges_total ?? detailFolio.total_charges)}</strong></div>
                    <div className="flex justify-between"><span>{t('cm.pages_DepartureList.toplam_odeme')}</span><strong>{fmtTRY(detailFolio.payments_total ?? detailFolio.total_payments)}</strong></div>
                    <div className="flex justify-between border-t pt-1 mt-1">
                      <span>{t('cm.pages_DepartureList.bakiye_33769')}</span>
                      <strong className={(detailFolio.balance || 0) > 0 ? 'text-amber-700' : 'text-emerald-700'}>
                        {fmtTRY(detailFolio.balance || 0)}
                      </strong>
                    </div>
                  </div>
                ) : (
                  <div className="text-xs text-slate-400">{t('cm.pages_DepartureList.folio_bilgisi_alinamadi')}</div>
                )}
              </div>

              <div className="flex flex-wrap gap-2 pt-2 border-t">
                {(detail.balance || 0) > 0 && (
                  <Button size="sm" onClick={() => { openPay(detail); setDetail(null); }}>
                    <CreditCard className="w-4 h-4 mr-1" /> Tahsil Et
                  </Button>
                )}
                <Button size="sm" variant="outline" onClick={() => { openLate(detail); setDetail(null); }}>
                  <Clock className="w-4 h-4 mr-1" /> {t('cm.pages_DepartureList.gec_cikis_9e19e')}
                </Button>
                <Button size="sm" variant="outline" onClick={() => { checkout(detail, false); setDetail(null); }}>
                  <LogOut className="w-4 h-4 mr-1" /> {t('cm.pages_DepartureList.cikis_yap')}
                </Button>
              </div>
            </div>
          )}
        </DialogContent>
      </Dialog>
    </div>
  );
};

export default DepartureList;
