import { useEffect, useMemo, useRef, useState } from 'react';
import { useLocation, useNavigate } from 'react-router-dom';
import { useTranslation } from 'react-i18next';
import axios from 'axios';
import { toast } from 'sonner';
import { Card, CardContent, CardHeader, CardTitle, CardDescription } from '@/components/ui/card';
import { Button } from '@/components/ui/button';
import { Input } from '@/components/ui/input';
import { Label } from '@/components/ui/label';
import { Badge } from '@/components/ui/badge';
import { Tabs, TabsContent, TabsList, TabsTrigger } from '@/components/ui/tabs';
import { Plus, Truck, ClipboardList, Package, FileCheck2, RefreshCw, Trash2, Send, History as HistoryIcon, X, Check, Ban, TrendingUp } from 'lucide-react';
import EntityHistoryDrawer from '@/components/EntityHistoryDrawer';
import ProcurementB2BTab from './ProcurementB2BTab';
import { confirmDialog, promptDialog } from '@/lib/dialogs';
// Status → CSS class only. Display label comes from i18n via prStatuses/poStatuses.
const PR_STATUS_CLS = {
  draft: 'bg-slate-100 text-slate-700',
  submitted: 'bg-amber-100 text-amber-800',
  approved: 'bg-emerald-100 text-emerald-800',
  rejected: 'bg-red-100 text-red-800',
  cancelled: 'bg-slate-100 text-slate-700',
  converted: 'bg-sky-100 text-sky-800'
};
const PO_STATUS_CLS = {
  draft: 'bg-slate-100 text-slate-700',
  sent: 'bg-amber-100 text-amber-800',
  partially_received: 'bg-sky-100 text-sky-800',
  received: 'bg-emerald-100 text-emerald-800',
  cancelled: 'bg-red-100 text-red-800',
  closed: 'bg-slate-200 text-slate-700'
};
const tl = (n, locale='tr-TR') => `${Number(n || 0).toLocaleString(locale, {
  minimumFractionDigits: 2,
  maximumFractionDigits: 2
})} ₺`;
const Modal = ({
  title,
  children,
  onClose,
  wide
}) => <div className="fixed inset-0 z-40 bg-black/40 flex items-center justify-center p-4" onClick={onClose}>
    <div className={`bg-white rounded-lg shadow-xl ${wide ? 'max-w-4xl' : 'max-w-2xl'} w-full max-h-[90vh] overflow-y-auto`} onClick={e => e.stopPropagation()}>
      <div className="border-b p-3 flex items-center justify-between sticky top-0 bg-white">
        <h2 className="font-semibold">{title}</h2>
        <Button size="sm" variant="ghost" onClick={onClose}><X className="w-4 h-4" /></Button>
      </div>
      <div className="p-4">{children}</div>
    </div>
  </div>;
const ProcurementPage = ({
  user,
  tenant,
  onLogout
}) => {
  const { t, i18n } = useTranslation();
  const location = useLocation();
  const navigate = useNavigate();
  const [tab, setTab] = useState('summary');
  const [summary, setSummary] = useState({});
  const [suppliers, setSuppliers] = useState([]);
  const [prs, setPrs] = useState([]);
  const [pos, setPos] = useState([]);
  const [inventoryItems, setInventoryItems] = useState([]);
  const [loading, setLoading] = useState(false);
  const [history, setHistory] = useState(null);
  const [supplierForm, setSupplierForm] = useState(null);
  const [prForm, setPrForm] = useState(null);
  const [poForm, setPoForm] = useState(null);
  const [grnForm, setGrnForm] = useState(null);
  const [selectedPo, setSelectedPo] = useState(null);
  const [creditUtil, setCreditUtil] = useState(null);
  const creditReqRef = useRef(0);
  const [creditReport, setCreditReport] = useState([]);
  const [creditReportLoaded, setCreditReportLoaded] = useState(false);
  const [creditReportLoading, setCreditReportLoading] = useState(false);
  const [creditIncludeUnlimited, setCreditIncludeUnlimited] = useState(false);
  const prLabel = code => t(`procurement.prStatuses.${code || 'draft'}`);
  const poLabel = code => t(`procurement.poStatuses.${code || 'draft'}`);

  // ── PR yetkilendirmesi ───────────────────────────────────
  // Backend zaten 403 döner (require_finance), frontend sadece UI'yı
  // sadeleştirir: talebi açan kişiye onay/red butonlarını göstermez,
  // yalnızca yetkili roller görsün. "Genel müdür" admin/owner,
  // "Satınalma" procurement rolü, finance da fatura tarafı için yetkili.
  const APPROVER_ROLES = useMemo(() => new Set(['super_admin', 'admin', 'owner', 'finance', 'procurement']), []);
  const canApprovePR = useMemo(() => {
    const roles = [user?.role, ...(Array.isArray(user?.roles) ? user.roles : [])].filter(Boolean);
    return roles.some(r => APPROVER_ROLES.has(r));
  }, [user, APPROVER_ROLES]);
  // Kendi açtığı talep mi? created_by backend tarafından atanır,
  // requester serbest text (boş bırakılabilir) → öncelikle created_by'a bak.
  const isOwnPR = pr => {
    const me = user?.username || user?.name;
    if (!me) return false;
    return pr.created_by === me || pr.requester === me;
  };

  // Tab-aware lazy loading. Only the data needed for the initial view is
  // fetched on mount; POs and inventory load on demand. `refresh()` (used by
  // every CRUD success path below) keeps the original "reload everything"
  // behavior so post-write screens stay consistent.
  const [posLoaded, setPosLoaded] = useState(false);
  const [invLoaded, setInvLoaded] = useState(false);
  // In-flight guard prevents duplicate inventory fetches when the gating
  // form object changes on every keystroke before the first response lands.
  const invLoadingRef = useRef(false);
  const loadSummary = async () => {
    const r = await axios.get('/procurement/summary');
    setSummary(r.data || {});
  };
  const loadSuppliers = async () => {
    const r = await axios.get('/procurement/suppliers?active_only=false&with_commitment=true');
    setSuppliers(r.data?.items || []);
  };
  const loadPRs = async () => {
    const r = await axios.get('/procurement/purchase-requests');
    setPrs(r.data?.items || []);
  };
  const loadPOs = async () => {
    const r = await axios.get('/procurement/purchase-orders');
    setPos(r.data?.items || []);
    setPosLoaded(true);
  };
  const loadCreditReport = async (includeUnlimited = creditIncludeUnlimited) => {
    setCreditReportLoading(true);
    try {
      const r = await axios.get('/procurement/credit-utilisation', {
        params: {
          include_unlimited: includeUnlimited
        }
      });
      setCreditReport(r.data?.items || []);
      setCreditReportLoaded(true);
    } catch (e) {
      toast.error(t('procurement.errors.loadFailed'));
    } finally {
      setCreditReportLoading(false);
    }
  };
  const loadInventory = async () => {
    if (invLoadingRef.current) return;
    invLoadingRef.current = true;
    try {
      const r = await axios.get('/accounting/inventory');
      setInventoryItems(r.data?.items || []);
      setInvLoaded(true);
    } catch {
      setInventoryItems([]);
      // leave invLoaded=false so a later trigger can retry
    } finally {
      invLoadingRef.current = false;
    }
  };
  const refresh = async () => {
    setLoading(true);
    try {
      await Promise.all([loadSummary(), loadSuppliers(), loadPRs(), loadPOs(), loadInventory()]);
    } catch (e) {
      toast.error(t('procurement.errors.loadFailed'));
    } finally {
      setLoading(false);
    }
  };

  // Mount: 3 endpoints instead of 5. Suppliers stays eager because PR/PO
  // forms reference the supplier dropdown immediately when opened.
  useEffect(() => {
    setLoading(true);
    Promise.all([loadSummary(), loadSuppliers(), loadPRs()]).catch(() => toast.error(t('procurement.errors.loadFailed'))).finally(() => setLoading(false));
    // eslint-disable-next-line react-hooks/exhaustive-deps -- mevcut davranış korunuyor; toplu temizlik turunda eklendi, niyet inceleme bekliyor
  }, []);

  // Lazy: POs only when the user opens that tab.
  useEffect(() => {
    if (tab === 'pos' && !posLoaded) loadPOs().catch(err => {
      console.error('Load POs failed:', err);
      toast.error('Satınalma siparişleri yüklenemedi');
    });
  }, [tab, posLoaded]);

  // Lazy: credit utilisation report only when user opens that tab.
  useEffect(() => {
    if (tab === 'credit' && !creditReportLoaded) loadCreditReport();
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [tab, creditReportLoaded]);

  // Lazy: inventory list needed by both PR and PO form autocompletes.
  // Boolean dependency prevents per-keystroke re-runs while the form object
  // mutates; the in-flight ref blocks duplicate concurrent fetches.
  const formOpen = !!prForm || !!poForm;
  useEffect(() => {
    if (formOpen && !invLoaded) loadInventory();
  }, [formOpen, invLoaded]);

  // Stok ekranından "Talep Oluştur" ile gelindiğinde formu otomatik aç +
  // Operasyon Komuta Merkezi'nden gelen `initialTab` ile sekme ön-seçimi.
  useEffect(() => {
    const seed = location.state?.newPRItem;
    const initialTab = location.state?.initialTab;
    let consumed = false;
    if (seed) {
      setPrForm({
        department: seed.department || '',
        requester: '',
        urgency: 'normal',
        notes: t('procurement.prModalForm.seedNote', {
          name: seed.name
        }),
        lines: [{
          item_name: seed.name || '',
          sku: seed.sku || '',
          inventory_item_id: seed.id || null,
          quantity: seed.suggested_quantity || Math.max(1, (seed.reorder_level || 0) * 2 - (seed.quantity || 0)),
          unit: seed.unit || 'adet',
          est_unit_cost: seed.unit_cost || 0
        }]
      });
      consumed = true;
    }
    if (initialTab && ['summary', 'pos', 'suppliers'].includes(initialTab)) {
      setTab(initialTab);
      consumed = true;
    }
    if (consumed) {
      navigate(location.pathname, {
        replace: true,
        state: null
      });
    }
    // eslint-disable-next-line react-hooks/exhaustive-deps -- mevcut davranış korunuyor; toplu temizlik turunda eklendi, niyet inceleme bekliyor
  }, [location.state]);
  const inventoryByName = useMemo(() => Object.fromEntries(inventoryItems.map(i => [i.name, i])), [inventoryItems]);
  const fillFromInventory = (lines, idx, value, costKey) => {
    const next = [...lines];
    next[idx] = {
      ...next[idx],
      item_name: value
    };
    const match = inventoryByName[value];
    if (match) {
      next[idx].sku = match.sku || next[idx].sku;
      next[idx].unit = match.unit || next[idx].unit;
      next[idx].inventory_item_id = match.id || match._id || null;
      if (costKey && (!next[idx][costKey] || next[idx][costKey] === 0)) {
        next[idx][costKey] = match.unit_cost || 0;
      }
    }
    return next;
  };
  const supplierMap = useMemo(() => Object.fromEntries(suppliers.map(s => [s.id, s])), [suppliers]);

  // ── Supplier ops ───────────────────────────────────────
  const saveSupplier = async () => {
    try {
      const body = {
        ...supplierForm
      };
      if (!body.name || body.name.length < 2) {
        toast.error(t('procurement.errors.nameRequired'));
        return;
      }
      if (supplierForm.id) {
        await axios.put(`/procurement/suppliers/${supplierForm.id}`, body);
        toast.success(t('procurement.toasts.supplierUpdated'));
      } else {
        await axios.post('/procurement/suppliers', body);
        toast.success(t('procurement.toasts.supplierAdded'));
      }
      setSupplierForm(null);
      refresh();
    } catch (e) {
      toast.error(e.response?.data?.detail || t('procurement.errors.saveFailed'));
    }
  };
  const deleteSupplier = async id => {
    if (!(await confirmDialog({
      message: t('procurement.prompts.confirmDeleteSupplier'),
      variant: 'danger'
    }))) return;
    try {
      await axios.delete(`/procurement/suppliers/${id}`);
      toast.success(t('procurement.toasts.supplierDeleted'));
      refresh();
    } catch (e) {
      toast.error(e.response?.data?.detail || t('procurement.errors.deleteFailed'));
    }
  };

  // ── PR ops ─────────────────────────────────────────────
  // "Aciliyet" seçimini backend'in beklediği `needed_by` tarihine çevirir.
  // Departman fiyat/tarih düşünmek zorunda kalmasın diye kullanıcıya
  // sadece basit bir aciliyet etiketi gösteriyoruz.
  const urgencyToNeededBy = urgency => {
    const days = {
      urgent: 1,
      week: 7,
      month: 30
    }[urgency];
    if (!days) return null; // 'normal' / tanımsız → tarih gönderme
    const d = new Date();
    d.setDate(d.getDate() + days);
    // toISOString UTC'ye çevirip gece yarısı civarı bir gün kaydırabilir;
    // backend `date` beklediği için yerel takvim gününü manuel formatla.
    const yyyy = d.getFullYear();
    const mm = String(d.getMonth() + 1).padStart(2, '0');
    const dd = String(d.getDate()).padStart(2, '0');
    return `${yyyy}-${mm}-${dd}`;
  };
  const savePR = async () => {
    try {
      if (!prForm.department || !prForm.lines?.length) {
        toast.error(t('procurement.errors.departmentLineRequired'));
        return;
      }
      const payload = {
        ...prForm,
        needed_by: urgencyToNeededBy(prForm.urgency)
      };
      delete payload.urgency;
      await axios.post('/procurement/purchase-requests', payload);
      toast.success(t('procurement.toasts.prCreated'));
      setPrForm(null);
      refresh();
    } catch (e) {
      toast.error(e.response?.data?.detail || t('procurement.errors.createFailed'));
    }
  };
  const changePRStatus = async (id, status) => {
    try {
      let reason = null;
      if (status === 'rejected' || status === 'cancelled') {
        const promptKey = status === 'rejected' ? 'procurement.prompts.rejectReason' : 'procurement.prompts.cancelReason';
        reason = await promptDialog({
          message: t(promptKey)
        });
        if (!reason || reason.trim().length < 5) {
          toast.error(t('procurement.errors.reasonMinLen'));
          return;
        }
      }
      await axios.post(`/procurement/purchase-requests/${id}/status`, {
        status,
        reason
      });
      toast.success(t('procurement.toasts.statusUpdated'));
      refresh();
    } catch (e) {
      toast.error(e.response?.data?.detail || t('procurement.errors.updateFailed'));
    }
  };
  const convertPRtoPO = pr => {
    setPoForm({
      supplier_id: '',
      source_pr_id: pr.id,
      currency: 'TRY',
      tax_rate: 20,
      lines: (pr.lines || []).map(l => ({
        item_name: l.item_name,
        sku: l.sku,
        inventory_item_id: l.inventory_item_id,
        quantity: l.quantity,
        unit: l.unit,
        unit_cost: l.est_unit_cost || 0
      }))
    });
  };

  // ── PO credit-utilisation lookup ───────────────────────
  // Projected grand_total for the current PO modal (subtotal * (1 + tax%)).
  const poProjectedTotal = useMemo(() => {
    if (!poForm) return 0;
    const subtotal = (poForm.lines || []).reduce((s, l) => s + (Number(l.quantity) || 0) * (Number(l.unit_cost) || 0), 0);
    const taxRate = Number(poForm.tax_rate) || 0;
    return Math.round(subtotal * (1 + taxRate / 100) * 100) / 100;
  }, [poForm]);
  useEffect(() => {
    if (!poForm || !poForm.supplier_id) {
      setCreditUtil(null);
      return;
    }
    const reqId = ++creditReqRef.current;
    const supplierId = poForm.supplier_id;
    const projected = poProjectedTotal;
    const handle = setTimeout(async () => {
      try {
        const r = await axios.get(`/procurement/suppliers/${supplierId}/credit-utilisation`, {
          params: {
            projected_amount: projected
          }
        });
        if (creditReqRef.current === reqId) setCreditUtil(r.data);
      } catch {
        if (creditReqRef.current === reqId) setCreditUtil(null);
      }
    }, 250);
    return () => clearTimeout(handle);
  }, [poForm?.supplier_id, poProjectedTotal, poForm]);

  // ── PO ops ─────────────────────────────────────────────
  const savePO = async () => {
    try {
      if (!poForm.supplier_id || !poForm.lines?.length) {
        toast.error(t('procurement.errors.supplierLineRequired'));
        return;
      }
      await axios.post('/procurement/purchase-orders', poForm);
      toast.success(t('procurement.toasts.poCreated'));
      setPoForm(null);
      refresh();
    } catch (e) {
      toast.error(e.response?.data?.detail || t('procurement.errors.createFailed'));
    }
  };
  const changePOStatus = async (id, status) => {
    try {
      let reason = null;
      if (status === 'cancelled') {
        reason = await promptDialog({
          message: t('procurement.prompts.cancelReason')
        });
        if (!reason || reason.trim().length < 5) {
          toast.error(t('procurement.errors.reasonMinLen'));
          return;
        }
      }
      await axios.post(`/procurement/purchase-orders/${id}/status`, {
        status,
        reason
      });
      toast.success(t('procurement.toasts.statusUpdated'));
      refresh();
      if (selectedPo?.id === id) openPo(id);
    } catch (e) {
      toast.error(e.response?.data?.detail || t('procurement.errors.updateFailed'));
    }
  };
  const openPo = async id => {
    try {
      const r = await axios.get(`/procurement/purchase-orders/${id}`);
      setSelectedPo(r.data);
    } catch {
      toast.error(t('procurement.errors.poLoadFailed'));
    }
  };

  // ── GRN ops ────────────────────────────────────────────
  const openGrnForm = po => {
    setGrnForm({
      po,
      notes: '',
      lines: (po.lines || []).map((l, i) => ({
        po_line_idx: i,
        item_name: l.item_name,
        ordered: l.quantity,
        already: l.received_qty || 0,
        received_qty: Math.max(0, (l.quantity || 0) - (l.received_qty || 0)),
        qc_status: 'accepted',
        notes: ''
      }))
    });
  };
  const saveGRN = async () => {
    try {
      const lines = grnForm.lines.filter(l => Number(l.received_qty) > 0).map(l => ({
        po_line_idx: l.po_line_idx,
        received_qty: Number(l.received_qty),
        qc_status: l.qc_status,
        notes: l.notes
      }));
      if (!lines.length) {
        toast.error(t('procurement.errors.leastOneQty'));
        return;
      }
      const r = await axios.post(`/procurement/purchase-orders/${grnForm.po.id}/grn`, {
        notes: grnForm.notes,
        lines
      });
      toast.success(t('procurement.toasts.grnCreated', {
        no: r.data.grn?.grn_no,
        status: r.data.po_status
      }));
      setGrnForm(null);
      refresh();
      if (selectedPo?.id === grnForm.po.id) openPo(grnForm.po.id);
    } catch (e) {
      toast.error(e.response?.data?.detail || t('procurement.errors.grnFailed'));
    }
  };
  return <>
    <div className="p-6 max-w-7xl mx-auto space-y-4">
      <div className="flex items-center justify-between">
        <div>
          <h1 className="text-2xl font-bold flex items-center gap-2">
            <Truck className="w-6 h-6" /> {t('procurement.header.title')}
          </h1>
          <p className="text-sm text-slate-600">
            {t('procurement.header.subtitle')}
          </p>
        </div>
        <Button onClick={refresh} variant="outline" disabled={loading}>
          <RefreshCw className={`w-4 h-4 mr-1 ${loading ? 'animate-spin' : ''}`} />
          {t('procurement.header.refresh')}
        </Button>
      </div>

      {/* Summary cards */}
      <div className="grid grid-cols-2 md:grid-cols-6 gap-3">
        {[[t('procurement.summary.activeSuppliers'), summary.suppliers_active ?? 0], [t('procurement.summary.pendingPR'), summary.pr_pending ?? 0], [t('procurement.summary.approvedPR'), summary.pr_approved ?? 0], [t('procurement.summary.openPO'), summary.po_open ?? 0], [t('procurement.summary.completedPO'), summary.po_received ?? 0], [t('procurement.summary.openAmount'), tl(summary.open_commitment_value)]].map(([k, v]) => <Card key={k}><CardContent className="p-3">
            <div className="text-xs text-slate-500">{k}</div>
            <div className="text-lg font-semibold mt-1">{v}</div>
          </CardContent></Card>)}
      </div>

      {/* Suppliers near credit limit (utilization ≥ 80% or over-limit) */}
      {(() => {
        const atRisk = suppliers.map(s => {
          const limit = s.credit_limit;
          const hasLimit = limit !== null && limit !== undefined && limit !== '';
          const limitNum = hasLimit ? Number(limit) : null;
          if (!hasLimit || !(limitNum > 0)) return null;
          const open = Number(s.open_commitment || 0);
          const pct = open / limitNum * 100;
          if (pct < 80) return null;
          return {
            id: s.id,
            name: s.name,
            code: s.code,
            open,
            limit: limitNum,
            pct
          };
        }).filter(Boolean).sort((a, b) => b.pct - a.pct).slice(0, 5);
        return <Card>
            <CardHeader className="pb-2">
              <CardTitle className="text-base">{t('procurement.creditWatch.title')}</CardTitle>
              <CardDescription>{t('procurement.creditWatch.description')}</CardDescription>
            </CardHeader>
            <CardContent>
              {atRisk.length === 0 ? <div className="text-sm text-slate-400 py-2">{t('procurement.creditWatch.empty')}</div> : <ul className="divide-y">
                  {atRisk.map(s => {
                const over = s.pct > 100;
                const toneText = over ? 'text-rose-700' : 'text-amber-700';
                const toneBar = over ? 'bg-rose-500' : 'bg-amber-500';
                const toneBg = over ? 'bg-rose-50' : '';
                return <li key={s.id} className={`py-2 px-2 ${toneBg}`}>
                        <div className="flex items-center justify-between gap-3">
                          <div className="min-w-0">
                            <div className="font-medium truncate">{s.name}</div>
                            {s.code && <div className="text-xs text-slate-500 font-mono">{s.code}</div>}
                          </div>
                          <div className="text-right shrink-0">
                            <div className={`text-sm font-semibold tabular-nums ${toneText}`}>
                              {s.pct.toFixed(0)}%
                              {over && <Badge className="ml-2 bg-rose-100 text-rose-800 border-0">{t('procurement.creditWatch.overLimit')}</Badge>}
                            </div>
                            <div className="text-xs text-slate-600 tabular-nums">
                              {s.open.toLocaleString()} / {s.limit.toLocaleString()}
                            </div>
                          </div>
                        </div>
                        <div className="mt-1 h-1.5 w-full bg-slate-100 rounded">
                          <div className={`h-1.5 rounded ${toneBar}`} style={{
                      width: `${Math.min(100, s.pct)}%`
                    }} />
                        </div>
                      </li>;
              })}
                </ul>}
            </CardContent>
          </Card>;
      })()}

      <Tabs value={tab} onValueChange={setTab}>
        <TabsList>
          <TabsTrigger value="summary"><ClipboardList className="w-4 h-4 mr-1" />{t('procurement.tabs.prs')}</TabsTrigger>
          <TabsTrigger value="pos"><Package className="w-4 h-4 mr-1" />{t('procurement.tabs.pos')}</TabsTrigger>
          <TabsTrigger value="suppliers"><Truck className="w-4 h-4 mr-1" />{t('procurement.tabs.suppliers')}</TabsTrigger>
          <TabsTrigger value="credit"><TrendingUp className="w-4 h-4 mr-1" />{t('procurement.tabs.credit')}</TabsTrigger>
          <TabsTrigger value="b2b"><FileCheck2 className="w-4 h-4 mr-1" />B2B Otomatik Sipariş</TabsTrigger>
        </TabsList>

        <TabsContent value="b2b">
          <ProcurementB2BTab />
        </TabsContent>

        {/* ── PR LIST ─────────────────────────────────────── */}
        <TabsContent value="summary">
          <Card>
            <CardHeader className="flex-row items-center justify-between">
              <div>
                <CardTitle>{t('procurement.prList.title')}</CardTitle>
                <CardDescription>{t('procurement.prList.description')}</CardDescription>
              </div>
              <Button onClick={() => setPrForm({
                department: '',
                requester: '',
                urgency: 'normal',
                notes: '',
                lines: [{
                  item_name: '',
                  quantity: 1,
                  unit: 'adet',
                  est_unit_cost: 0
                }]
              })}>
                <Plus className="w-4 h-4 mr-1" /> {t('procurement.prList.newPR')}
              </Button>
            </CardHeader>
            <CardContent>
              <table className="w-full text-sm">
                <thead><tr className="text-left border-b text-slate-600">
                  <th className="p-2">{t('procurement.prList.columns.no')}</th>
                  <th className="p-2">{t('procurement.prList.columns.department')}</th>
                  <th className="p-2">{t('procurement.prList.columns.requester')}</th>
                  <th className="p-2">{t('procurement.prList.columns.items')}</th>
                  <th className="p-2 text-right">{t('procurement.prList.columns.estimated')}</th>
                  <th className="p-2">{t('procurement.prList.columns.status')}</th>
                  <th className="p-2 text-right">{t('procurement.prList.columns.action')}</th>
                </tr></thead>
                <tbody>
                  {prs.map(pr => {
                    const cls = PR_STATUS_CLS[pr.status] || PR_STATUS_CLS.draft;
                    return <tr key={pr.id} className="border-b hover:bg-slate-50">
                        <td className="p-2 font-mono text-xs">{pr.pr_no}</td>
                        <td className="p-2">{pr.department}</td>
                        <td className="p-2 text-xs text-slate-600">{pr.requester}</td>
                        <td className="p-2">{pr.lines?.length || 0}</td>
                        <td className="p-2 text-right">{tl(pr.lines_total)}</td>
                        <td className="p-2"><Badge className={`${cls} border-0`}>{prLabel(pr.status)}</Badge></td>
                        <td className="p-2 text-right space-x-1 whitespace-nowrap">
                          {pr.status === 'draft' && <Button size="sm" variant="outline" onClick={() => changePRStatus(pr.id, 'submitted')}><Send className="w-3.5 h-3.5 mr-1" />{t('procurement.prList.actions.send')}</Button>}
                          {pr.status === 'submitted' && <>
                            {canApprovePR && !isOwnPR(pr) && <>
                              <Button size="sm" variant="outline" className="border-emerald-300 text-emerald-700 hover:bg-emerald-50" onClick={() => changePRStatus(pr.id, 'approved')}><Check className="w-3.5 h-3.5 mr-1" />{t('procurement.prList.actions.approve')}</Button>
                              <Button size="sm" variant="outline" className="border-rose-300 text-rose-700 hover:bg-rose-50" onClick={() => changePRStatus(pr.id, 'rejected')}><X className="w-3.5 h-3.5 mr-1" />{t('procurement.prList.actions.reject')}</Button>
                            </>}
                            {(canApprovePR || isOwnPR(pr)) && <Button size="sm" variant="outline" onClick={() => changePRStatus(pr.id, 'cancelled')}><Ban className="w-3.5 h-3.5 mr-1" />{t('procurement.prList.actions.cancel')}</Button>}
                          </>}
                          {pr.status === 'approved' && <>
                            {canApprovePR && <Button size="sm" onClick={() => convertPRtoPO(pr)}>{t('procurement.prList.actions.convertToPo')}</Button>}
                            {canApprovePR && <Button size="sm" variant="outline" onClick={() => changePRStatus(pr.id, 'cancelled')}><Ban className="w-3.5 h-3.5 mr-1" />{t('procurement.prList.actions.cancel')}</Button>}
                          </>}
                          <Button size="sm" variant="ghost" title={t('procurement.prList.actions.history')} onClick={() => setHistory({
                          type: 'proc_pr',
                          id: pr.id,
                          title: pr.pr_no
                        })}>
                            <HistoryIcon className="w-4 h-4" />
                          </Button>
                        </td>
                      </tr>;
                  })}
                  {prs.length === 0 && <tr><td colSpan="7" className="p-4 text-center text-slate-400">{t('procurement.prList.empty')}</td></tr>}
                </tbody>
              </table>
            </CardContent>
          </Card>
        </TabsContent>

        {/* ── PO LIST ─────────────────────────────────────── */}
        <TabsContent value="pos">
          <Card>
            <CardHeader className="flex-row items-center justify-between">
              <div>
                <CardTitle>{t('procurement.poList.title')}</CardTitle>
                <CardDescription>{t('procurement.poList.description')}</CardDescription>
              </div>
              <Button onClick={() => setPoForm({
                supplier_id: '',
                currency: 'TRY',
                tax_rate: 20,
                lines: [{
                  item_name: '',
                  quantity: 1,
                  unit: 'adet',
                  unit_cost: 0
                }]
              })}>
                <Plus className="w-4 h-4 mr-1" /> {t('procurement.poList.newPO')}
              </Button>
            </CardHeader>
            <CardContent>
              <table className="w-full text-sm">
                <thead><tr className="text-left border-b text-slate-600">
                  <th className="p-2">{t('procurement.poList.columns.no')}</th>
                  <th className="p-2">{t('procurement.poList.columns.supplier')}</th>
                  <th className="p-2">{t('procurement.poList.columns.items')}</th>
                  <th className="p-2 text-right">{t('procurement.poList.columns.amount')}</th>
                  <th className="p-2">{t('procurement.poList.columns.status')}</th>
                  <th className="p-2 text-right">{t('procurement.poList.columns.action')}</th>
                </tr></thead>
                <tbody>
                  {pos.map(po => {
                    const cls = PO_STATUS_CLS[po.status] || PO_STATUS_CLS.draft;
                    return <tr key={po.id} className="border-b hover:bg-slate-50">
                        <td className="p-2 font-mono text-xs">{po.po_no}</td>
                        <td className="p-2">{po.supplier_name}</td>
                        <td className="p-2">{po.lines?.length || 0}</td>
                        <td className="p-2 text-right">{tl(po.grand_total)}</td>
                        <td className="p-2"><Badge className={`${cls} border-0`}>{poLabel(po.status)}</Badge></td>
                        <td className="p-2 text-right space-x-1 whitespace-nowrap">
                          <Button size="sm" variant="ghost" onClick={() => openPo(po.id)}>{t('procurement.poList.actions.details')}</Button>
                          {po.status === 'draft' && <Button size="sm" onClick={() => changePOStatus(po.id, 'sent')}>
                              <Send className="w-3 h-3 mr-1" />{t('procurement.poList.actions.send')}
                            </Button>}
                          {(po.status === 'sent' || po.status === 'partially_received') && <Button size="sm" onClick={() => openGrnForm(po)}>
                              <FileCheck2 className="w-3 h-3 mr-1" />{t('procurement.poList.actions.receiveGoods')}
                            </Button>}
                          {(po.status === 'draft' || po.status === 'sent') && <Button size="sm" variant="ghost" onClick={() => changePOStatus(po.id, 'cancelled')}>{t('procurement.poList.actions.cancel')}</Button>}
                          {po.status === 'received' && <Button size="sm" variant="ghost" onClick={() => changePOStatus(po.id, 'closed')}>{t('procurement.poList.actions.close')}</Button>}
                          <Button size="sm" variant="ghost" title={t('procurement.poList.actions.history')} onClick={() => setHistory({
                          type: 'proc_po',
                          id: po.id,
                          title: po.po_no
                        })}>
                            <HistoryIcon className="w-4 h-4" />
                          </Button>
                        </td>
                      </tr>;
                  })}
                  {pos.length === 0 && <tr><td colSpan="6" className="p-4 text-center text-slate-400">{t('procurement.poList.empty')}</td></tr>}
                </tbody>
              </table>
            </CardContent>
          </Card>
        </TabsContent>

        {/* ── SUPPLIERS ───────────────────────────────────── */}
        <TabsContent value="suppliers">
          <Card>
            <CardHeader className="flex-row items-center justify-between">
              <div>
                <CardTitle>{t('procurement.supplierList.title')}</CardTitle>
                <CardDescription>{t('procurement.supplierList.description')}</CardDescription>
              </div>
              <Button onClick={() => setSupplierForm({
                name: '',
                code: '',
                tax_no: '',
                contact_name: '',
                email: '',
                phone: '',
                address: '',
                payment_terms_days: 30,
                credit_limit: '',
                categories: [],
                notes: '',
                active: true
              })}>
                <Plus className="w-4 h-4 mr-1" /> {t('procurement.supplierList.newSupplier')}
              </Button>
            </CardHeader>
            <CardContent>
              <table className="w-full text-sm">
                <thead><tr className="text-left border-b text-slate-600">
                  <th className="p-2">{t('procurement.supplierList.columns.code')}</th>
                  <th className="p-2">{t('procurement.supplierList.columns.name')}</th>
                  <th className="p-2">{t('procurement.supplierList.columns.taxNo')}</th>
                  <th className="p-2">{t('procurement.supplierList.columns.contact')}</th>
                  <th className="p-2 text-right">{t('procurement.supplierList.columns.paymentDays')}</th>
                  <th className="p-2 text-right">{t('procurement.supplierList.columns.creditLimit')}</th>
                  <th className="p-2">{t('procurement.supplierList.columns.status')}</th>
                  <th className="p-2 text-right">{t('procurement.supplierList.columns.action')}</th>
                </tr></thead>
                <tbody>
                  {suppliers.map(s => {
                    const limit = s.credit_limit;
                    const open = Number(s.open_commitment || 0);
                    const hasLimit = limit !== null && limit !== undefined && limit !== '';
                    const limitNum = hasLimit ? Number(limit) : null;
                    const headroom = hasLimit ? limitNum - open : null;
                    const pct = hasLimit && limitNum > 0 ? Math.min(100, open / limitNum * 100) : 0;
                    const tone = !hasLimit ? 'text-slate-400' : headroom < 0 ? 'text-rose-700' : pct >= 80 ? 'text-amber-700' : 'text-slate-700';
                    return <tr key={s.id} className="border-b hover:bg-slate-50">
                      <td className="p-2 font-mono text-xs">{s.code || '—'}</td>
                      <td className="p-2 font-medium">{s.name}</td>
                      <td className="p-2 text-xs">{s.tax_no || '—'}</td>
                      <td className="p-2 text-xs">{s.contact_name || s.email || s.phone || '—'}</td>
                      <td className="p-2 text-right">{s.payment_terms_days} {t('procurement.supplierList.daysSuffix')}</td>
                      <td className={`p-2 text-right tabular-nums ${tone}`}>
                        {hasLimit ? <span title={t('procurement.supplierList.openCommitmentTooltip', {
                          open: open.toLocaleString(),
                          limit: limitNum.toLocaleString()
                        })}>
                            {open.toLocaleString()} / {limitNum.toLocaleString()}
                          </span> : <span>—</span>}
                      </td>
                      <td className="p-2">
                        <Badge className={s.active ? 'bg-emerald-100 text-emerald-800 border-0' : 'bg-slate-200 text-slate-600 border-0'}>
                          {s.active ? t('procurement.supplierList.active') : t('procurement.supplierList.inactive')}
                        </Badge>
                      </td>
                      <td className="p-2 text-right space-x-1">
                        <Button size="sm" variant="ghost" onClick={() => setSupplierForm(s)}>{t('procurement.supplierList.edit')}</Button>
                        <Button size="sm" variant="ghost" onClick={() => deleteSupplier(s.id)}>
                          <Trash2 className="w-4 h-4" />
                        </Button>
                      </td>
                    </tr>;
                  })}
                  {suppliers.length === 0 && <tr><td colSpan="8" className="p-4 text-center text-slate-400">{t('procurement.supplierList.empty')}</td></tr>}
                </tbody>
              </table>
            </CardContent>
          </Card>
        </TabsContent>

        {/* ── CREDIT UTILISATION REPORT (Task #79) ───────── */}
        <TabsContent value="credit">
          <Card>
            <CardHeader className="flex-row items-center justify-between gap-2">
              <div>
                <CardTitle>{t('procurement.creditReport.title')}</CardTitle>
                <CardDescription>{t('procurement.creditReport.description')}</CardDescription>
              </div>
              <div className="flex items-center gap-3">
                <label className="text-xs text-slate-600 flex items-center gap-1">
                  <input type="checkbox" checked={creditIncludeUnlimited} onChange={e => {
                    const v = e.target.checked;
                    setCreditIncludeUnlimited(v);
                    loadCreditReport(v);
                  }} />
                  {t('procurement.creditReport.includeUnlimited')}
                </label>
                <Button size="sm" variant="outline" onClick={() => loadCreditReport()} disabled={creditReportLoading}>
                  <RefreshCw className={`w-4 h-4 mr-1 ${creditReportLoading ? 'animate-spin' : ''}`} />
                  {t('procurement.creditReport.refresh')}
                </Button>
              </div>
            </CardHeader>
            <CardContent>
              <table className="w-full text-sm">
                <thead><tr className="text-left border-b text-slate-600">
                  <th className="p-2">{t('procurement.creditReport.columns.code')}</th>
                  <th className="p-2">{t('procurement.creditReport.columns.supplier')}</th>
                  <th className="p-2 text-right">{t('procurement.creditReport.columns.open')}</th>
                  <th className="p-2 text-right">{t('procurement.creditReport.columns.limit')}</th>
                  <th className="p-2 text-right">{t('procurement.creditReport.columns.headroom')}</th>
                  <th className="p-2 text-right">{t('procurement.creditReport.columns.usedPct')}</th>
                  <th className="p-2">{t('procurement.creditReport.columns.status')}</th>
                </tr></thead>
                <tbody>
                  {creditReport.map(row => {
                    const cls = row.status === 'exceeded' ? 'bg-rose-100 text-rose-800' : row.status === 'warning' ? 'bg-amber-100 text-amber-800' : row.status === 'ok' ? 'bg-emerald-100 text-emerald-800' : 'bg-slate-100 text-slate-600';
                    const tone = row.status === 'exceeded' ? 'text-rose-700' : row.status === 'warning' ? 'text-amber-700' : 'text-slate-700';
                    return <tr key={row.supplier_id} className="border-b hover:bg-slate-50">
                        <td className="p-2 font-mono text-xs">{row.supplier_code || '—'}</td>
                        <td className="p-2 font-medium">{row.supplier_name}</td>
                        <td className={`p-2 text-right tabular-nums ${tone}`}>{tl(row.open_total)}</td>
                        <td className="p-2 text-right tabular-nums">
                          {row.limit === null ? '—' : tl(row.limit)}
                        </td>
                        <td className={`p-2 text-right tabular-nums ${tone}`}>
                          {row.headroom === null ? '—' : tl(row.headroom)}
                        </td>
                        <td className={`p-2 text-right tabular-nums ${tone}`}>
                          {row.used_pct === null ? '—' : `${row.used_pct.toFixed(1)}%`}
                        </td>
                        <td className="p-2">
                          <Badge className={`${cls} border-0`}>
                            {t(`procurement.creditReport.statuses.${row.status}`)}
                          </Badge>
                        </td>
                      </tr>;
                  })}
                  {creditReport.length === 0 && <tr><td colSpan="7" className="p-4 text-center text-slate-400">
                      {creditReportLoading ? t('procurement.creditReport.loading') : t('procurement.creditReport.empty')}
                    </td></tr>}
                </tbody>
              </table>
            </CardContent>
          </Card>
        </TabsContent>
      </Tabs>

      {/* ── Supplier Modal ─────────────────────────────── */}
      {supplierForm && <Modal title={supplierForm.id ? t('procurement.supplierModal.titleEdit') : t('procurement.supplierModal.titleNew')} onClose={() => setSupplierForm(null)}>
          <div className="grid grid-cols-2 gap-3">
            <div><Label>{t('procurement.supplierModal.name')}</Label>
              <Input value={supplierForm.name || ''} onChange={e => setSupplierForm({
              ...supplierForm,
              name: e.target.value
            })} /></div>
            <div><Label>{t('procurement.supplierModal.code')}</Label>
              <Input value={supplierForm.code || ''} onChange={e => setSupplierForm({
              ...supplierForm,
              code: e.target.value
            })} /></div>
            <div><Label>{t('procurement.supplierModal.taxNo')}</Label>
              <Input value={supplierForm.tax_no || ''} onChange={e => setSupplierForm({
              ...supplierForm,
              tax_no: e.target.value
            })} /></div>
            <div><Label>{t('procurement.supplierModal.contact')}</Label>
              <Input value={supplierForm.contact_name || ''} onChange={e => setSupplierForm({
              ...supplierForm,
              contact_name: e.target.value
            })} /></div>
            <div><Label>{t('procurement.supplierModal.email')}</Label>
              <Input value={supplierForm.email || ''} onChange={e => setSupplierForm({
              ...supplierForm,
              email: e.target.value
            })} /></div>
            <div><Label>{t('procurement.supplierModal.phone')}</Label>
              <Input value={supplierForm.phone || ''} onChange={e => setSupplierForm({
              ...supplierForm,
              phone: e.target.value
            })} /></div>
            <div className="col-span-2"><Label>{t('procurement.supplierModal.address')}</Label>
              <Input value={supplierForm.address || ''} onChange={e => setSupplierForm({
              ...supplierForm,
              address: e.target.value
            })} /></div>
            <div><Label>{t('procurement.supplierModal.paymentTerms')}</Label>
              <Input type="number" value={supplierForm.payment_terms_days || 30} onChange={e => setSupplierForm({
              ...supplierForm,
              payment_terms_days: Number(e.target.value)
            })} /></div>
            <div><Label>{t('procurement.supplierModal.creditLimit')}</Label>
              <Input type="number" min="0" step="0.01" placeholder={t('procurement.supplierModal.creditLimitPlaceholder')} value={supplierForm.credit_limit ?? ''} onChange={e => {
              const v = e.target.value;
              setSupplierForm({
                ...supplierForm,
                credit_limit: v === '' ? null : Number(v)
              });
            }} />
              <p className="text-xs text-slate-500 mt-1">{t('procurement.supplierModal.creditLimitHelp')}</p>
            </div>
            <div><Label>{t('procurement.supplierModal.categories')}</Label>
              <Input value={(supplierForm.categories || []).join(', ')} onChange={e => setSupplierForm({
              ...supplierForm,
              categories: e.target.value.split(',').map(s => s.trim()).filter(Boolean)
            })} /></div>
            <div className="col-span-2 flex items-center gap-2">
              <input type="checkbox" id="sf-active" checked={!!supplierForm.active} onChange={e => setSupplierForm({
              ...supplierForm,
              active: e.target.checked
            })} />
              <label htmlFor="sf-active" className="text-sm">{t('procurement.supplierModal.active')}</label>
            </div>
            <div className="col-span-2"><Label>{t('procurement.supplierModal.notes')}</Label>
              <Input value={supplierForm.notes || ''} onChange={e => setSupplierForm({
              ...supplierForm,
              notes: e.target.value
            })} /></div>
          </div>
          <div className="mt-4 text-right space-x-2">
            <Button variant="outline" onClick={() => setSupplierForm(null)}>{t('procurement.supplierModal.cancel')}</Button>
            <Button onClick={saveSupplier}>{t('procurement.supplierModal.save')}</Button>
          </div>
        </Modal>}

      {/* ── PR Modal ─────────────────────────────────── */}
      {prForm && <Modal title={t('procurement.prModalForm.title')} onClose={() => setPrForm(null)} wide>
          <div className="grid grid-cols-2 gap-3">
            <div><Label>{t('procurement.prModalForm.department')}</Label>
              <select value={prForm.department || ''} onChange={e => setPrForm({
              ...prForm,
              department: e.target.value
            })} className="flex h-10 w-full rounded-md border border-input bg-background px-3 py-2 text-sm ring-offset-background focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-ring focus-visible:ring-offset-2">
                <option value="">{t('procurement.prModal.departmentSelectPlaceholder')}</option>
                <option value="Kat Hizmetleri">{t('procurement.prModal.departments.housekeeping')}</option>
                <option value="F&B">{t('procurement.prModal.departments.fnb')}</option>
                <option value="Teknik">{t('procurement.prModal.departments.engineering')}</option>
                <option value="Ön Büro">{t('procurement.prModal.departments.frontOffice')}</option>
                <option value="Bakım">{t('procurement.prModal.departments.maintenance')}</option>
                <option value="Güvenlik">{t('procurement.prModal.departments.security')}</option>
                <option value="Yönetim">{t('procurement.prModal.departments.administration')}</option>
                <option value="Diğer">{t('procurement.prModal.departments.other')}</option>
              </select>
            </div>
            <div><Label>{t('procurement.prModalForm.requester')}</Label>
              <Input value={prForm.requester || ''} onChange={e => setPrForm({
              ...prForm,
              requester: e.target.value
            })} /></div>
            <div><Label>{t('procurement.prModalForm.urgency')}</Label>
              <select value={prForm.urgency || 'normal'} onChange={e => setPrForm({
              ...prForm,
              urgency: e.target.value
            })} className="flex h-10 w-full rounded-md border border-input bg-background px-3 py-2 text-sm ring-offset-background focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-ring focus-visible:ring-offset-2">
                <option value="normal">{t('procurement.prModalForm.urgencyNormal')}</option>
                <option value="month">{t('procurement.prModalForm.urgencyMonth')}</option>
                <option value="week">{t('procurement.prModalForm.urgencyWeek')}</option>
                <option value="urgent">{t('procurement.prModalForm.urgencyUrgent')}</option>
              </select>
            </div>
            <div className="col-span-2"><Label>{t('procurement.prModalForm.notes')}</Label>
              <Input value={prForm.notes || ''} onChange={e => setPrForm({
              ...prForm,
              notes: e.target.value
            })} /></div>
          </div>
          <div className="mt-4">
            <div className="flex items-center justify-between mb-2">
              <h3 className="font-semibold text-sm">{t('procurement.prModalForm.items')}</h3>
              <Button size="sm" variant="outline" onClick={() => setPrForm({
              ...prForm,
              lines: [...prForm.lines, {
                item_name: '',
                quantity: 1,
                unit: 'adet',
                est_unit_cost: 0
              }]
            })}><Plus className="w-3 h-3 mr-1" /> {t('procurement.prModalForm.addItem')}</Button>
            </div>
            <table className="w-full text-sm">
              <thead><tr className="border-b text-left text-slate-600">
                <th className="p-1">{t('procurement.prModalForm.itemHeader')}</th>
                <th className="p-1">{t('procurement.prModalForm.skuHeader')}</th>
                <th className="p-1 w-20">{t('procurement.prModalForm.qtyHeader')}</th>
                <th className="p-1 w-20">{t('procurement.prModalForm.unitHeader')}</th>
                <th className="p-1"></th>
              </tr></thead>
              <tbody>
                {prForm.lines.map((l, i) => <tr key={l.id || i}>
                    <td className="p-1">
                      <Input value={l.item_name} list="inv-items-pr" placeholder={t('procurement.prModalForm.itemPlaceholder')} onChange={e => setPrForm({
                    ...prForm,
                    lines: fillFromInventory(prForm.lines, i, e.target.value, 'est_unit_cost')
                  })} />
                    </td>
                    <td className="p-1"><Input value={l.sku || ''} onChange={e => {
                    const lines = [...prForm.lines];
                    lines[i].sku = e.target.value;
                    setPrForm({
                      ...prForm,
                      lines
                    });
                  }} /></td>
                    <td className="p-1"><Input type="number" value={l.quantity} onChange={e => {
                    const lines = [...prForm.lines];
                    lines[i].quantity = Number(e.target.value);
                    setPrForm({
                      ...prForm,
                      lines
                    });
                  }} /></td>
                    <td className="p-1"><Input value={l.unit} onChange={e => {
                    const lines = [...prForm.lines];
                    lines[i].unit = e.target.value;
                    setPrForm({
                      ...prForm,
                      lines
                    });
                  }} /></td>
                    <td className="p-1"><Button size="sm" variant="ghost" onClick={() => setPrForm({
                    ...prForm,
                    lines: prForm.lines.filter((_, j) => j !== i)
                  })}><Trash2 className="w-4 h-4" /></Button></td>
                  </tr>)}
              </tbody>
            </table>
            <datalist id="inv-items-pr">
              {inventoryItems.map(it => <option key={it.id || it._id || it.name} value={it.name}>
                  {it.sku ? `${it.sku} · ` : ''}{t('procurement.prModalForm.datalistAvailable')}: {it.quantity} {it.unit}
                </option>)}
            </datalist>
            {inventoryItems.length > 0 && <p className="text-xs text-slate-500 mt-2">
                {t('procurement.prModalForm.hint')}
              </p>}
          </div>
          <div className="mt-4 text-right space-x-2">
            <Button variant="outline" onClick={() => setPrForm(null)}>{t('procurement.prModalForm.cancel')}</Button>
            <Button onClick={savePR}>{t('procurement.prModalForm.create')}</Button>
          </div>
        </Modal>}

      {/* ── PO Modal ─────────────────────────────────── */}
      {poForm && <Modal title={poForm.source_pr_id ? t('procurement.poModal.titleFromPR') : t('procurement.poModal.titleNew')} onClose={() => setPoForm(null)} wide>
          <div className="grid grid-cols-3 gap-3">
            <div><Label>{t('procurement.poModal.supplier')}</Label>
              <select className="w-full border rounded p-2" value={poForm.supplier_id} onChange={e => setPoForm({
              ...poForm,
              supplier_id: e.target.value
            })}>
                <option value="">{t('procurement.poModal.supplierSelect')}</option>
                {suppliers.filter(s => s.active).map(s => {
                const cl = s.credit_limit;
                const label = cl !== null && cl !== undefined ? t('procurement.poModal.supplierOptionCredit', {
                  name: s.name,
                  limit: tl(cl)
                }) : s.name;
                return <option key={s.id} value={s.id}>{label}</option>;
              })}
              </select>
              {creditUtil && creditUtil.limit !== null && <div className="text-xs text-slate-500 mt-1">
                  {t('procurement.poModal.creditHeadroom', {
                headroom: tl(creditUtil.headroom),
                limit: tl(creditUtil.limit)
              })}
                </div>}
            </div>
            <div><Label>{t('procurement.poModal.expectedDelivery')}</Label>
              <Input type="date" value={poForm.expected_delivery || ''} onChange={e => setPoForm({
              ...poForm,
              expected_delivery: e.target.value || null
            })} /></div>
            <div><Label>{t('procurement.poModal.taxRate')}</Label>
              <Input type="number" value={poForm.tax_rate} onChange={e => setPoForm({
              ...poForm,
              tax_rate: Number(e.target.value)
            })} /></div>
          </div>
          {creditUtil && creditUtil.warning && creditUtil.limit !== null && <div className={`mt-3 rounded border px-3 py-2 text-sm ${creditUtil.exceeded ? 'border-rose-300 bg-rose-50 text-rose-800' : 'border-amber-300 bg-amber-50 text-amber-800'}`}>
              <div className="font-semibold">
                {creditUtil.exceeded ? t('procurement.poModal.creditExceededTitle') : t('procurement.poModal.creditWarnTitle', {
              pct: creditUtil.used_pct
            })}
              </div>
              <div className="text-xs mt-0.5">
                {t('procurement.poModal.creditWarnDetail', {
              open: tl(creditUtil.open_total),
              projected: tl(creditUtil.projected_amount),
              total: tl(creditUtil.projected_total),
              limit: tl(creditUtil.limit)
            })}
              </div>
            </div>}
          <div className="mt-4">
            <div className="flex items-center justify-between mb-2">
              <h3 className="font-semibold text-sm">{t('procurement.poModal.items')}</h3>
              <Button size="sm" variant="outline" onClick={() => setPoForm({
              ...poForm,
              lines: [...poForm.lines, {
                item_name: '',
                quantity: 1,
                unit: 'adet',
                unit_cost: 0
              }]
            })}><Plus className="w-3 h-3 mr-1" /> {t('procurement.poModal.addItem')}</Button>
            </div>
            <table className="w-full text-sm">
              <thead><tr className="border-b text-left text-slate-600">
                <th className="p-1">{t('procurement.poModal.itemHeader')}</th>
                <th className="p-1">{t('procurement.poModal.skuHeader')}</th>
                <th className="p-1 w-20">{t('procurement.poModal.qtyHeader')}</th>
                <th className="p-1 w-20">{t('procurement.poModal.unitHeader')}</th>
                <th className="p-1 w-24">{t('procurement.poModal.unitPriceHeader')}</th>
                <th className="p-1 w-24 text-right">{t('procurement.poModal.totalHeader')}</th>
                <th className="p-1"></th>
              </tr></thead>
              <tbody>
                {poForm.lines.map((l, i) => <tr key={l.id || i}>
                    <td className="p-1">
                      <Input value={l.item_name} list="inv-items-po" placeholder={t('procurement.poModal.itemPlaceholder')} onChange={e => setPoForm({
                    ...poForm,
                    lines: fillFromInventory(poForm.lines, i, e.target.value, 'unit_cost')
                  })} />
                    </td>
                    <td className="p-1"><Input value={l.sku || ''} onChange={e => {
                    const lines = [...poForm.lines];
                    lines[i].sku = e.target.value;
                    setPoForm({
                      ...poForm,
                      lines
                    });
                  }} /></td>
                    <td className="p-1"><Input type="number" value={l.quantity} onChange={e => {
                    const lines = [...poForm.lines];
                    lines[i].quantity = Number(e.target.value);
                    setPoForm({
                      ...poForm,
                      lines
                    });
                  }} /></td>
                    <td className="p-1"><Input value={l.unit} onChange={e => {
                    const lines = [...poForm.lines];
                    lines[i].unit = e.target.value;
                    setPoForm({
                      ...poForm,
                      lines
                    });
                  }} /></td>
                    <td className="p-1"><Input type="number" value={l.unit_cost} onChange={e => {
                    const lines = [...poForm.lines];
                    lines[i].unit_cost = Number(e.target.value);
                    setPoForm({
                      ...poForm,
                      lines
                    });
                  }} /></td>
                    <td className="p-1 text-right text-xs">
                      {tl((Number(l.quantity) || 0) * (Number(l.unit_cost) || 0))}
                    </td>
                    <td className="p-1"><Button size="sm" variant="ghost" onClick={() => setPoForm({
                    ...poForm,
                    lines: poForm.lines.filter((_, j) => j !== i)
                  })}><Trash2 className="w-4 h-4" /></Button></td>
                  </tr>)}
              </tbody>
              <tfoot>
                <tr className="border-t font-semibold">
                  <td colSpan="5" className="p-2 text-right">{t('procurement.poModal.subtotal')}</td>
                  <td className="p-2 text-right">
                    {tl(poForm.lines.reduce((s, l) => s + (Number(l.quantity) || 0) * (Number(l.unit_cost) || 0), 0))}
                  </td>
                  <td></td>
                </tr>
                <tr>
                  <td colSpan="5" className="p-2 text-right">{t('procurement.poModal.vat', {
                    rate: poForm.tax_rate
                  })}</td>
                  <td className="p-2 text-right">
                    {tl(poForm.lines.reduce((s, l) => s + (Number(l.quantity) || 0) * (Number(l.unit_cost) || 0), 0) * poForm.tax_rate / 100)}
                  </td>
                  <td></td>
                </tr>
                <tr className="font-bold text-base">
                  <td colSpan="5" className="p-2 text-right">{t('procurement.poModal.grandTotal')}</td>
                  <td className="p-2 text-right">
                    {tl(poForm.lines.reduce((s, l) => s + (Number(l.quantity) || 0) * (Number(l.unit_cost) || 0), 0) * (1 + poForm.tax_rate / 100))}
                  </td>
                  <td></td>
                </tr>
              </tfoot>
            </table>
            <datalist id="inv-items-po">
              {inventoryItems.map(it => <option key={it.id || it._id || it.name} value={it.name}>
                  {it.sku ? `${it.sku} · ` : ''}{t('procurement.prModalForm.datalistAvailable')}: {it.quantity} {it.unit}
                </option>)}
            </datalist>
          </div>
          <div className="mt-4 text-right space-x-2">
            <Button variant="outline" onClick={() => setPoForm(null)}>{t('procurement.poModal.cancel')}</Button>
            <Button onClick={savePO}>{t('procurement.poModal.create')}</Button>
          </div>
        </Modal>}

      {/* ── PO Detail ────────────────────────────────── */}
      {selectedPo && <Modal title={t('procurement.poDetail.title', {
        no: selectedPo.po_no,
        supplier: selectedPo.supplier_name
      })} onClose={() => setSelectedPo(null)} wide>
          <div className="grid grid-cols-3 gap-3 text-sm">
            <div><span className="text-slate-500">{t('procurement.poDetail.status')}</span> <Badge className={`${PO_STATUS_CLS[selectedPo.status] || PO_STATUS_CLS.draft} border-0`}>{poLabel(selectedPo.status)}</Badge></div>
            <div><span className="text-slate-500">{t('procurement.poDetail.expected')}</span> {selectedPo.expected_delivery || '—'}</div>
            <div><span className="text-slate-500">{t('procurement.poDetail.total')}</span> <strong>{tl(selectedPo.grand_total)}</strong></div>
          </div>
          <h3 className="font-semibold text-sm mt-4 mb-1">{t('procurement.poDetail.items')}</h3>
          <table className="w-full text-sm">
            <thead><tr className="text-left border-b text-slate-600">
              <th className="p-1">{t('procurement.poDetail.itemHeader')}</th>
              <th className="p-1 w-16">{t('procurement.poDetail.orderedHeader')}</th>
              <th className="p-1 w-16">{t('procurement.poDetail.receivedHeader')}</th>
              <th className="p-1 w-16">{t('procurement.poDetail.remainingHeader')}</th>
              <th className="p-1 w-24 text-right">{t('procurement.poDetail.unitHeader')}</th>
              <th className="p-1 w-24 text-right">{t('procurement.poDetail.totalHeader')}</th>
            </tr></thead>
            <tbody>
              {(selectedPo.lines || []).map((l, i) => <tr key={l.id || i} className="border-b">
                  <td className="p-1">{l.item_name}</td>
                  <td className="p-1">{l.quantity} {l.unit}</td>
                  <td className="p-1">{l.received_qty || 0}</td>
                  <td className="p-1">{(l.quantity || 0) - (l.received_qty || 0)}</td>
                  <td className="p-1 text-right">{tl(l.unit_cost)}</td>
                  <td className="p-1 text-right">{tl(l.line_total)}</td>
                </tr>)}
            </tbody>
          </table>
          {selectedPo.grns?.length > 0 && <>
            <h3 className="font-semibold text-sm mt-4 mb-1">{t('procurement.poDetail.grnNotes')}</h3>
            <ul className="text-xs space-y-1">
              {selectedPo.grns.map(g => <li key={g.id} className="border-b py-1 flex justify-between">
                  <span>{g.grn_no} — {new Date(g.received_at).toLocaleString(i18n.language)}</span>
                  <span>{t('procurement.poDetail.grnSummary', {
                  count: g.lines?.length || 0,
                  user: g.received_by
                })}</span>
                </li>)}
            </ul>
          </>}
          <div className="mt-4 text-right space-x-2">
            {(selectedPo.status === 'sent' || selectedPo.status === 'partially_received') && <Button onClick={() => {
            openGrnForm(selectedPo);
          }}>
                <FileCheck2 className="w-4 h-4 mr-1" /> {t('procurement.poDetail.receiveGoods')}
              </Button>}
            <Button variant="ghost" onClick={() => setHistory({
            type: 'proc_po',
            id: selectedPo.id,
            title: selectedPo.po_no
          })}><HistoryIcon className="w-4 h-4 mr-1" /> {t('procurement.poDetail.history')}</Button>
          </div>
        </Modal>}

      {/* ── GRN Modal ────────────────────────────────── */}
      {grnForm && <Modal title={t('procurement.grnModal.title', {
        no: grnForm.po.po_no
      })} onClose={() => setGrnForm(null)} wide>
          <div className="text-xs text-slate-600 mb-2">
            {t('procurement.grnModal.supplier')} <strong>{grnForm.po.supplier_name}</strong>
          </div>
          <table className="w-full text-sm">
            <thead><tr className="text-left border-b text-slate-600">
              <th className="p-1">{t('procurement.grnModal.itemHeader')}</th>
              <th className="p-1 w-16">{t('procurement.grnModal.orderedHeader')}</th>
              <th className="p-1 w-16">{t('procurement.grnModal.previousHeader')}</th>
              <th className="p-1 w-24">{t('procurement.grnModal.thisShipmentHeader')}</th>
              <th className="p-1 w-32">{t('procurement.grnModal.qcHeader')}</th>
              <th className="p-1">{t('procurement.grnModal.noteHeader')}</th>
            </tr></thead>
            <tbody>
              {grnForm.lines.map((l, i) => <tr key={l.id || i} className="border-b">
                  <td className="p-1">{l.item_name}</td>
                  <td className="p-1">{l.ordered}</td>
                  <td className="p-1">{l.already}</td>
                  <td className="p-1"><Input type="number" value={l.received_qty} onChange={e => {
                  const lines = [...grnForm.lines];
                  lines[i].received_qty = Number(e.target.value);
                  setGrnForm({
                    ...grnForm,
                    lines
                  });
                }} /></td>
                  <td className="p-1">
                    <select className="border rounded p-1 w-full" value={l.qc_status} onChange={e => {
                  const lines = [...grnForm.lines];
                  lines[i].qc_status = e.target.value;
                  setGrnForm({
                    ...grnForm,
                    lines
                  });
                }}>
                      <option value="accepted">{t('procurement.grnModal.qc.accepted')}</option>
                      <option value="partial">{t('procurement.grnModal.qc.partial')}</option>
                      <option value="rejected">{t('procurement.grnModal.qc.rejected')}</option>
                    </select>
                  </td>
                  <td className="p-1"><Input value={l.notes || ''} onChange={e => {
                  const lines = [...grnForm.lines];
                  lines[i].notes = e.target.value;
                  setGrnForm({
                    ...grnForm,
                    lines
                  });
                }} /></td>
                </tr>)}
            </tbody>
          </table>
          <div className="mt-3"><Label>{t('procurement.grnModal.generalNote')}</Label>
            <Input value={grnForm.notes || ''} onChange={e => setGrnForm({
            ...grnForm,
            notes: e.target.value
          })} /></div>
          <div className="mt-4 text-right space-x-2">
            <Button variant="outline" onClick={() => setGrnForm(null)}>{t('procurement.grnModal.cancel')}</Button>
            <Button onClick={saveGRN}>{t('procurement.grnModal.confirm')}</Button>
          </div>
        </Modal>}

      {/* ── History Drawer ───────────────────────────── */}
      {history && <EntityHistoryDrawer entityType={history.type} entityId={history.id} title={history.title} onClose={() => setHistory(null)} />}
    </div>
    </>;
};
export default ProcurementPage;