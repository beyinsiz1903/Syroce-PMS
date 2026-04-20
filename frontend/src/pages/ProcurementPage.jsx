import { useEffect, useMemo, useState } from 'react';
import { useLocation, useNavigate } from 'react-router-dom';
import axios from 'axios';
import { toast } from 'sonner';
import {
  Card, CardContent, CardHeader, CardTitle, CardDescription,
} from '@/components/ui/card';
import { Button } from '@/components/ui/button';
import { Input } from '@/components/ui/input';
import { Label } from '@/components/ui/label';
import { Badge } from '@/components/ui/badge';
import { Tabs, TabsContent, TabsList, TabsTrigger } from '@/components/ui/tabs';
import {
  Plus, Truck, ClipboardList, Package, FileCheck2, RefreshCw,
  Trash2, Send, History as HistoryIcon, X,
} from 'lucide-react';
import Layout from '@/components/Layout';
import EntityHistoryDrawer from '@/components/EntityHistoryDrawer';

const PR_STATUS = {
  draft: { label: 'Taslak', cls: 'bg-slate-100 text-slate-700' },
  submitted: { label: 'Gönderildi', cls: 'bg-amber-100 text-amber-800' },
  approved: { label: 'Onaylandı', cls: 'bg-emerald-100 text-emerald-800' },
  rejected: { label: 'Red', cls: 'bg-red-100 text-red-800' },
  cancelled: { label: 'İptal', cls: 'bg-slate-100 text-slate-700' },
  converted: { label: 'POya Dönüştü', cls: 'bg-sky-100 text-sky-800' },
};

const PO_STATUS = {
  draft: { label: 'Taslak', cls: 'bg-slate-100 text-slate-700' },
  sent: { label: 'Gönderildi', cls: 'bg-amber-100 text-amber-800' },
  partially_received: { label: 'Kısmi Alındı', cls: 'bg-sky-100 text-sky-800' },
  received: { label: 'Tamamı Alındı', cls: 'bg-emerald-100 text-emerald-800' },
  cancelled: { label: 'İptal', cls: 'bg-red-100 text-red-800' },
  closed: { label: 'Kapalı', cls: 'bg-slate-200 text-slate-700' },
};

const tl = (n) => `${Number(n || 0).toLocaleString('tr-TR', { minimumFractionDigits: 2, maximumFractionDigits: 2 })} ₺`;

const Modal = ({ title, children, onClose, wide }) => (
  <div className="fixed inset-0 z-40 bg-black/40 flex items-center justify-center p-4"
       onClick={onClose}>
    <div className={`bg-white rounded-lg shadow-xl ${wide ? 'max-w-4xl' : 'max-w-2xl'} w-full max-h-[90vh] overflow-y-auto`}
         onClick={(e) => e.stopPropagation()}>
      <div className="border-b p-3 flex items-center justify-between sticky top-0 bg-white">
        <h2 className="font-semibold">{title}</h2>
        <Button size="sm" variant="ghost" onClick={onClose}><X className="w-4 h-4" /></Button>
      </div>
      <div className="p-4">{children}</div>
    </div>
  </div>
);

const ProcurementPage = ({ user, tenant, onLogout }) => {
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

  const refresh = async () => {
    setLoading(true);
    try {
      const [s, sup, pr, po, inv] = await Promise.all([
        axios.get('/procurement/summary'),
        axios.get('/procurement/suppliers?active_only=false'),
        axios.get('/procurement/purchase-requests'),
        axios.get('/procurement/purchase-orders'),
        axios.get('/accounting/inventory').catch(() => ({ data: { items: [] } })),
      ]);
      setSummary(s.data || {});
      setSuppliers(sup.data?.items || []);
      setPrs(pr.data?.items || []);
      setPos(po.data?.items || []);
      setInventoryItems(inv.data?.items || []);
    } catch (e) {
      toast.error('Satınalma verileri alınamadı');
    } finally { setLoading(false); }
  };
  useEffect(() => { refresh(); }, []);

  // Stok ekranından "Talep Oluştur" ile gelindiğinde formu otomatik aç
  useEffect(() => {
    const seed = location.state?.newPRItem;
    if (seed) {
      setPrForm({
        department: seed.department || '',
        requester: '',
        notes: `${seed.name} stoğu kritik seviyenin altına düştü.`,
        lines: [{
          item_name: seed.name || '',
          sku: seed.sku || '',
          inventory_item_id: seed.id || null,
          quantity: seed.suggested_quantity || Math.max(1, (seed.reorder_level || 0) * 2 - (seed.quantity || 0)),
          unit: seed.unit || 'adet',
          est_unit_cost: seed.unit_cost || 0,
        }],
      });
      navigate(location.pathname, { replace: true, state: null });
    }
  }, [location.state]);

  const inventoryByName = useMemo(
    () => Object.fromEntries(inventoryItems.map((i) => [i.name, i])), [inventoryItems]);

  const fillFromInventory = (lines, idx, value, costKey) => {
    const next = [...lines];
    next[idx] = { ...next[idx], item_name: value };
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

  const supplierMap = useMemo(
    () => Object.fromEntries(suppliers.map((s) => [s.id, s])), [suppliers]);

  // ── Supplier ops ───────────────────────────────────────
  const saveSupplier = async () => {
    try {
      const body = { ...supplierForm };
      if (!body.name || body.name.length < 2) {
        toast.error('İsim zorunlu (≥2 karakter)'); return;
      }
      if (supplierForm.id) {
        await axios.put(`/procurement/suppliers/${supplierForm.id}`, body);
        toast.success('Tedarikçi güncellendi');
      } else {
        await axios.post('/procurement/suppliers', body);
        toast.success('Tedarikçi eklendi');
      }
      setSupplierForm(null);
      refresh();
    } catch (e) {
      toast.error(e.response?.data?.detail || 'Kaydedilemedi');
    }
  };
  const deleteSupplier = async (id) => {
    if (!window.confirm('Tedarikçi silinsin mi?')) return;
    try {
      await axios.delete(`/procurement/suppliers/${id}`);
      toast.success('Silindi');
      refresh();
    } catch (e) {
      toast.error(e.response?.data?.detail || 'Silinemedi');
    }
  };

  // ── PR ops ─────────────────────────────────────────────
  const savePR = async () => {
    try {
      if (!prForm.department || !prForm.lines?.length) {
        toast.error('Departman ve en az bir kalem gerekli'); return;
      }
      await axios.post('/procurement/purchase-requests', prForm);
      toast.success('Talep oluşturuldu');
      setPrForm(null); refresh();
    } catch (e) {
      toast.error(e.response?.data?.detail || 'Oluşturulamadı');
    }
  };
  const changePRStatus = async (id, status) => {
    try {
      let reason = null;
      if (status === 'rejected' || status === 'cancelled') {
        reason = window.prompt(`${status === 'rejected' ? 'Red' : 'İptal'} nedeni (≥5 karakter):`);
        if (!reason || reason.trim().length < 5) {
          toast.error('Neden en az 5 karakter olmalı'); return;
        }
      }
      await axios.post(`/procurement/purchase-requests/${id}/status`,
        { status, reason });
      toast.success('Durum güncellendi');
      refresh();
    } catch (e) {
      toast.error(e.response?.data?.detail || 'Güncellenemedi');
    }
  };
  const convertPRtoPO = (pr) => {
    setPoForm({
      supplier_id: '',
      source_pr_id: pr.id,
      currency: 'TRY',
      tax_rate: 20,
      lines: (pr.lines || []).map((l) => ({
        item_name: l.item_name,
        sku: l.sku,
        inventory_item_id: l.inventory_item_id,
        quantity: l.quantity,
        unit: l.unit,
        unit_cost: l.est_unit_cost || 0,
      })),
    });
  };

  // ── PO ops ─────────────────────────────────────────────
  const savePO = async () => {
    try {
      if (!poForm.supplier_id || !poForm.lines?.length) {
        toast.error('Tedarikçi ve en az bir kalem gerekli'); return;
      }
      await axios.post('/procurement/purchase-orders', poForm);
      toast.success('Sipariş oluşturuldu');
      setPoForm(null); refresh();
    } catch (e) {
      toast.error(e.response?.data?.detail || 'Oluşturulamadı');
    }
  };
  const changePOStatus = async (id, status) => {
    try {
      let reason = null;
      if (status === 'cancelled') {
        reason = window.prompt('İptal nedeni (≥5 karakter):');
        if (!reason || reason.trim().length < 5) {
          toast.error('Neden en az 5 karakter olmalı'); return;
        }
      }
      await axios.post(`/procurement/purchase-orders/${id}/status`,
        { status, reason });
      toast.success('Durum güncellendi');
      refresh();
      if (selectedPo?.id === id) openPo(id);
    } catch (e) {
      toast.error(e.response?.data?.detail || 'Güncellenemedi');
    }
  };
  const openPo = async (id) => {
    try {
      const r = await axios.get(`/procurement/purchase-orders/${id}`);
      setSelectedPo(r.data);
    } catch { toast.error('PO yüklenemedi'); }
  };

  // ── GRN ops ────────────────────────────────────────────
  const openGrnForm = (po) => {
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
        notes: '',
      })),
    });
  };
  const saveGRN = async () => {
    try {
      const lines = grnForm.lines
        .filter((l) => Number(l.received_qty) > 0)
        .map((l) => ({
          po_line_idx: l.po_line_idx,
          received_qty: Number(l.received_qty),
          qc_status: l.qc_status,
          notes: l.notes,
        }));
      if (!lines.length) {
        toast.error('En az bir kalem için miktar girin'); return;
      }
      const r = await axios.post(
        `/procurement/purchase-orders/${grnForm.po.id}/grn`,
        { notes: grnForm.notes, lines });
      toast.success(`GRN ${r.data.grn?.grn_no} oluşturuldu — PO: ${r.data.po_status}`);
      setGrnForm(null);
      refresh();
      if (selectedPo?.id === grnForm.po.id) openPo(grnForm.po.id);
    } catch (e) {
      toast.error(e.response?.data?.detail || 'Mal kabul yapılamadı');
    }
  };

  return (
    <Layout user={user} tenant={tenant} onLogout={onLogout} currentModule="procurement">
    <div className="p-6 max-w-7xl mx-auto space-y-4">
      <div className="flex items-center justify-between">
        <div>
          <h1 className="text-2xl font-bold flex items-center gap-2">
            <Truck className="w-6 h-6" /> Satınalma & Tedarik
          </h1>
          <p className="text-sm text-slate-600">
            Tedarikçiler, satınalma talebi (PR), sipariş (PO), mal kabul (GRN).
          </p>
        </div>
        <Button onClick={refresh} variant="outline" disabled={loading}>
          <RefreshCw className={`w-4 h-4 mr-1 ${loading ? 'animate-spin' : ''}`} />
          Yenile
        </Button>
      </div>

      {/* Summary cards */}
      <div className="grid grid-cols-2 md:grid-cols-6 gap-3">
        {[
          ['Aktif Tedarikçi', summary.suppliers_active ?? 0],
          ['Bekleyen PR', summary.pr_pending ?? 0],
          ['Onaylı PR', summary.pr_approved ?? 0],
          ['Açık PO', summary.po_open ?? 0],
          ['Tamamlanan PO', summary.po_received ?? 0],
          ['Açık Tutar', tl(summary.open_commitment_value)],
        ].map(([k, v]) => (
          <Card key={k}><CardContent className="p-3">
            <div className="text-xs text-slate-500">{k}</div>
            <div className="text-lg font-semibold mt-1">{v}</div>
          </CardContent></Card>
        ))}
      </div>

      <Tabs value={tab} onValueChange={setTab}>
        <TabsList>
          <TabsTrigger value="summary"><ClipboardList className="w-4 h-4 mr-1" />PRs</TabsTrigger>
          <TabsTrigger value="pos"><Package className="w-4 h-4 mr-1" />POs</TabsTrigger>
          <TabsTrigger value="suppliers"><Truck className="w-4 h-4 mr-1" />Tedarikçiler</TabsTrigger>
        </TabsList>

        {/* ── PR LIST ─────────────────────────────────────── */}
        <TabsContent value="summary">
          <Card>
            <CardHeader className="flex-row items-center justify-between">
              <div>
                <CardTitle>Satınalma Talepleri</CardTitle>
                <CardDescription>Departmanların talep akışı, onay ve POya dönüştürme.</CardDescription>
              </div>
              <Button onClick={() => setPrForm({
                department: '', requester: '', notes: '',
                lines: [{ item_name: '', quantity: 1, unit: 'adet', est_unit_cost: 0 }],
              })}>
                <Plus className="w-4 h-4 mr-1" /> Yeni Talep
              </Button>
            </CardHeader>
            <CardContent>
              <table className="w-full text-sm">
                <thead><tr className="text-left border-b text-slate-600">
                  <th className="p-2">No</th><th className="p-2">Departman</th>
                  <th className="p-2">Talep Eden</th><th className="p-2">Kalem</th>
                  <th className="p-2 text-right">Tahmini</th>
                  <th className="p-2">Durum</th><th className="p-2 text-right">İşlem</th>
                </tr></thead>
                <tbody>
                  {prs.map((pr) => {
                    const st = PR_STATUS[pr.status] || PR_STATUS.draft;
                    return (
                      <tr key={pr.id} className="border-b hover:bg-slate-50">
                        <td className="p-2 font-mono text-xs">{pr.pr_no}</td>
                        <td className="p-2">{pr.department}</td>
                        <td className="p-2 text-xs text-slate-600">{pr.requester}</td>
                        <td className="p-2">{pr.lines?.length || 0}</td>
                        <td className="p-2 text-right">{tl(pr.lines_total)}</td>
                        <td className="p-2"><Badge className={`${st.cls} border-0`}>{st.label}</Badge></td>
                        <td className="p-2 text-right space-x-1 whitespace-nowrap">
                          {pr.status === 'draft' &&
                            <Button size="sm" variant="ghost"
                              onClick={() => changePRStatus(pr.id, 'submitted')}>Gönder</Button>}
                          {pr.status === 'submitted' && <>
                            <Button size="sm" variant="ghost"
                              onClick={() => changePRStatus(pr.id, 'approved')}>Onayla</Button>
                            <Button size="sm" variant="ghost"
                              onClick={() => changePRStatus(pr.id, 'rejected')}>Reddet</Button>
                          </>}
                          {pr.status === 'approved' &&
                            <Button size="sm" onClick={() => convertPRtoPO(pr)}>POya Çevir</Button>}
                          <Button size="sm" variant="ghost" title="Geçmiş"
                            onClick={() => setHistory({ type: 'proc_pr', id: pr.id, title: pr.pr_no })}>
                            <HistoryIcon className="w-4 h-4" />
                          </Button>
                        </td>
                      </tr>
                    );
                  })}
                  {prs.length === 0 && <tr><td colSpan="7" className="p-4 text-center text-slate-400">Talep yok</td></tr>}
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
                <CardTitle>Satınalma Siparişleri</CardTitle>
                <CardDescription>Tedarikçiye gönderilen siparişler ve mal kabul takibi.</CardDescription>
              </div>
              <Button onClick={() => setPoForm({
                supplier_id: '', currency: 'TRY', tax_rate: 20,
                lines: [{ item_name: '', quantity: 1, unit: 'adet', unit_cost: 0 }],
              })}>
                <Plus className="w-4 h-4 mr-1" /> Yeni Sipariş
              </Button>
            </CardHeader>
            <CardContent>
              <table className="w-full text-sm">
                <thead><tr className="text-left border-b text-slate-600">
                  <th className="p-2">No</th><th className="p-2">Tedarikçi</th>
                  <th className="p-2">Kalem</th><th className="p-2 text-right">Tutar</th>
                  <th className="p-2">Durum</th><th className="p-2 text-right">İşlem</th>
                </tr></thead>
                <tbody>
                  {pos.map((po) => {
                    const st = PO_STATUS[po.status] || PO_STATUS.draft;
                    return (
                      <tr key={po.id} className="border-b hover:bg-slate-50">
                        <td className="p-2 font-mono text-xs">{po.po_no}</td>
                        <td className="p-2">{po.supplier_name}</td>
                        <td className="p-2">{po.lines?.length || 0}</td>
                        <td className="p-2 text-right">{tl(po.grand_total)}</td>
                        <td className="p-2"><Badge className={`${st.cls} border-0`}>{st.label}</Badge></td>
                        <td className="p-2 text-right space-x-1 whitespace-nowrap">
                          <Button size="sm" variant="ghost" onClick={() => openPo(po.id)}>Detay</Button>
                          {po.status === 'draft' &&
                            <Button size="sm" onClick={() => changePOStatus(po.id, 'sent')}>
                              <Send className="w-3 h-3 mr-1" />Gönder
                            </Button>}
                          {(po.status === 'sent' || po.status === 'partially_received') &&
                            <Button size="sm" onClick={() => openGrnForm(po)}>
                              <FileCheck2 className="w-3 h-3 mr-1" />Mal Kabul
                            </Button>}
                          {po.status === 'received' &&
                            <Button size="sm" variant="ghost"
                              onClick={() => changePOStatus(po.id, 'closed')}>Kapat</Button>}
                          <Button size="sm" variant="ghost" title="Geçmiş"
                            onClick={() => setHistory({ type: 'proc_po', id: po.id, title: po.po_no })}>
                            <HistoryIcon className="w-4 h-4" />
                          </Button>
                        </td>
                      </tr>
                    );
                  })}
                  {pos.length === 0 && <tr><td colSpan="6" className="p-4 text-center text-slate-400">Sipariş yok</td></tr>}
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
                <CardTitle>Tedarikçiler</CardTitle>
                <CardDescription>Vendor master — kategori, ödeme vadesi, vergi no.</CardDescription>
              </div>
              <Button onClick={() => setSupplierForm({
                name: '', code: '', tax_no: '', contact_name: '', email: '', phone: '',
                address: '', payment_terms_days: 30, categories: [], notes: '', active: true,
              })}>
                <Plus className="w-4 h-4 mr-1" /> Yeni Tedarikçi
              </Button>
            </CardHeader>
            <CardContent>
              <table className="w-full text-sm">
                <thead><tr className="text-left border-b text-slate-600">
                  <th className="p-2">Kod</th><th className="p-2">İsim</th>
                  <th className="p-2">Vergi No</th><th className="p-2">İletişim</th>
                  <th className="p-2 text-right">Vade</th>
                  <th className="p-2">Durum</th><th className="p-2 text-right">İşlem</th>
                </tr></thead>
                <tbody>
                  {suppliers.map((s) => (
                    <tr key={s.id} className="border-b hover:bg-slate-50">
                      <td className="p-2 font-mono text-xs">{s.code || '—'}</td>
                      <td className="p-2 font-medium">{s.name}</td>
                      <td className="p-2 text-xs">{s.tax_no || '—'}</td>
                      <td className="p-2 text-xs">{s.contact_name || s.email || s.phone || '—'}</td>
                      <td className="p-2 text-right">{s.payment_terms_days} gün</td>
                      <td className="p-2">
                        <Badge className={s.active ? 'bg-emerald-100 text-emerald-800 border-0' : 'bg-slate-200 text-slate-600 border-0'}>
                          {s.active ? 'Aktif' : 'Pasif'}
                        </Badge>
                      </td>
                      <td className="p-2 text-right space-x-1">
                        <Button size="sm" variant="ghost" onClick={() => setSupplierForm(s)}>Düzenle</Button>
                        <Button size="sm" variant="ghost" onClick={() => deleteSupplier(s.id)}>
                          <Trash2 className="w-4 h-4" />
                        </Button>
                      </td>
                    </tr>
                  ))}
                  {suppliers.length === 0 && <tr><td colSpan="7" className="p-4 text-center text-slate-400">Tedarikçi yok</td></tr>}
                </tbody>
              </table>
            </CardContent>
          </Card>
        </TabsContent>
      </Tabs>

      {/* ── Supplier Modal ─────────────────────────────── */}
      {supplierForm && (
        <Modal title={supplierForm.id ? 'Tedarikçi Düzenle' : 'Yeni Tedarikçi'}
               onClose={() => setSupplierForm(null)}>
          <div className="grid grid-cols-2 gap-3">
            <div><Label>İsim *</Label>
              <Input value={supplierForm.name || ''}
                onChange={(e) => setSupplierForm({ ...supplierForm, name: e.target.value })} /></div>
            <div><Label>Kod</Label>
              <Input value={supplierForm.code || ''}
                onChange={(e) => setSupplierForm({ ...supplierForm, code: e.target.value })} /></div>
            <div><Label>Vergi No</Label>
              <Input value={supplierForm.tax_no || ''}
                onChange={(e) => setSupplierForm({ ...supplierForm, tax_no: e.target.value })} /></div>
            <div><Label>İletişim Kişisi</Label>
              <Input value={supplierForm.contact_name || ''}
                onChange={(e) => setSupplierForm({ ...supplierForm, contact_name: e.target.value })} /></div>
            <div><Label>E-posta</Label>
              <Input value={supplierForm.email || ''}
                onChange={(e) => setSupplierForm({ ...supplierForm, email: e.target.value })} /></div>
            <div><Label>Telefon</Label>
              <Input value={supplierForm.phone || ''}
                onChange={(e) => setSupplierForm({ ...supplierForm, phone: e.target.value })} /></div>
            <div className="col-span-2"><Label>Adres</Label>
              <Input value={supplierForm.address || ''}
                onChange={(e) => setSupplierForm({ ...supplierForm, address: e.target.value })} /></div>
            <div><Label>Ödeme Vadesi (gün)</Label>
              <Input type="number" value={supplierForm.payment_terms_days || 30}
                onChange={(e) => setSupplierForm({ ...supplierForm, payment_terms_days: Number(e.target.value) })} /></div>
            <div><Label>Kategoriler (virgülle)</Label>
              <Input value={(supplierForm.categories || []).join(', ')}
                onChange={(e) => setSupplierForm({
                  ...supplierForm,
                  categories: e.target.value.split(',').map((s) => s.trim()).filter(Boolean),
                })} /></div>
            <div className="col-span-2 flex items-center gap-2">
              <input type="checkbox" id="sf-active" checked={!!supplierForm.active}
                onChange={(e) => setSupplierForm({ ...supplierForm, active: e.target.checked })} />
              <label htmlFor="sf-active" className="text-sm">Aktif</label>
            </div>
            <div className="col-span-2"><Label>Notlar</Label>
              <Input value={supplierForm.notes || ''}
                onChange={(e) => setSupplierForm({ ...supplierForm, notes: e.target.value })} /></div>
          </div>
          <div className="mt-4 text-right space-x-2">
            <Button variant="outline" onClick={() => setSupplierForm(null)}>Vazgeç</Button>
            <Button onClick={saveSupplier}>Kaydet</Button>
          </div>
        </Modal>
      )}

      {/* ── PR Modal ─────────────────────────────────── */}
      {prForm && (
        <Modal title="Yeni Satınalma Talebi" onClose={() => setPrForm(null)} wide>
          <div className="grid grid-cols-2 gap-3">
            <div><Label>Departman *</Label>
              <Input value={prForm.department}
                onChange={(e) => setPrForm({ ...prForm, department: e.target.value })}
                placeholder="Housekeeping / F&B / Engineering" /></div>
            <div><Label>Talep Eden</Label>
              <Input value={prForm.requester || ''}
                onChange={(e) => setPrForm({ ...prForm, requester: e.target.value })} /></div>
            <div><Label>İhtiyaç Tarihi</Label>
              <Input type="date" value={prForm.needed_by || ''}
                onChange={(e) => setPrForm({ ...prForm, needed_by: e.target.value || null })} /></div>
            <div className="col-span-2"><Label>Notlar</Label>
              <Input value={prForm.notes || ''}
                onChange={(e) => setPrForm({ ...prForm, notes: e.target.value })} /></div>
          </div>
          <div className="mt-4">
            <div className="flex items-center justify-between mb-2">
              <h3 className="font-semibold text-sm">Kalemler</h3>
              <Button size="sm" variant="outline" onClick={() => setPrForm({
                ...prForm,
                lines: [...prForm.lines, { item_name: '', quantity: 1, unit: 'adet', est_unit_cost: 0 }],
              })}><Plus className="w-3 h-3 mr-1" /> Ekle</Button>
            </div>
            <table className="w-full text-sm">
              <thead><tr className="border-b text-left text-slate-600">
                <th className="p-1">Kalem</th><th className="p-1">SKU</th>
                <th className="p-1 w-20">Miktar</th><th className="p-1 w-20">Birim</th>
                <th className="p-1 w-24">Birim Tahmini</th><th className="p-1"></th>
              </tr></thead>
              <tbody>
                {prForm.lines.map((l, i) => (
                  <tr key={i}>
                    <td className="p-1">
                      <Input value={l.item_name} list="inv-items-pr"
                        placeholder="Stoktan seç veya yaz…"
                        onChange={(e) => setPrForm({
                          ...prForm,
                          lines: fillFromInventory(prForm.lines, i, e.target.value, 'est_unit_cost'),
                        })} />
                    </td>
                    <td className="p-1"><Input value={l.sku || ''}
                      onChange={(e) => {
                        const lines = [...prForm.lines]; lines[i].sku = e.target.value;
                        setPrForm({ ...prForm, lines });
                      }} /></td>
                    <td className="p-1"><Input type="number" value={l.quantity}
                      onChange={(e) => {
                        const lines = [...prForm.lines]; lines[i].quantity = Number(e.target.value);
                        setPrForm({ ...prForm, lines });
                      }} /></td>
                    <td className="p-1"><Input value={l.unit}
                      onChange={(e) => {
                        const lines = [...prForm.lines]; lines[i].unit = e.target.value;
                        setPrForm({ ...prForm, lines });
                      }} /></td>
                    <td className="p-1"><Input type="number" value={l.est_unit_cost}
                      onChange={(e) => {
                        const lines = [...prForm.lines]; lines[i].est_unit_cost = Number(e.target.value);
                        setPrForm({ ...prForm, lines });
                      }} /></td>
                    <td className="p-1"><Button size="sm" variant="ghost"
                      onClick={() => setPrForm({
                        ...prForm,
                        lines: prForm.lines.filter((_, j) => j !== i),
                      })}><Trash2 className="w-4 h-4" /></Button></td>
                  </tr>
                ))}
              </tbody>
            </table>
            <datalist id="inv-items-pr">
              {inventoryItems.map((it) => (
                <option key={it.id || it._id || it.name} value={it.name}>
                  {it.sku ? `${it.sku} · ` : ''}Mevcut: {it.quantity} {it.unit}
                </option>
              ))}
            </datalist>
            {inventoryItems.length > 0 && (
              <p className="text-xs text-slate-500 mt-2">
                İpucu: Kalem adı kutusuna yazmaya başlayın, stoğunuzdaki kalemler otomatik önerilir.
                Seçtiğinizde birim ve fiyat otomatik dolar.
              </p>
            )}
          </div>
          <div className="mt-4 text-right space-x-2">
            <Button variant="outline" onClick={() => setPrForm(null)}>Vazgeç</Button>
            <Button onClick={savePR}>Talep Oluştur</Button>
          </div>
        </Modal>
      )}

      {/* ── PO Modal ─────────────────────────────────── */}
      {poForm && (
        <Modal title={poForm.source_pr_id ? 'Talepten Sipariş' : 'Yeni Sipariş'}
               onClose={() => setPoForm(null)} wide>
          <div className="grid grid-cols-3 gap-3">
            <div><Label>Tedarikçi *</Label>
              <select className="w-full border rounded p-2"
                value={poForm.supplier_id}
                onChange={(e) => setPoForm({ ...poForm, supplier_id: e.target.value })}>
                <option value="">— Seç —</option>
                {suppliers.filter((s) => s.active).map((s) =>
                  <option key={s.id} value={s.id}>{s.name}</option>)}
              </select>
            </div>
            <div><Label>Beklenen Teslimat</Label>
              <Input type="date" value={poForm.expected_delivery || ''}
                onChange={(e) => setPoForm({ ...poForm, expected_delivery: e.target.value || null })} /></div>
            <div><Label>KDV %</Label>
              <Input type="number" value={poForm.tax_rate}
                onChange={(e) => setPoForm({ ...poForm, tax_rate: Number(e.target.value) })} /></div>
          </div>
          <div className="mt-4">
            <div className="flex items-center justify-between mb-2">
              <h3 className="font-semibold text-sm">Kalemler</h3>
              <Button size="sm" variant="outline" onClick={() => setPoForm({
                ...poForm,
                lines: [...poForm.lines, { item_name: '', quantity: 1, unit: 'adet', unit_cost: 0 }],
              })}><Plus className="w-3 h-3 mr-1" /> Ekle</Button>
            </div>
            <table className="w-full text-sm">
              <thead><tr className="border-b text-left text-slate-600">
                <th className="p-1">Kalem</th><th className="p-1">SKU</th>
                <th className="p-1 w-20">Miktar</th><th className="p-1 w-20">Birim</th>
                <th className="p-1 w-24">Birim Fiyat</th>
                <th className="p-1 w-24 text-right">Toplam</th><th className="p-1"></th>
              </tr></thead>
              <tbody>
                {poForm.lines.map((l, i) => (
                  <tr key={i}>
                    <td className="p-1">
                      <Input value={l.item_name} list="inv-items-po"
                        placeholder="Stoktan seç veya yaz…"
                        onChange={(e) => setPoForm({
                          ...poForm,
                          lines: fillFromInventory(poForm.lines, i, e.target.value, 'unit_cost'),
                        })} />
                    </td>
                    <td className="p-1"><Input value={l.sku || ''}
                      onChange={(e) => {
                        const lines = [...poForm.lines]; lines[i].sku = e.target.value;
                        setPoForm({ ...poForm, lines });
                      }} /></td>
                    <td className="p-1"><Input type="number" value={l.quantity}
                      onChange={(e) => {
                        const lines = [...poForm.lines]; lines[i].quantity = Number(e.target.value);
                        setPoForm({ ...poForm, lines });
                      }} /></td>
                    <td className="p-1"><Input value={l.unit}
                      onChange={(e) => {
                        const lines = [...poForm.lines]; lines[i].unit = e.target.value;
                        setPoForm({ ...poForm, lines });
                      }} /></td>
                    <td className="p-1"><Input type="number" value={l.unit_cost}
                      onChange={(e) => {
                        const lines = [...poForm.lines]; lines[i].unit_cost = Number(e.target.value);
                        setPoForm({ ...poForm, lines });
                      }} /></td>
                    <td className="p-1 text-right text-xs">
                      {tl((Number(l.quantity) || 0) * (Number(l.unit_cost) || 0))}
                    </td>
                    <td className="p-1"><Button size="sm" variant="ghost"
                      onClick={() => setPoForm({
                        ...poForm,
                        lines: poForm.lines.filter((_, j) => j !== i),
                      })}><Trash2 className="w-4 h-4" /></Button></td>
                  </tr>
                ))}
              </tbody>
              <tfoot>
                <tr className="border-t font-semibold">
                  <td colSpan="5" className="p-2 text-right">Ara Toplam:</td>
                  <td className="p-2 text-right">
                    {tl(poForm.lines.reduce((s, l) => s + (Number(l.quantity) || 0) * (Number(l.unit_cost) || 0), 0))}
                  </td>
                  <td></td>
                </tr>
                <tr>
                  <td colSpan="5" className="p-2 text-right">KDV ({poForm.tax_rate}%):</td>
                  <td className="p-2 text-right">
                    {tl(poForm.lines.reduce((s, l) => s + (Number(l.quantity) || 0) * (Number(l.unit_cost) || 0), 0) * poForm.tax_rate / 100)}
                  </td>
                  <td></td>
                </tr>
                <tr className="font-bold text-base">
                  <td colSpan="5" className="p-2 text-right">Genel Toplam:</td>
                  <td className="p-2 text-right">
                    {tl(poForm.lines.reduce((s, l) => s + (Number(l.quantity) || 0) * (Number(l.unit_cost) || 0), 0) * (1 + poForm.tax_rate / 100))}
                  </td>
                  <td></td>
                </tr>
              </tfoot>
            </table>
            <datalist id="inv-items-po">
              {inventoryItems.map((it) => (
                <option key={it.id || it._id || it.name} value={it.name}>
                  {it.sku ? `${it.sku} · ` : ''}Mevcut: {it.quantity} {it.unit}
                </option>
              ))}
            </datalist>
          </div>
          <div className="mt-4 text-right space-x-2">
            <Button variant="outline" onClick={() => setPoForm(null)}>Vazgeç</Button>
            <Button onClick={savePO}>Sipariş Oluştur</Button>
          </div>
        </Modal>
      )}

      {/* ── PO Detail ────────────────────────────────── */}
      {selectedPo && (
        <Modal title={`PO ${selectedPo.po_no} — ${selectedPo.supplier_name}`}
               onClose={() => setSelectedPo(null)} wide>
          <div className="grid grid-cols-3 gap-3 text-sm">
            <div><span className="text-slate-500">Durum:</span> <Badge className={`${(PO_STATUS[selectedPo.status] || PO_STATUS.draft).cls} border-0`}>{(PO_STATUS[selectedPo.status] || PO_STATUS.draft).label}</Badge></div>
            <div><span className="text-slate-500">Beklenen:</span> {selectedPo.expected_delivery || '—'}</div>
            <div><span className="text-slate-500">Toplam:</span> <strong>{tl(selectedPo.grand_total)}</strong></div>
          </div>
          <h3 className="font-semibold text-sm mt-4 mb-1">Kalemler</h3>
          <table className="w-full text-sm">
            <thead><tr className="text-left border-b text-slate-600">
              <th className="p-1">Kalem</th><th className="p-1 w-16">Sip.</th>
              <th className="p-1 w-16">Alınan</th><th className="p-1 w-16">Kalan</th>
              <th className="p-1 w-24 text-right">Birim</th><th className="p-1 w-24 text-right">Toplam</th>
            </tr></thead>
            <tbody>
              {(selectedPo.lines || []).map((l, i) => (
                <tr key={i} className="border-b">
                  <td className="p-1">{l.item_name}</td>
                  <td className="p-1">{l.quantity} {l.unit}</td>
                  <td className="p-1">{l.received_qty || 0}</td>
                  <td className="p-1">{(l.quantity || 0) - (l.received_qty || 0)}</td>
                  <td className="p-1 text-right">{tl(l.unit_cost)}</td>
                  <td className="p-1 text-right">{tl(l.line_total)}</td>
                </tr>
              ))}
            </tbody>
          </table>
          {selectedPo.grns?.length > 0 && <>
            <h3 className="font-semibold text-sm mt-4 mb-1">Mal Kabul Notları</h3>
            <ul className="text-xs space-y-1">
              {selectedPo.grns.map((g) => (
                <li key={g.id} className="border-b py-1 flex justify-between">
                  <span>{g.grn_no} — {new Date(g.received_at).toLocaleString('tr-TR')}</span>
                  <span>{g.lines?.length || 0} kalem · {g.received_by}</span>
                </li>
              ))}
            </ul>
          </>}
          <div className="mt-4 text-right space-x-2">
            {(selectedPo.status === 'sent' || selectedPo.status === 'partially_received') &&
              <Button onClick={() => { openGrnForm(selectedPo); }}>
                <FileCheck2 className="w-4 h-4 mr-1" /> Mal Kabul
              </Button>}
            <Button variant="ghost" onClick={() => setHistory({
              type: 'proc_po', id: selectedPo.id, title: selectedPo.po_no,
            })}><HistoryIcon className="w-4 h-4 mr-1" /> Geçmiş</Button>
          </div>
        </Modal>
      )}

      {/* ── GRN Modal ────────────────────────────────── */}
      {grnForm && (
        <Modal title={`Mal Kabul — PO ${grnForm.po.po_no}`}
               onClose={() => setGrnForm(null)} wide>
          <div className="text-xs text-slate-600 mb-2">
            Tedarikçi: <strong>{grnForm.po.supplier_name}</strong>
          </div>
          <table className="w-full text-sm">
            <thead><tr className="text-left border-b text-slate-600">
              <th className="p-1">Kalem</th><th className="p-1 w-16">Sip.</th>
              <th className="p-1 w-16">Önceki</th>
              <th className="p-1 w-24">Bu Sevkte</th>
              <th className="p-1 w-32">QC</th>
              <th className="p-1">Not</th>
            </tr></thead>
            <tbody>
              {grnForm.lines.map((l, i) => (
                <tr key={i} className="border-b">
                  <td className="p-1">{l.item_name}</td>
                  <td className="p-1">{l.ordered}</td>
                  <td className="p-1">{l.already}</td>
                  <td className="p-1"><Input type="number" value={l.received_qty}
                    onChange={(e) => {
                      const lines = [...grnForm.lines];
                      lines[i].received_qty = Number(e.target.value);
                      setGrnForm({ ...grnForm, lines });
                    }} /></td>
                  <td className="p-1">
                    <select className="border rounded p-1 w-full"
                      value={l.qc_status}
                      onChange={(e) => {
                        const lines = [...grnForm.lines];
                        lines[i].qc_status = e.target.value;
                        setGrnForm({ ...grnForm, lines });
                      }}>
                      <option value="accepted">Kabul</option>
                      <option value="partial">Kısmi</option>
                      <option value="rejected">Red</option>
                    </select>
                  </td>
                  <td className="p-1"><Input value={l.notes || ''}
                    onChange={(e) => {
                      const lines = [...grnForm.lines];
                      lines[i].notes = e.target.value;
                      setGrnForm({ ...grnForm, lines });
                    }} /></td>
                </tr>
              ))}
            </tbody>
          </table>
          <div className="mt-3"><Label>Genel Not</Label>
            <Input value={grnForm.notes || ''}
              onChange={(e) => setGrnForm({ ...grnForm, notes: e.target.value })} /></div>
          <div className="mt-4 text-right space-x-2">
            <Button variant="outline" onClick={() => setGrnForm(null)}>Vazgeç</Button>
            <Button onClick={saveGRN}>Mal Kabulü Onayla</Button>
          </div>
        </Modal>
      )}

      {/* ── History Drawer ───────────────────────────── */}
      {history && (
        <EntityHistoryDrawer
          entityType={history.type}
          entityId={history.id}
          title={history.title}
          onClose={() => setHistory(null)} />
      )}
    </div>
    </Layout>
  );
};

export default ProcurementPage;
