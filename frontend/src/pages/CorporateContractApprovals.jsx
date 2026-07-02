import { useTranslation } from "react-i18next";
import React, { useEffect, useMemo, useState } from 'react';
import { Card, CardHeader, CardTitle, CardContent } from '@/components/ui/card';
import { Button } from '@/components/ui/button';
import { StatusBadge } from '@/components/ui/status-badge';
import { KpiCard } from '@/components/ui/kpi-card';
import { PageHeader } from '@/components/ui/page-header';
import { Dialog, DialogContent, DialogHeader, DialogTitle, DialogDescription, DialogFooter } from '@/components/ui/dialog';
import { Textarea } from '@/components/ui/textarea';
import { Label } from '@/components/ui/label';
import { Building2, RefreshCw, FileText, History, XCircle, CheckCircle2, Clock, FilePen, AlertTriangle, Send } from 'lucide-react';
import { toast } from 'sonner';
import { confirmDialog } from '@/lib/dialogs';

// Approval-status → presentation map. Mirrors the backend state machine in
// rms_router/sales.py (draft → pending → approved | rejected, rejected → draft).
const APPROVAL_META = {
  draft: {
    label: 'Taslak',
    intent: 'neutral',
    icon: FilePen
  },
  pending: {
    label: 'Onay Bekliyor',
    intent: 'info',
    icon: Clock
  },
  approved: {
    label: 'Onaylandı',
    intent: 'success',
    icon: CheckCircle2
  },
  rejected: {
    label: 'Reddedildi',
    intent: 'danger',
    icon: XCircle
  }
};
function approvalMeta(status) {
  return APPROVAL_META[status] || APPROVAL_META.draft;
}
function formatDateTime(iso) {
  if (!iso) return '-';
  const d = new Date(iso);
  if (Number.isNaN(d.getTime())) return iso;
  return d.toLocaleString();
}

// Most recent rejection entry in approval_history (newest wins). The history is
// appended chronologically, so we scan from the end.
function latestRejection(history) {
  if (!Array.isArray(history)) return null;
  for (let i = history.length - 1; i >= 0; i -= 1) {
    if (history[i] && history[i].to_status === 'rejected') return history[i];
  }
  return null;
}
const CorporateContractApprovals = () => {
  const {
    t
  } = useTranslation();
  const [contracts, setContracts] = useState([]);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState(null);
  const [historyContract, setHistoryContract] = useState(null);
  // Owner resubmit flow: the rejected contract currently being re-sent.
  const [resubmittingId, setResubmittingId] = useState(null);
  // Contract currently being approved/rejected (id) so we can disable its
  // buttons and avoid double-submits while the request is in flight.
  const [actioningId, setActioningId] = useState(null);
  // Reject flow: the contract being rejected + the mandatory reason text.
  const [rejectContract, setRejectContract] = useState(null);
  const [rejectReason, setRejectReason] = useState('');
  const loadContracts = async () => {
    setLoading(true);
    setError(null);
    try {
      const res = await fetch('/api/sales/corporate-contracts', {
        credentials: "include",
        headers: {}
      });
      if (!res.ok) {
        throw new Error(`HTTP ${res.status}`);
      }
      const data = await res.json();
      setContracts(Array.isArray(data.contracts) ? data.contracts : []);
    } catch (err) {
      console.error('Failed to load corporate contracts', err);
      setError('Kurumsal sözleşmeler yüklenemedi.');
      setContracts([]);
    } finally {
      setLoading(false);
    }
  };

  // Low-level approval-transition POST. The backend (rms_router/sales.py) is the
  // source of truth: it validates the transition and 400s on a rejection without
  // a reason, so we surface its error detail verbatim rather than re-implementing
  // the rules client-side.
  const postTransition = async (contractId, toStatus, reason) => {
    const res = await fetch(`/api/sales/corporate-contract/${contractId}/approval-transition`, {
      method: 'POST',
      headers: {
        'Content-Type': 'application/json'
      },
      body: JSON.stringify({
        to_status: toStatus,
        reason: reason || null
      }),
      credentials: "include"
    });
    if (!res.ok) {
      let detail = `HTTP ${res.status}`;
      try {
        const body = await res.json();
        if (body && body.detail) detail = body.detail;
      } catch (_) {/* non-JSON error body */}
      throw new Error(detail);
    }
    return res.json();
  };

  // Move a rejected contract back through rejected → draft → pending so the
  // owner can re-submit it for approval after fixing the issue. Two sequential
  // transitions because the backend state machine only allows one hop each
  // (CONTRACT_APPROVAL_TRANSITIONS in rms_router/sales.py).
  const handleResubmit = async contract => {
    if (!contract || contract.approval_status !== 'rejected') return;
    const ok = await confirmDialog({
      title: 'Sözleşmeyi Yeniden Gönder',
      message: `"${contract.company_name || 'Bu sözleşme'}" taslağa alınıp tekrar ` + 'onaya gönderilecek. Devam edilsin mi?',
      confirmText: 'Yeniden Gönder',
      cancelText: 'Vazgeç'
    });
    if (!ok) return;
    setResubmittingId(contract.id);
    try {
      await postTransition(contract.id, 'draft');
      await postTransition(contract.id, 'pending');
      toast.success('Sözleşme yeniden onaya gönderildi.');
      await loadContracts();
    } catch (err) {
      console.error('Failed to resubmit corporate contract', err);
      toast.error(`Yeniden gönderilemedi: ${err.message || 'Bilinmeyen hata'}`);
    } finally {
      setResubmittingId(null);
    }
  };
  useEffect(() => {
    loadContracts();
  }, []);

  // Approver action: drive a single contract through one approval hop and give
  // toast feedback, disabling its buttons while the request is in flight.
  // The backend returns `owner_notified` (Task #235): whether the outcome email
  // actually reached the contract owner. We surface it so approvers can tell the
  // owner was informed — and warn (without failing the approval) when the email
  // was skipped because the contact_email is missing/invalid.
  const runApproverAction = async (contract, toStatus, reason) => {
    setActioningId(contract.id);
    try {
      const result = await postTransition(contract.id, toStatus, reason);
      const company = contract.company_name || 'Sözleşme';
      // Tri-state: true = sent, false = skipped/failed, undefined = older
      // backend that doesn't report it (stay silent rather than guess).
      const ownerNotified = result && typeof result.owner_notified === 'boolean' ? result.owner_notified : null;
      toast.success(toStatus === 'approved' ? 'Sözleşme onaylandı' : 'Sözleşme reddedildi', {
        description: ownerNotified === true ? `${company} · Sözleşme sahibine bilgilendirme e-postası gönderildi.` : company
      });
      if (ownerNotified === false) {
        toast.warning('Sözleşme sahibine e-posta gönderilemedi', {
          description: 'Geçerli bir iletişim e-postası bulunmadığı için bildirim ' + 'atlandı. Sözleşmenin iletişim e-postasını güncelleyin.',
          duration: 8000
        });
      }
      return true;
    } catch (err) {
      console.error('Approval transition failed', err);
      toast.error('İşlem başarısız', {
        description: err.message
      });
      return false;
    } finally {
      setActioningId(null);
    }
  };
  const handleApprove = async contract => {
    const ok = await runApproverAction(contract, 'approved');
    if (ok) await loadContracts();
  };
  const submitReject = async () => {
    if (!rejectContract) return;
    const reason = rejectReason.trim();
    if (!reason) return;
    const ok = await runApproverAction(rejectContract, 'rejected', reason);
    if (ok) {
      setRejectContract(null);
      setRejectReason('');
      await loadContracts();
    }
  };
  const counts = useMemo(() => {
    const acc = {
      total: contracts.length,
      pending: 0,
      approved: 0,
      rejected: 0
    };
    for (const c of contracts) {
      const s = c.approval_status || 'draft';
      if (s === 'pending') acc.pending += 1;else if (s === 'approved') acc.approved += 1;else if (s === 'rejected') acc.rejected += 1;
    }
    return acc;
  }, [contracts]);
  return <div className="p-4 md:p-6 max-w-7xl mx-auto">
      <PageHeader icon={Building2} title={t("cm.pages_CorporateContractApprovals.kurumsal_s\xF6zle\u015Fme_onaylar\u0131")} subtitle="Onay bekleyen sözleşmeleri inceleyin; onaylayın veya gerekçe belirterek reddedin. Reddedilen sözleşmelerde gerekçeyi okuyup düzeltin ve yeniden gönderin." actions={<Button size="sm" variant="outline" onClick={loadContracts} disabled={loading}>
            <RefreshCw className={`w-4 h-4 mr-1 ${loading ? 'animate-spin' : ''}`} />{t("cm.pages_CorporateContractApprovals.yenile")}</Button>} />

      <div className="grid grid-cols-2 md:grid-cols-4 gap-3 mb-5">
        <KpiCard icon={FileText} label={t("cm.pages_CorporateContractApprovals.toplam_s\xF6zle\u015Fme")} value={counts.total} />
        <KpiCard icon={Clock} label={t("cm.pages_CorporateContractApprovals.onay_bekleyen")} value={counts.pending} intent="info" />
        <KpiCard icon={CheckCircle2} label={t("cm.pages_CorporateContractApprovals.onaylanan")} value={counts.approved} intent="success" />
        <KpiCard icon={XCircle} label={t("cm.pages_CorporateContractApprovals.reddedilen")} value={counts.rejected} intent="danger" />
      </div>

      {error && <Card className="mb-4 border-l-4 border-l-rose-500">
          <CardContent className="p-4 flex items-center gap-2 text-sm text-rose-700">
            <AlertTriangle className="w-4 h-4" />
            {error}
          </CardContent>
        </Card>}

      <Card>
        <CardHeader className="pb-2">
          <CardTitle className="text-sm flex items-center gap-2">
            <FileText className="w-4 h-4" />{t("cm.pages_CorporateContractApprovals.s\xF6zle\u015Fmeler")}{contracts.length})
          </CardTitle>
        </CardHeader>
        <CardContent>
          {loading ? <div className="py-10 text-center text-gray-500 text-sm flex items-center justify-center gap-2">
              <RefreshCw className="w-5 h-5 animate-spin" />{t("cm.pages_CorporateContractApprovals.y\xFCkleniyor")}</div> : contracts.length === 0 ? <div className="py-10 text-center text-gray-500 text-sm">{t("cm.pages_CorporateContractApprovals.hen\xFCz_kurumsal_s\xF6zle\u015Fme_bulunm")}</div> : <div className="space-y-3">
              {contracts.map(c => {
            const meta = approvalMeta(c.approval_status);
            const rejection = c.approval_status === 'rejected' ? latestRejection(c.approval_history) : null;
            const historyLen = Array.isArray(c.approval_history) ? c.approval_history.length : 0;
            return <Card key={c.id} className={`border-l-4 ${c.approval_status === 'rejected' ? 'border-l-rose-500' : c.approval_status === 'approved' ? 'border-l-emerald-500' : c.approval_status === 'pending' ? 'border-l-sky-500' : 'border-l-slate-300'}`}>
                    <CardContent className="p-4">
                      <div className="flex flex-col md:flex-row md:items-start md:justify-between gap-3">
                        <div className="min-w-0 space-y-1">
                          <div className="flex items-center gap-2 flex-wrap">
                            <h3 className="text-base font-semibold text-slate-900">
                              {c.company_name || 'İsimsiz Sözleşme'}
                            </h3>
                            <StatusBadge intent={meta.intent} icon={meta.icon}>
                              {meta.label}
                            </StatusBadge>
                          </div>
                          <div className="text-xs text-gray-500 flex flex-wrap gap-x-4 gap-y-1">
                            {c.contract_type && <span>{t("cm.pages_CorporateContractApprovals.t\xFCr")}{c.contract_type}</span>}
                            {c.rate_code && <span>{t("cm.pages_CorporateContractApprovals.kod")}{c.rate_code}</span>}
                            {(c.start_date || c.end_date) && <span>{t("cm.pages_CorporateContractApprovals.d\xF6nem")}{c.start_date || '?'} – {c.end_date || '?'}</span>}
                          </div>
                        </div>
                        <div className="flex items-center gap-2 flex-wrap shrink-0">
                          {c.approval_status === 'pending' && <>
                              <Button size="sm" onClick={() => handleApprove(c)} disabled={actioningId === c.id} className="bg-emerald-600 hover:bg-emerald-700 text-white">
                                {actioningId === c.id ? <RefreshCw className="w-4 h-4 mr-1 animate-spin" /> : <CheckCircle2 className="w-4 h-4 mr-1" />}{t("cm.pages_CorporateContractApprovals.onayla")}</Button>
                              <Button size="sm" variant="outline" onClick={() => {
                        setRejectContract(c);
                        setRejectReason('');
                      }} disabled={actioningId === c.id} className="border-rose-300 text-rose-700 hover:bg-rose-50">
                                <XCircle className="w-4 h-4 mr-1" />{t("cm.pages_CorporateContractApprovals.reddet")}</Button>
                            </>}
                          <Button size="sm" variant="outline" onClick={() => setHistoryContract(c)} disabled={historyLen === 0}>
                            <History className="w-4 h-4 mr-1" />{t("cm.pages_CorporateContractApprovals.onay_ge\xE7mi\u015Fi")}{historyLen ? ` (${historyLen})` : ''}
                          </Button>
                        </div>
                      </div>

                      {rejection && <div className="mt-3 rounded-md border border-rose-200 bg-rose-50 p-3">
                          <div className="flex items-center gap-2 text-rose-800 text-sm font-semibold">
                            <XCircle className="w-4 h-4" />{t("cm.pages_CorporateContractApprovals.reddedilme_gerek\xE7esi")}</div>
                          <p className="mt-1 text-sm text-rose-900 whitespace-pre-wrap break-words">
                            {rejection.reason || 'Gerekçe belirtilmemiş.'}
                          </p>
                          <div className="mt-2 text-[11px] text-rose-700">
                            {rejection.by ? `${rejection.by} tarafından` : 'Bilinmeyen kullanıcı'}
                            {' · '}
                            {formatDateTime(rejection.at)}
                          </div>
                          <p className="mt-2 text-[11px] text-rose-700">{t("cm.pages_CorporateContractApprovals.sonraki_ad\u0131m_gerekli_d\xFCzeltmel")}</p>
                          <div className="mt-3">
                            <Button size="sm" onClick={() => handleResubmit(c)} disabled={resubmittingId === c.id}>
                              {resubmittingId === c.id ? <RefreshCw className="w-4 h-4 mr-1 animate-spin" /> : <Send className="w-4 h-4 mr-1" />}{t("cm.pages_CorporateContractApprovals.yeniden_g\xF6nder")}</Button>
                          </div>
                        </div>}
                    </CardContent>
                  </Card>;
          })}
            </div>}
        </CardContent>
      </Card>

      <Dialog open={!!historyContract} onOpenChange={open => !open && setHistoryContract(null)}>
        <DialogContent className="max-w-lg">
          <DialogHeader>
            <DialogTitle className="flex items-center gap-2">
              <History className="w-4 h-4" />{t("cm.pages_CorporateContractApprovals.onay_ge\xE7mi\u015Fi")}</DialogTitle>
            <DialogDescription>
              {historyContract?.company_name || 'Sözleşme'}{t("cm.pages_CorporateContractApprovals._durum_ge\xE7i\u015Fleri_gerek\xE7eler_ki")}</DialogDescription>
          </DialogHeader>
          <div className="max-h-[60vh] overflow-y-auto space-y-3 pr-1">
            {(historyContract?.approval_history || []).length === 0 ? <div className="py-6 text-center text-sm text-gray-500">{t("cm.pages_CorporateContractApprovals.hen\xFCz_onay_hareketi_yok")}</div> : [...(historyContract?.approval_history || [])].slice().reverse().map((entry, idx) => {
            const toMeta = approvalMeta(entry.to_status);
            const fromMeta = approvalMeta(entry.from_status);
            return <div key={idx} className="rounded-md border border-slate-200 p-3">
                      <div className="flex items-center gap-2 text-sm flex-wrap">
                        <StatusBadge intent={fromMeta.intent}>{fromMeta.label}</StatusBadge>
                        <span className="text-gray-400">→</span>
                        <StatusBadge intent={toMeta.intent} icon={toMeta.icon}>
                          {toMeta.label}
                        </StatusBadge>
                      </div>
                      {entry.reason && <p className="mt-2 text-sm text-slate-700 whitespace-pre-wrap break-words">
                          {entry.reason}
                        </p>}
                      <div className="mt-2 text-[11px] text-gray-500">
                        {entry.by ? `${entry.by} tarafından` : 'Bilinmeyen kullanıcı'}
                        {' · '}
                        {formatDateTime(entry.at)}
                      </div>
                    </div>;
          })}
          </div>
        </DialogContent>
      </Dialog>

      <Dialog open={!!rejectContract} onOpenChange={open => {
      if (!open) {
        setRejectContract(null);
        setRejectReason('');
      }
    }}>
        <DialogContent className="max-w-lg">
          <DialogHeader>
            <DialogTitle className="flex items-center gap-2">
              <XCircle className="w-4 h-4 text-rose-600" />{t("cm.pages_CorporateContractApprovals.s\xF6zle\u015Fmeyi_reddet")}</DialogTitle>
            <DialogDescription>
              {rejectContract?.company_name || 'Sözleşme'}{t("cm.pages_CorporateContractApprovals.reddedilecek_gerek\xE7e_zorunludu")}</DialogDescription>
          </DialogHeader>
          <div className="space-y-2">
            <Label htmlFor="reject-reason">{t("cm.pages_CorporateContractApprovals.reddetme_gerek\xE7esi")}</Label>
            <Textarea id="reject-reason" value={rejectReason} onChange={e => setRejectReason(e.target.value)} placeholder={t("cm.pages_CorporateContractApprovals.\xF6rn_g\xF6r\xFC\u015F\xFClen_oran_politikam\u0131z")} rows={4} autoFocus />
          </div>
          <DialogFooter>
            <Button variant="outline" onClick={() => {
            setRejectContract(null);
            setRejectReason('');
          }} disabled={!!actioningId}>{t("cm.pages_CorporateContractApprovals.vazge\xE7")}</Button>
            <Button onClick={submitReject} disabled={!rejectReason.trim() || !!actioningId} className="bg-rose-600 hover:bg-rose-700 text-white">
              {actioningId ? <RefreshCw className="w-4 h-4 mr-1 animate-spin" /> : <XCircle className="w-4 h-4 mr-1" />}{t("cm.pages_CorporateContractApprovals.reddet")}</Button>
          </DialogFooter>
        </DialogContent>
      </Dialog>
    </div>;
};
export default CorporateContractApprovals;