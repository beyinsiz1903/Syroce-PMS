import { useState, useEffect, useCallback } from 'react';
import axios from 'axios';
import { toast } from 'sonner';
import { useTranslation } from 'react-i18next';
import { Link } from 'react-router-dom';

import { Card, CardContent, CardHeader, CardTitle, CardDescription } from '@/components/ui/card';
import { Button } from '@/components/ui/button';
import { Badge } from '@/components/ui/badge';
import { Tabs, TabsContent, TabsList, TabsTrigger } from '@/components/ui/tabs';
import { Dialog, DialogContent, DialogHeader, DialogTitle, DialogFooter } from '@/components/ui/dialog';
import { Input } from '@/components/ui/input';
import { Label } from '@/components/ui/label';
import { Textarea } from '@/components/ui/textarea';
import {
  Handshake, Clock, CheckCircle2, XCircle, Ban, RefreshCw, Building2,
  Percent, Calendar, CreditCard, Globe, FileText, AlertTriangle, Loader2,
  Info, ArrowRight,
} from 'lucide-react';

const STATUS_META = {
  pending:    { color: 'border-amber-200 bg-amber-50 text-amber-700 dark:border-amber-800 dark:bg-amber-950/40 dark:text-amber-300', icon: Clock, label: 'Bekliyor' },
  approved:   { color: 'border-emerald-200 bg-emerald-50 text-emerald-700 dark:border-emerald-800 dark:bg-emerald-950/40 dark:text-emerald-300', icon: CheckCircle2, label: 'Onaylı' },
  rejected:   { color: 'border-red-200 bg-red-50 text-red-700 dark:border-red-800 dark:bg-red-950/40 dark:text-red-300', icon: XCircle, label: 'Reddedildi' },
  terminated: { color: 'border-slate-200 bg-slate-100 text-slate-700 dark:border-slate-700 dark:bg-slate-800 dark:text-slate-300', icon: Ban, label: 'Feshedildi' },
  expired:    { color: 'border-slate-200 bg-slate-100 text-slate-600 dark:border-slate-700 dark:bg-slate-800 dark:text-slate-300', icon: Clock, label: 'Süresi Doldu' },
  withdrawn:  { color: 'border-slate-200 bg-slate-100 text-slate-600 dark:border-slate-700 dark:bg-slate-800 dark:text-slate-300', icon: Ban, label: 'Geri Çekildi' },
};

const PAYMENT_LABEL = {
  prepaid: 'Ön Ödeme',
  on_arrival: 'Geliş Anında',
  net_7: 'Net 7 Gün',
  net_15: 'Net 15 Gün',
  net_30: 'Net 30 Gün',
};

const StatusBadge = ({ status }) => {
  const meta = STATUS_META[status] || STATUS_META.pending;
  const Icon = meta.icon;
  return (
    <Badge className={`${meta.color} border gap-1`}>
      <Icon className="w-3 h-3" /> {meta.label}
    </Badge>
  );
};

const ContractCard = ({ contract, onApprove, onReject, onTerminate }) => {
  const cp = contract.cancellation_policy || {};
  const isPending = contract.status === 'pending';
  const isApproved = contract.status === 'approved';

  return (
    <Card className="border-border bg-card shadow-sm transition hover:border-slate-300 hover:shadow-md dark:hover:border-slate-700">
      <CardHeader className="pb-3">
        <div className="flex items-start justify-between gap-3">
          <div className="min-w-0">
            <CardTitle className="text-base flex items-center gap-2">
              <Building2 className="w-4 h-4 text-blue-600 dark:text-blue-400 shrink-0" />
              <span className="truncate">{contract.agency_name || 'Acente'}</span>
              <span className="text-xs font-mono text-muted-foreground">{contract.contract_code}</span>
            </CardTitle>
            <CardDescription className="text-xs mt-1">
              {contract.agency_country && <span>{contract.agency_country} • </span>}
              {contract.agency_email}
            </CardDescription>
          </div>
          <StatusBadge status={contract.status} />
        </div>
      </CardHeader>
      <CardContent className="space-y-3">
        <div className="grid grid-cols-2 gap-3 text-sm">
          <div className="flex items-center gap-2">
            <Percent className="w-4 h-4 text-amber-400" />
            <div>
              <div className="text-muted-foreground text-xs">Komisyon</div>
              <div className="font-semibold">%{contract.commission_pct?.toFixed(1)}</div>
              {contract.agency_proposed_commission_pct !== contract.commission_pct && isApproved && (
                <div className="text-[10px] text-muted-foreground">
                  Teklif: %{contract.agency_proposed_commission_pct?.toFixed(1)}
                </div>
              )}
            </div>
          </div>
          <div className="flex items-center gap-2">
            <CreditCard className="w-4 h-4 text-violet-400" />
            <div>
              <div className="text-muted-foreground text-xs">Ödeme</div>
              <div className="font-semibold">{PAYMENT_LABEL[contract.payment_terms] || contract.payment_terms}</div>
            </div>
          </div>
          <div className="flex items-center gap-2">
            <Calendar className="w-4 h-4 text-blue-600 dark:text-blue-400" />
            <div>
              <div className="text-muted-foreground text-xs">Geçerlilik</div>
              <div className="font-semibold text-xs">{contract.valid_from} → {contract.valid_to}</div>
            </div>
          </div>
          <div className="flex items-center gap-2">
            <Globe className="w-4 h-4 text-emerald-400" />
            <div>
              <div className="text-muted-foreground text-xs">Para Birimi</div>
              <div className="font-semibold">{contract.currency}</div>
            </div>
          </div>
        </div>

        <div className="rounded-lg border border-slate-200 bg-slate-50 p-3 text-xs space-y-1 dark:border-slate-800 dark:bg-slate-950/50">
          <div className="font-semibold text-slate-800 flex items-center gap-1 dark:text-slate-200">
            <AlertTriangle className="w-3 h-3" /> İptal Politikası
          </div>
          <div className="text-muted-foreground">
            {cp.free_until_days_before ?? 7} gün öncesine kadar ücretsiz —
            sonrasında %{cp.penalty_pct ?? 50} ceza —
            no-show: %{cp.no_show_penalty_pct ?? 100}
          </div>
        </div>

        {contract.allowed_room_types?.length > 0 && (
          <div className="text-xs">
            <span className="text-muted-foreground">İzinli Oda Tipleri: </span>
            {contract.allowed_room_types.map(rt => (
              <Badge key={rt} variant="secondary" className="ml-1">{rt}</Badge>
            ))}
          </div>
        )}

        {contract.special_terms && (
          <div className="text-xs bg-slate-50 border border-slate-200 rounded-lg p-2 dark:border-slate-800 dark:bg-slate-950/40">
            <div className="text-muted-foreground mb-1 flex items-center gap-1">
              <FileText className="w-3 h-3" /> Özel Şartlar
            </div>
            <div className="whitespace-pre-wrap text-slate-700 dark:text-slate-300">{contract.special_terms}</div>
          </div>
        )}

        {contract.decision_notes && !isPending && (
          <div className="text-xs text-muted-foreground italic">
            Karar Notu: {contract.decision_notes}
            {contract.decided_by && <span className="block">— {contract.decided_by}</span>}
          </div>
        )}

        {(isPending || isApproved) && (
          <div className="flex gap-2 pt-1">
            {isPending && (
              <>
                <Button data-testid="approve-btn" size="sm" className="flex-1 bg-emerald-600 hover:bg-emerald-500"
                        onClick={() => onApprove(contract)}>
                  <CheckCircle2 className="w-4 h-4 mr-1" /> Onayla
                </Button>
                <Button data-testid="reject-btn" size="sm" variant="destructive" className="flex-1"
                        onClick={() => onReject(contract)}>
                  <XCircle className="w-4 h-4 mr-1" /> Reddet
                </Button>
              </>
            )}
            {isApproved && (
              <Button data-testid="terminate-btn" size="sm" variant="outline"
                      className="ml-auto border-red-200 text-red-700 hover:bg-red-50 dark:border-red-800 dark:text-red-300 dark:hover:bg-red-950/40"
                      onClick={() => onTerminate(contract)}>
                <Ban className="w-4 h-4 mr-1" /> Feshet
              </Button>
            )}
          </div>
        )}
      </CardContent>
    </Card>
  );
};

const IncomingAgencyContracts = ({ user, tenant, onLogout }) => {
  const { t: _t, i18n } = useTranslation();
  const [tab, setTab] = useState('pending');
  const [loading, setLoading] = useState(false);
  const [loadError, setLoadError] = useState('');
  const [contracts, setContracts] = useState([]);
  const [counts, setCounts] = useState({ pending: 0, approved: 0, rejected: 0, terminated: 0, expired: 0, withdrawn: 0 });

  const [approveDlg, setApproveDlg] = useState(null);
  const [rejectDlg, setRejectDlg] = useState(null);
  const [terminateDlg, setTerminateDlg] = useState(null);
  const [commissionOverride, setCommissionOverride] = useState('');
  const [approveNotes, setApproveNotes] = useState('');
  const [rejectReason, setRejectReason] = useState('');
  const [terminateReason, setTerminateReason] = useState('');
  const [acting, setActing] = useState(false);

  const [historyFilter, setHistoryFilter] = useState('all'); // all|rejected|terminated|expired|withdrawn

  const tabToStatus = {
    pending: 'pending',
    active: 'approved',
    history: 'history', // backend $in alias
  };

  const fetchContracts = useCallback(async ({ silent = false, signal } = {}) => {
    setLoading(true);
    // History sekmesinde alt-filtre secilirse o spesifik status'u sor; aksi halde 'history' alias.
    let status = tabToStatus[tab];
    if (tab === 'history' && historyFilter !== 'all') status = historyFilter;
    const params = status ? { status } : {};
    // 4xx hariç (auth/yetki) tek retry: backend restart / 502/503 / network için.
    const tryOnce = () => axios.get('/marketplace/incoming-requests', { params, signal }).then(r => r.data);
    try {
      setLoadError('');
      let data;
      try {
        data = await tryOnce();
      } catch (firstErr) {
        if (axios.isCancel?.(firstErr) || firstErr?.name === 'CanceledError') return;
        const st = firstErr?.response?.status;
        if (st && st >= 400 && st < 500) throw firstErr;
        await new Promise(r => setTimeout(r, 1500));
        data = await tryOnce();
      }
      // Backend artik dogru filtrelenmis listeyi donuyor — client-side filter YOK.
      setContracts(data.contracts || []);
      setCounts(data.counts || {});
    } catch (e) {
      if (axios.isCancel?.(e) || e?.name === 'CanceledError') return;
      console.error('[IncomingAgencyContracts] fetch failed:', e?.response?.status, e?.response?.data);
      setContracts([]);
      setLoadError(e.response?.data?.detail || e.message || 'Acente talepleri yüklenemedi');
      if (!silent) {
        toast.error('Sözleşmeler yüklenemedi: ' + (e.response?.data?.detail || e.message));
      }
    } finally {
      setLoading(false);
    }
  // eslint-disable-next-line react-hooks/exhaustive-deps -- tab/historyFilter degisiminde refetch
  }, [tab, historyFilter]);

  useEffect(() => {
    const ctrl = new AbortController();
    fetchContracts({ silent: true, signal: ctrl.signal });
    return () => ctrl.abort();
  }, [fetchContracts]);

  const openApprove = (c) => {
    setApproveDlg(c);
    setCommissionOverride(String(c.commission_pct ?? ''));
    setApproveNotes('');
  };

  const submitApprove = async () => {
    if (!approveDlg) return;
    setActing(true);
    try {
      const override = parseFloat(commissionOverride);
      const body = {
        notes: approveNotes,
        commission_pct_override: !isNaN(override) && override !== approveDlg.commission_pct ? override : null,
      };
      await axios.post(`/marketplace/incoming-requests/${approveDlg.id}/approve`, body);
      toast.success('Sözleşme onaylandı — acente artık otelinize rezervasyon yapabilir');
      setApproveDlg(null);
      fetchContracts();
    } catch (e) {
      toast.error('Onaylanamadı: ' + (e.response?.data?.detail || e.message));
    } finally {
      setActing(false);
    }
  };

  const openReject = (c) => {
    setRejectDlg(c);
    setRejectReason('');
  };

  const submitReject = async () => {
    if (!rejectDlg) return;
    setActing(true);
    try {
      await axios.post(`/marketplace/incoming-requests/${rejectDlg.id}/reject`, { reason: rejectReason });
      toast.success('Sözleşme reddedildi');
      setRejectDlg(null);
      fetchContracts();
    } catch (e) {
      toast.error('Reddedilemedi: ' + (e.response?.data?.detail || e.message));
    } finally {
      setActing(false);
    }
  };

  const openTerminate = (c) => {
    setTerminateDlg(c);
    setTerminateReason('');
  };

  const submitTerminate = async () => {
    if (!terminateDlg) return;
    setActing(true);
    try {
      await axios.post(`/marketplace/incoming-requests/${terminateDlg.id}/terminate`,
        { reason: terminateReason });
      toast.success('Sözleşme feshedildi — yeni rezervasyonlar engellenecek');
      setTerminateDlg(null);
      fetchContracts();
    } catch (e) {
      toast.error('Feshedilemedi: ' + (e.response?.data?.detail || e.message));
    } finally {
      setActing(false);
    }
  };

  return (
    <>
      <div className="p-6 max-w-7xl mx-auto space-y-6">
        <div className="flex flex-col gap-4 md:flex-row md:items-center md:justify-between">
          <div>
            <h1 className="text-2xl font-bold flex items-center gap-2">
              <Handshake className="w-6 h-6 text-blue-600 dark:text-blue-400" />
              Acente Sözleşme Talepleri
            </h1>
            <p className="text-sm text-muted-foreground mt-1">
              Marketplace'ten otelinize sözleşme teklifi gönderen acenteleri buradan yönetin.
              Sadece onayladığınız acenteler otelinize rezervasyon yapabilir.
            </p>
          </div>
          <Button variant="outline" size="sm" onClick={() => fetchContracts()} disabled={loading}>
            <RefreshCw className={`w-4 h-4 mr-1.5 ${loading ? 'animate-spin' : ''}`} />
            Yenile
          </Button>
        </div>

        <div className="rounded-xl border border-blue-200 bg-blue-50/70 p-4 dark:border-blue-800 dark:bg-blue-950/30">
          <div className="flex flex-col gap-4 lg:flex-row lg:items-center lg:justify-between">
            <div className="flex items-start gap-3">
              <div className="mt-0.5 rounded-lg bg-white p-2 text-blue-700 shadow-sm dark:bg-slate-900 dark:text-blue-300">
                <Info className="h-4 w-4" />
              </div>
              <div className="space-y-1">
                <p className="font-semibold text-slate-900 dark:text-slate-100">B2B iş ortaklığı onay merkezi</p>
                <p className="max-w-4xl text-sm leading-6 text-slate-600 dark:text-slate-300">
                  Burada komisyon, ödeme vadesi, geçerlilik ve iptal şartlarını inceleyip acenteye rezervasyon yetkisi verirsiniz. Bu ekran HotelRunner kanal bağlantılarını değil, Syroce Marketplace B2B sözleşmelerini yönetir.
                </p>
              </div>
            </div>
            <div className="flex flex-wrap gap-2">
              <Button asChild variant="outline" className="bg-white dark:bg-slate-900">
                <Link to="/agency-management">Acente Yönetimi <ArrowRight className="ml-2 h-4 w-4" /></Link>
              </Button>
              <Button asChild variant="outline" className="bg-white dark:bg-slate-900">
                <Link to="/travel-agent-arap">Komisyon ve Ödemeler <ArrowRight className="ml-2 h-4 w-4" /></Link>
              </Button>
            </div>
          </div>
        </div>

        <div className="grid gap-3 sm:grid-cols-3" data-testid="agency-contract-summary">
          <Card className="border-amber-200 bg-amber-50/60 dark:border-amber-900 dark:bg-amber-950/20">
            <CardContent className="flex items-center justify-between p-4">
              <div><p className="text-xs font-medium text-muted-foreground">Karar bekleyen</p><p className="text-2xl font-bold">{counts.pending || 0}</p></div>
              <Clock className="h-5 w-5 text-amber-600 dark:text-amber-400" />
            </CardContent>
          </Card>
          <Card className="border-emerald-200 bg-emerald-50/60 dark:border-emerald-900 dark:bg-emerald-950/20">
            <CardContent className="flex items-center justify-between p-4">
              <div><p className="text-xs font-medium text-muted-foreground">Aktif sözleşme</p><p className="text-2xl font-bold">{counts.approved || 0}</p></div>
              <CheckCircle2 className="h-5 w-5 text-emerald-600 dark:text-emerald-400" />
            </CardContent>
          </Card>
          <Card>
            <CardContent className="flex items-center justify-between p-4">
              <div><p className="text-xs font-medium text-muted-foreground">Geçmiş karar</p><p className="text-2xl font-bold">{counts.history || 0}</p></div>
              <FileText className="h-5 w-5 text-slate-500" />
            </CardContent>
          </Card>
        </div>

        <Tabs value={tab} onValueChange={(v) => { setTab(v); if (v !== 'history') setHistoryFilter('all'); }}>
          <TabsList className="grid grid-cols-3 w-full max-w-md">
            <TabsTrigger value="pending" data-testid="tab-pending">
              Bekleyen
              {counts.pending > 0 && (
                <Badge className="ml-2 bg-amber-100 text-amber-700 dark:bg-amber-950/50 dark:text-amber-300">{counts.pending}</Badge>
              )}
            </TabsTrigger>
            <TabsTrigger value="active" data-testid="tab-active">
              Aktif
              {counts.approved > 0 && (
                <Badge className="ml-2 bg-emerald-100 text-emerald-700 dark:bg-emerald-950/50 dark:text-emerald-300">{counts.approved}</Badge>
              )}
            </TabsTrigger>
            <TabsTrigger value="history" data-testid="tab-history">
              Geçmiş
              {counts.history > 0 && (
                <Badge className="ml-2 bg-slate-100 text-slate-700 dark:bg-slate-800 dark:text-slate-300">{counts.history}</Badge>
              )}
            </TabsTrigger>
          </TabsList>

          <TabsContent value={tab} className="mt-6 space-y-4">
              {tab === 'history' && (
                <div className="flex flex-wrap gap-2" data-testid="history-filters">
                  {[
                    { key: 'all',        label: 'Tümü',         count: counts.history ?? 0 },
                    { key: 'rejected',   label: 'Reddedildi',   count: counts.rejected ?? 0 },
                    { key: 'terminated', label: 'Feshedildi',   count: counts.terminated ?? 0 },
                    { key: 'expired',    label: 'Süresi Doldu', count: counts.expired ?? 0 },
                    { key: 'withdrawn',  label: 'Geri Çekildi', count: counts.withdrawn ?? 0 },
                  ].map(f => {
                    const active = historyFilter === f.key;
                    return (
                      <button
                        key={f.key}
                        type="button"
                        data-testid={`history-filter-${f.key}`}
                        onClick={() => setHistoryFilter(f.key)}
                        className={[
                          'inline-flex items-center gap-1.5 px-3 py-1.5 rounded-full text-xs border transition',
                          active
                            ? 'bg-slate-900 text-white border-slate-900 dark:bg-slate-100 dark:text-slate-900 dark:border-slate-100'
                            : 'bg-white text-slate-700 border-slate-200 hover:bg-slate-50 dark:bg-slate-900 dark:text-slate-300 dark:border-slate-700 dark:hover:bg-slate-800',
                        ].join(' ')}
                      >
                        {f.label}
                        <span className={[
                          'inline-flex items-center justify-center min-w-[1.25rem] h-5 px-1 rounded-full text-[10px] font-medium',
                          active ? 'bg-white/15 text-white dark:bg-slate-900/10 dark:text-slate-900' : 'bg-slate-100 text-slate-600 dark:bg-slate-800 dark:text-slate-300',
                        ].join(' ')}>{f.count}</span>
                      </button>
                    );
                  })}
                </div>
              )}
              {loading ? (
                <div className="text-center py-12">
                  <Loader2 className="w-8 h-8 animate-spin mx-auto text-slate-500" />
                </div>
              ) : loadError ? (
                <Card className="border-red-200 bg-red-50/60 dark:border-red-900 dark:bg-red-950/20" data-testid="agency-contract-load-error">
                  <CardContent className="flex flex-col items-center gap-3 py-10 text-center">
                    <AlertTriangle className="h-9 w-9 text-red-600 dark:text-red-400" />
                    <div>
                      <p className="font-semibold">Acente talepleri yüklenemedi</p>
                      <p className="mt-1 text-sm text-muted-foreground">{loadError}</p>
                    </div>
                    <Button variant="outline" size="sm" onClick={() => fetchContracts()}>
                      <RefreshCw className="mr-2 h-4 w-4" /> Yeniden Dene
                    </Button>
                  </CardContent>
                </Card>
              ) : contracts.length === 0 ? (
                <Card className="border-dashed border-slate-300 bg-slate-50/70 dark:border-slate-700 dark:bg-slate-900/40">
                  <CardContent className="py-12 text-center">
                    <div className="mx-auto mb-3 flex h-12 w-12 items-center justify-center rounded-full bg-white text-slate-500 shadow-sm dark:bg-slate-800 dark:text-slate-300">
                      <Handshake className="h-6 w-6" />
                    </div>
                    <p className="font-medium text-slate-800 dark:text-slate-200">
                      {tab === 'pending' && 'Şu an bekleyen acente talebi yok.'}
                      {tab === 'active' && 'Aktif sözleşmeniz olan acente yok.'}
                      {tab === 'history' && historyFilter === 'all' && 'Henüz geçmiş kayıt yok.'}
                      {tab === 'history' && historyFilter === 'rejected' && 'Reddedilen sözleşme yok.'}
                      {tab === 'history' && historyFilter === 'terminated' && 'Feshedilen sözleşme yok.'}
                      {tab === 'history' && historyFilter === 'expired' && 'Süresi dolmuş sözleşme yok.'}
                      {tab === 'history' && historyFilter === 'withdrawn' && 'Geri çekilmiş sözleşme yok.'}
                    </p>
                    <p className="mx-auto mt-2 max-w-xl text-sm text-muted-foreground">
                      Yeni bir Marketplace sözleşme teklifi geldiğinde acente, komisyon oranı ve ticari şartları burada görünecek.
                    </p>
                  </CardContent>
                </Card>
              ) : (
                <div className="grid md:grid-cols-2 gap-4">
                  {contracts.map(c => (
                    <ContractCard
                      key={c.id}
                      contract={c}
                      onApprove={openApprove}
                      onReject={openReject}
                      onTerminate={openTerminate}
                    />
                  ))}
                </div>
              )}
          </TabsContent>
        </Tabs>
      </div>

      {/* APPROVE DIALOG */}
      <Dialog open={!!approveDlg} onOpenChange={(o) => !o && setApproveDlg(null)}>
        <DialogContent>
          <DialogHeader>
            <DialogTitle>Sözleşmeyi Onayla — {approveDlg?.agency_name}</DialogTitle>
          </DialogHeader>
          <div className="space-y-4">
            <p className="text-sm text-muted-foreground">
              Acente <strong>%{approveDlg?.commission_pct?.toFixed(1)}</strong> komisyon teklif etti.
              Aşağıdan değiştirebilir veya aynen onaylayabilirsiniz.
            </p>
            <div>
              <Label>Komisyon (%)</Label>
              <Input
                data-testid="commission-override"
                type="number" min="0" max="100" step="0.1"
                value={commissionOverride}
                onChange={(e) => setCommissionOverride(e.target.value)}
              />
              <p className="text-xs text-muted-foreground mt-1">
                Acentenin teklif ettiği oranın üzerine yazabilirsiniz; aynı bırakırsanız teklif kabul edilir.
              </p>
            </div>
            <div>
              <Label>Not (opsiyonel)</Label>
              <Textarea
                data-testid="approve-notes"
                value={approveNotes}
                onChange={(e) => setApproveNotes(e.target.value)}
                placeholder="Örn: Yaz sezonu için özel anlaşma"
                rows={3}
              />
            </div>
          </div>
          <DialogFooter>
            <Button variant="outline" onClick={() => setApproveDlg(null)}>İptal</Button>
            <Button
              data-testid="confirm-approve"
              className="bg-emerald-600 hover:bg-emerald-500"
              onClick={submitApprove}
              disabled={acting}
            >
              {acting ? <Loader2 className="w-4 h-4 animate-spin" /> : <CheckCircle2 className="w-4 h-4 mr-1" />}
              Onayla
            </Button>
          </DialogFooter>
        </DialogContent>
      </Dialog>

      {/* REJECT DIALOG */}
      <Dialog open={!!rejectDlg} onOpenChange={(o) => !o && setRejectDlg(null)}>
        <DialogContent>
          <DialogHeader>
            <DialogTitle>Sözleşmeyi Reddet — {rejectDlg?.agency_name}</DialogTitle>
          </DialogHeader>
          <div className="space-y-4">
            <p className="text-sm text-muted-foreground">
              Bu acentenin teklifini reddediyorsunuz. İsterseniz sebebini belirtebilirsiniz —
              acenteye iletilecektir.
            </p>
            <div>
              <Label>Sebep (opsiyonel)</Label>
              <Textarea
                data-testid="reject-reason"
                value={rejectReason}
                onChange={(e) => setRejectReason(e.target.value)}
                placeholder="Örn: Komisyon oranı çok yüksek"
                rows={3}
              />
            </div>
          </div>
          <DialogFooter>
            <Button variant="outline" onClick={() => setRejectDlg(null)}>İptal</Button>
            <Button
              data-testid="confirm-reject"
              variant="destructive"
              onClick={submitReject}
              disabled={acting}
            >
              {acting ? <Loader2 className="w-4 h-4 animate-spin" /> : <XCircle className="w-4 h-4 mr-1" />}
              Reddet
            </Button>
          </DialogFooter>
        </DialogContent>
      </Dialog>

      {/* TERMINATE DIALOG */}
      <Dialog open={!!terminateDlg} onOpenChange={(o) => !o && setTerminateDlg(null)}>
        <DialogContent>
          <DialogHeader>
            <DialogTitle>Sözleşmeyi Feshet — {terminateDlg?.agency_name}</DialogTitle>
          </DialogHeader>
          <div className="space-y-4">
            <p className="flex items-start gap-1.5 rounded border border-amber-200 bg-amber-50 p-2 text-sm text-amber-800 dark:border-amber-900 dark:bg-amber-950/20 dark:text-amber-300">
              <AlertTriangle className="w-4 h-4 mt-0.5 shrink-0" />
              <span>Fesih sonrası bu acente <strong>yeni rezervasyon</strong> yapamayacak.
              Mevcut rezervasyonlar etkilenmez.</span>
            </p>
            <div>
              <Label>Fesih Sebebi</Label>
              <Textarea
                data-testid="terminate-reason"
                value={terminateReason}
                onChange={(e) => setTerminateReason(e.target.value)}
                placeholder="Örn: Sözleşme şartlarına uyulmadı"
                rows={3}
              />
            </div>
          </div>
          <DialogFooter>
            <Button variant="outline" onClick={() => setTerminateDlg(null)}>İptal</Button>
            <Button
              data-testid="confirm-terminate"
              variant="destructive"
              onClick={submitTerminate}
              disabled={acting}
            >
              {acting ? <Loader2 className="w-4 h-4 animate-spin" /> : <Ban className="w-4 h-4 mr-1" />}
              Feshet
            </Button>
          </DialogFooter>
        </DialogContent>
      </Dialog>
    </>
  );
};

export default IncomingAgencyContracts;
