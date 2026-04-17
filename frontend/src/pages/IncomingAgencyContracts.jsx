import { useState, useEffect, useCallback } from 'react';
import axios from 'axios';
import { toast } from 'sonner';
import { useTranslation } from 'react-i18next';
import Layout from '@/components/Layout';
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
} from 'lucide-react';

const STATUS_META = {
  pending:    { color: 'bg-amber-500/15 text-amber-400 border-amber-500/30',   icon: Clock,        label: 'Bekliyor' },
  approved:   { color: 'bg-emerald-500/15 text-emerald-400 border-emerald-500/30', icon: CheckCircle2, label: 'Onaylı' },
  rejected:   { color: 'bg-red-500/15 text-red-400 border-red-500/30',          icon: XCircle,      label: 'Reddedildi' },
  terminated: { color: 'bg-slate-500/15 text-slate-300 border-slate-500/30',    icon: Ban,          label: 'Feshedildi' },
  expired:    { color: 'bg-slate-500/15 text-slate-400 border-slate-700',       icon: Clock,        label: 'Süresi Doldu' },
  withdrawn:  { color: 'bg-slate-500/15 text-slate-400 border-slate-700',       icon: Ban,          label: 'Geri Çekildi' },
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
    <Card className="bg-slate-900/50 border-slate-700 hover:border-slate-600 transition">
      <CardHeader className="pb-3">
        <div className="flex items-start justify-between gap-3">
          <div className="min-w-0">
            <CardTitle className="text-base flex items-center gap-2">
              <Building2 className="w-4 h-4 text-cyan-400 shrink-0" />
              <span className="truncate">{contract.agency_name || 'Acente'}</span>
              <span className="text-xs font-mono text-slate-500">{contract.contract_code}</span>
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
              <div className="text-slate-400 text-xs">Komisyon</div>
              <div className="font-semibold">%{contract.commission_pct?.toFixed(1)}</div>
              {contract.agency_proposed_commission_pct !== contract.commission_pct && isApproved && (
                <div className="text-[10px] text-slate-500">
                  Teklif: %{contract.agency_proposed_commission_pct?.toFixed(1)}
                </div>
              )}
            </div>
          </div>
          <div className="flex items-center gap-2">
            <CreditCard className="w-4 h-4 text-violet-400" />
            <div>
              <div className="text-slate-400 text-xs">Ödeme</div>
              <div className="font-semibold">{PAYMENT_LABEL[contract.payment_terms] || contract.payment_terms}</div>
            </div>
          </div>
          <div className="flex items-center gap-2">
            <Calendar className="w-4 h-4 text-cyan-400" />
            <div>
              <div className="text-slate-400 text-xs">Geçerlilik</div>
              <div className="font-semibold text-xs">{contract.valid_from} → {contract.valid_to}</div>
            </div>
          </div>
          <div className="flex items-center gap-2">
            <Globe className="w-4 h-4 text-emerald-400" />
            <div>
              <div className="text-slate-400 text-xs">Para Birimi</div>
              <div className="font-semibold">{contract.currency}</div>
            </div>
          </div>
        </div>

        <div className="rounded-md bg-slate-950/60 p-3 text-xs space-y-1">
          <div className="font-semibold text-slate-300 flex items-center gap-1">
            <AlertTriangle className="w-3 h-3" /> İptal Politikası
          </div>
          <div className="text-slate-400">
            {cp.free_until_days_before ?? 7} gün öncesine kadar ücretsiz —
            sonrasında %{cp.penalty_pct ?? 50} ceza —
            no-show: %{cp.no_show_penalty_pct ?? 100}
          </div>
        </div>

        {contract.allowed_room_types?.length > 0 && (
          <div className="text-xs">
            <span className="text-slate-400">İzinli Oda Tipleri: </span>
            {contract.allowed_room_types.map(rt => (
              <Badge key={rt} className="ml-1 bg-slate-800 text-slate-300">{rt}</Badge>
            ))}
          </div>
        )}

        {contract.special_terms && (
          <div className="text-xs bg-slate-950/40 border border-slate-800 rounded p-2">
            <div className="text-slate-400 mb-1 flex items-center gap-1">
              <FileText className="w-3 h-3" /> Özel Şartlar
            </div>
            <div className="whitespace-pre-wrap text-slate-300">{contract.special_terms}</div>
          </div>
        )}

        {contract.decision_notes && !isPending && (
          <div className="text-xs text-slate-400 italic">
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
                      className="ml-auto border-red-800 text-red-400 hover:bg-red-950"
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
  const { t: _t } = useTranslation();
  const [tab, setTab] = useState('pending');
  const [loading, setLoading] = useState(false);
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

  const tabToStatus = {
    pending: 'pending',
    active: 'approved',
    history: null,
  };

  const fetchContracts = useCallback(async () => {
    setLoading(true);
    try {
      const status = tabToStatus[tab];
      const params = status ? { status } : {};
      const { data } = await axios.get('/api/marketplace/incoming-requests', { params });
      let list = data.contracts || [];
      if (tab === 'history') {
        list = list.filter(c => ['rejected', 'terminated', 'expired', 'withdrawn'].includes(c.status));
      }
      setContracts(list);
      setCounts(data.counts || {});
    } catch (e) {
      toast.error('Sözleşmeler yüklenemedi: ' + (e.response?.data?.detail || e.message));
    } finally {
      setLoading(false);
    }
  }, [tab]);

  useEffect(() => { fetchContracts(); }, [fetchContracts]);

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
      await axios.post(`/api/marketplace/incoming-requests/${approveDlg.id}/approve`, body);
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
      await axios.post(`/api/marketplace/incoming-requests/${rejectDlg.id}/reject`, { reason: rejectReason });
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
      await axios.post(`/api/marketplace/incoming-requests/${terminateDlg.id}/terminate`,
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
    <Layout user={user} tenant={tenant} onLogout={onLogout}>
      <div className="p-6 max-w-7xl mx-auto space-y-6">
        <div className="flex items-center justify-between">
          <div>
            <h1 className="text-2xl font-bold flex items-center gap-2">
              <Handshake className="w-6 h-6 text-cyan-400" />
              Gelen Acente Talepleri
            </h1>
            <p className="text-sm text-slate-400 mt-1">
              Marketplace'ten otelinize sözleşme teklifi gönderen acenteleri buradan yönetin.
              Sadece onayladığınız acenteler otelinize rezervasyon yapabilir.
            </p>
          </div>
          <Button variant="outline" onClick={fetchContracts} disabled={loading}>
            <RefreshCw className={`w-4 h-4 mr-2 ${loading ? 'animate-spin' : ''}`} />
            Yenile
          </Button>
        </div>

        <Tabs value={tab} onValueChange={setTab}>
          <TabsList className="grid grid-cols-3 w-full max-w-md">
            <TabsTrigger value="pending" data-testid="tab-pending">
              Bekleyen
              {counts.pending > 0 && (
                <Badge className="ml-2 bg-amber-500/20 text-amber-300">{counts.pending}</Badge>
              )}
            </TabsTrigger>
            <TabsTrigger value="active" data-testid="tab-active">
              Aktif
              {counts.approved > 0 && (
                <Badge className="ml-2 bg-emerald-500/20 text-emerald-300">{counts.approved}</Badge>
              )}
            </TabsTrigger>
            <TabsTrigger value="history" data-testid="tab-history">Geçmiş</TabsTrigger>
          </TabsList>

          {['pending', 'active', 'history'].map(v => (
            <TabsContent key={v} value={v} className="mt-6">
              {loading ? (
                <div className="text-center py-12">
                  <Loader2 className="w-8 h-8 animate-spin mx-auto text-slate-500" />
                </div>
              ) : contracts.length === 0 ? (
                <Card className="bg-slate-900/30 border-dashed border-slate-700">
                  <CardContent className="py-12 text-center">
                    <Handshake className="w-12 h-12 mx-auto text-slate-600 mb-3" />
                    <p className="text-slate-400">
                      {v === 'pending' && 'Şu an bekleyen acente talebi yok.'}
                      {v === 'active' && 'Aktif sözleşmeniz olan acente yok.'}
                      {v === 'history' && 'Henüz geçmiş kayıt yok.'}
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
          ))}
        </Tabs>
      </div>

      {/* APPROVE DIALOG */}
      <Dialog open={!!approveDlg} onOpenChange={(o) => !o && setApproveDlg(null)}>
        <DialogContent>
          <DialogHeader>
            <DialogTitle>Sözleşmeyi Onayla — {approveDlg?.agency_name}</DialogTitle>
          </DialogHeader>
          <div className="space-y-4">
            <p className="text-sm text-slate-400">
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
              <p className="text-xs text-slate-500 mt-1">
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
            <p className="text-sm text-slate-400">
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
            <p className="text-sm text-amber-400 bg-amber-950/20 border border-amber-900 rounded p-2">
              ⚠️ Fesih sonrası bu acente <strong>yeni rezervasyon</strong> yapamayacak.
              Mevcut rezervasyonlar etkilenmez.
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
    </Layout>
  );
};

export default IncomingAgencyContracts;
