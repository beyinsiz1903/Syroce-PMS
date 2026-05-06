import React, { useCallback, useEffect, useMemo, useRef, useState } from 'react';
import axios from 'axios';
import { toast } from 'sonner';
import Layout from '@/components/Layout';
import { Card, CardContent, CardHeader, CardTitle } from '@/components/ui/card';
import { Button } from '@/components/ui/button';
import { Input } from '@/components/ui/input';
import { Label } from '@/components/ui/label';
import { Textarea } from '@/components/ui/textarea';
import {
  Select, SelectContent, SelectItem, SelectTrigger, SelectValue,
} from '@/components/ui/select';
import {
  Dialog, DialogContent, DialogHeader, DialogTitle, DialogTrigger, DialogFooter,
} from '@/components/ui/dialog';
import { Mail, Phone, Trash2, Activity, RefreshCw } from 'lucide-react';

const STAGES = [
  { key: 'new',           label: 'Yeni',       color: 'bg-gray-500' },
  { key: 'contacted',     label: 'İletişim',   color: 'bg-blue-500' },
  { key: 'qualified',     label: 'Nitelikli',  color: 'bg-indigo-500' },
  { key: 'proposal_sent', label: 'Teklif',     color: 'bg-indigo-500' },
  { key: 'negotiating',   label: 'Müzakere',   color: 'bg-amber-500' },
  { key: 'won',           label: 'Kazanıldı',  color: 'bg-green-500' },
  { key: 'lost',          label: 'Kaybedildi', color: 'bg-red-500' },
];
const STAGE_LABEL = Object.fromEntries(STAGES.map((s) => [s.key, s.label]));
const ACTIVITY_TYPES = [
  { key: 'call',    label: 'Telefon' },
  { key: 'email',   label: 'E-posta' },
  { key: 'meeting', label: 'Toplantı' },
  { key: 'note',    label: 'Not' },
  { key: 'task',    label: 'Görev' },
];
const ACTIVITY_LABEL = Object.fromEntries(
  ACTIVITY_TYPES.map((a) => [a.key, a.label]),
);

const fmtTL = (v) =>
  Number(v || 0).toLocaleString('tr-TR', {
    style: 'currency', currency: 'TRY', maximumFractionDigits: 0,
  });

const SalesCRM = ({ user, tenant, onLogout }) => {
  const [leads, setLeads] = useState([]);
  const [funnel, setFunnel] = useState(null);
  const [loadingList, setLoadingList] = useState(true);
  const [statusFilter, setStatusFilter] = useState('all');
  const [search, setSearch] = useState('');

  // Yeni lead diyaloğu
  const [showCreate, setShowCreate] = useState(false);
  const [creating, setCreating] = useState(false);
  const emptyNew = {
    contact_name: '', contact_email: '', contact_phone: '',
    company_name: '', source: 'website', priority: 'medium',
    estimated_value: 0, estimated_rooms: 0, notes: '',
  };
  const [newLead, setNewLead] = useState(emptyNew);

  // Detay diyaloğu
  const [detailOpen, setDetailOpen] = useState(false);
  const [detailLoading, setDetailLoading] = useState(false);
  const [detail, setDetail] = useState(null); // { lead, activities }
  const [stageSaving, setStageSaving] = useState(false);
  const [actDraft, setActDraft] = useState({
    activity_type: 'call', subject: '', description: '',
  });
  const [actSaving, setActSaving] = useState(false);
  const [confirmDelete, setConfirmDelete] = useState(false);

  // ── Listeleme ──
  // Stale-response guard: yalnızca son istek setLeads çalıştırabilsin.
  const reqIdRef = useRef(0);

  const loadLeads = useCallback(async (statusArg, searchArg) => {
    const myId = ++reqIdRef.current;
    setLoadingList(true);
    try {
      const params = {};
      if (statusArg && statusArg !== 'all') params.status = statusArg;
      if (searchArg && searchArg.trim()) params.q = searchArg.trim();
      const r = await axios.get('/sales/leads', { params });
      if (myId === reqIdRef.current) {
        setLeads(r.data?.leads || []);
      }
    } catch (e) {
      if (myId === reqIdRef.current) {
        toast.error('Lead listesi yüklenemedi');
        setLeads([]);
      }
    } finally {
      if (myId === reqIdRef.current) setLoadingList(false);
    }
  }, []);

  const loadFunnel = useCallback(async () => {
    try {
      const r = await axios.get('/sales/funnel');
      setFunnel(r.data || null);
    } catch (e) {
      setFunnel(null);
    }
  }, []);

  useEffect(() => { loadFunnel(); }, [loadFunnel]);

  // Tek effect: status anında, search debounced. Stale yanıtları guard yutar.
  useEffect(() => {
    const delay = search.trim() ? 300 : 0;
    const t = setTimeout(() => loadLeads(statusFilter, search), delay);
    return () => clearTimeout(t);
  }, [statusFilter, search, loadLeads]);

  // ── Oluştur ──
  const handleCreate = async (e) => {
    e.preventDefault();
    if (!newLead.contact_name || !newLead.contact_email) {
      toast.error('Ad ve e-posta zorunlu');
      return;
    }
    setCreating(true);
    try {
      await axios.post('/sales/leads', newLead);
      toast.success('Lead oluşturuldu');
      setShowCreate(false);
      setNewLead(emptyNew);
      await Promise.all([loadLeads(statusFilter, search), loadFunnel()]);
    } catch (err) {
      toast.error(err?.response?.data?.detail || 'Lead oluşturulamadı');
    } finally {
      setCreating(false);
    }
  };

  // ── Detay aç ──
  const openDetail = async (leadId) => {
    setDetailOpen(true);
    setDetailLoading(true);
    setDetail(null);
    try {
      const r = await axios.get(`/sales/leads/${leadId}`);
      setDetail(r.data);
    } catch (err) {
      toast.error('Lead detayı yüklenemedi');
      setDetailOpen(false);
    } finally {
      setDetailLoading(false);
    }
  };

  // ── Aşama değiştir ──
  const changeStage = async (newStatus) => {
    if (!detail?.lead) return;
    if (newStatus === detail.lead.status) return;
    setStageSaving(true);
    try {
      await axios.put(`/sales/leads/${detail.lead.id}/stage`, { status: newStatus });
      toast.success(`Aşama: ${STAGE_LABEL[newStatus] || newStatus}`);
      await openDetail(detail.lead.id);
      await Promise.all([loadLeads(statusFilter, search), loadFunnel()]);
    } catch (err) {
      toast.error(err?.response?.data?.detail || 'Aşama güncellenemedi');
    } finally {
      setStageSaving(false);
    }
  };

  // ── Aktivite ekle ──
  const logActivity = async (e) => {
    e.preventDefault();
    if (!actDraft.subject.trim()) {
      toast.error('Konu zorunlu');
      return;
    }
    setActSaving(true);
    try {
      await axios.post('/sales/activity', {
        lead_id: detail.lead.id,
        activity_type: actDraft.activity_type,
        subject: actDraft.subject,
        description: actDraft.description,
      });
      toast.success('Aktivite kaydedildi');
      setActDraft({ activity_type: 'call', subject: '', description: '' });
      await openDetail(detail.lead.id);
    } catch (err) {
      toast.error(err?.response?.data?.detail || 'Aktivite kaydedilemedi');
    } finally {
      setActSaving(false);
    }
  };

  // ── Sil ──
  const deleteLead = async () => {
    if (!detail?.lead) return;
    try {
      await axios.delete(`/sales/leads/${detail.lead.id}`);
      toast.success('Lead silindi');
      setConfirmDelete(false);
      setDetailOpen(false);
      setDetail(null);
      await Promise.all([loadLeads(statusFilter, search), loadFunnel()]);
    } catch (err) {
      toast.error(err?.response?.data?.detail || 'Lead silinemedi');
    }
  };

  const stageBadgeClass = useMemo(() => ({
    new:           'bg-gray-100 text-gray-700',
    contacted:     'bg-blue-100 text-blue-800',
    qualified:     'bg-indigo-100 text-indigo-800',
    proposal_sent: 'bg-indigo-100 text-indigo-800',
    negotiating:   'bg-amber-100 text-amber-800',
    won:           'bg-green-100 text-green-800',
    lost:          'bg-red-100 text-red-800',
  }), []);

  return (
    <Layout user={user} tenant={tenant} onLogout={onLogout} currentModule="sales-crm">
      <div className="p-6">
        {/* Başlık + Yeni Lead */}
        <div className="flex flex-wrap items-center justify-between gap-3 mb-6">
          <div>
            <h1 className="text-2xl font-bold text-gray-900">
              Satış CRM &amp; Pipeline
            </h1>
            <p className="text-sm text-gray-600 mt-1">
              Lead'leri yönet, aşama değiştir, aktivite kaydet
            </p>
          </div>

          <div className="flex items-center gap-2">
            <Button
              variant="outline"
              size="sm"
              onClick={() => { loadLeads(statusFilter, search); loadFunnel(); }}
              disabled={loadingList}
            >
              <RefreshCw className={`w-4 h-4 mr-2 ${loadingList ? 'animate-spin' : ''}`} />
              Yenile
            </Button>

            <Dialog open={showCreate} onOpenChange={setShowCreate}>
              <DialogTrigger asChild>
                <Button className="bg-blue-600 hover:bg-blue-700">+ Yeni Lead</Button>
              </DialogTrigger>
              <DialogContent>
                <DialogHeader>
                  <DialogTitle>Yeni Lead Oluştur</DialogTitle>
                </DialogHeader>
                <form onSubmit={handleCreate} className="space-y-3 mt-2">
                  <div>
                    <Label>İlgili Kişi *</Label>
                    <Input
                      value={newLead.contact_name}
                      onChange={(e) => setNewLead({ ...newLead, contact_name: e.target.value })}
                      required
                    />
                  </div>
                  <div className="grid grid-cols-2 gap-3">
                    <div>
                      <Label>E-posta *</Label>
                      <Input
                        type="email"
                        value={newLead.contact_email}
                        onChange={(e) => setNewLead({ ...newLead, contact_email: e.target.value })}
                        required
                      />
                    </div>
                    <div>
                      <Label>Telefon</Label>
                      <Input
                        value={newLead.contact_phone}
                        onChange={(e) => setNewLead({ ...newLead, contact_phone: e.target.value })}
                      />
                    </div>
                  </div>
                  <div>
                    <Label>Şirket</Label>
                    <Input
                      value={newLead.company_name}
                      onChange={(e) => setNewLead({ ...newLead, company_name: e.target.value })}
                    />
                  </div>
                  <div className="grid grid-cols-3 gap-3">
                    <div>
                      <Label>Tahmini Oda</Label>
                      <Input
                        type="number" min={0}
                        value={newLead.estimated_rooms}
                        onChange={(e) => setNewLead({
                          ...newLead, estimated_rooms: parseInt(e.target.value) || 0,
                        })}
                      />
                    </div>
                    <div>
                      <Label>Tahmini Değer (₺)</Label>
                      <Input
                        type="number" min={0}
                        value={newLead.estimated_value}
                        onChange={(e) => setNewLead({
                          ...newLead, estimated_value: parseFloat(e.target.value) || 0,
                        })}
                      />
                    </div>
                    <div>
                      <Label>Öncelik</Label>
                      <Select
                        value={newLead.priority}
                        onValueChange={(v) => setNewLead({ ...newLead, priority: v })}
                      >
                        <SelectTrigger><SelectValue /></SelectTrigger>
                        <SelectContent>
                          <SelectItem value="low">Düşük</SelectItem>
                          <SelectItem value="medium">Orta</SelectItem>
                          <SelectItem value="high">Yüksek</SelectItem>
                        </SelectContent>
                      </Select>
                    </div>
                  </div>
                  <div>
                    <Label>Notlar</Label>
                    <Textarea
                      rows={2}
                      value={newLead.notes}
                      onChange={(e) => setNewLead({ ...newLead, notes: e.target.value })}
                    />
                  </div>
                  <Button type="submit" className="w-full" disabled={creating}>
                    {creating ? 'Oluşturuluyor…' : 'Oluştur'}
                  </Button>
                </form>
              </DialogContent>
            </Dialog>
          </div>
        </div>

        {/* Funnel */}
        {funnel && (
          <Card className="mb-6">
            <CardHeader className="pb-3">
              <CardTitle className="text-base">Satış Hunisi</CardTitle>
            </CardHeader>
            <CardContent>
              <div className="grid grid-cols-2 sm:grid-cols-4 lg:grid-cols-7 gap-2">
                {STAGES.map((s) => {
                  const count = funnel?.funnel?.[s.key] ?? 0;
                  const active = statusFilter === s.key;
                  return (
                    <button
                      key={s.key}
                      type="button"
                      onClick={() => setStatusFilter(active ? 'all' : s.key)}
                      className={`text-center transition ${active ? 'ring-2 ring-blue-500 rounded-lg' : ''}`}
                      title={`${s.label} aşamasındaki lead'leri filtrele`}
                    >
                      <div className={`${s.color} text-white rounded-lg p-3 mb-1`}>
                        <p className="text-2xl font-bold">{count}</p>
                      </div>
                      <p className="text-xs text-gray-600">{s.label}</p>
                    </button>
                  );
                })}
              </div>
              <div className="mt-4 pt-4 border-t flex items-center justify-between text-sm">
                <span className="text-gray-600">
                  Toplam: <span className="font-semibold text-gray-900">{funnel.total_leads}</span> lead
                </span>
                <span className="text-gray-600">
                  Win Rate: <span className="font-bold text-green-600">{funnel.win_rate}%</span>
                </span>
              </div>
            </CardContent>
          </Card>
        )}

        {/* Filtreler */}
        <div className="flex flex-wrap gap-3 mb-4">
          <div className="flex-1 min-w-[200px]">
            <Input
              placeholder="Ara: kişi, şirket veya e-posta…"
              value={search}
              onChange={(e) => setSearch(e.target.value)}
            />
          </div>
          <div className="w-44">
            <Select value={statusFilter} onValueChange={setStatusFilter}>
              <SelectTrigger><SelectValue placeholder="Aşama" /></SelectTrigger>
              <SelectContent>
                <SelectItem value="all">Tüm aşamalar</SelectItem>
                {STAGES.map((s) => (
                  <SelectItem key={s.key} value={s.key}>{s.label}</SelectItem>
                ))}
              </SelectContent>
            </Select>
          </div>
        </div>

        {/* Liste */}
        {loadingList ? (
          <div className="text-center text-gray-500 py-12">Yükleniyor…</div>
        ) : leads.length === 0 ? (
          <Card>
            <CardContent className="py-12 text-center text-gray-500">
              Filtreyle eşleşen lead yok. "+ Yeni Lead" ile başla.
            </CardContent>
          </Card>
        ) : (
          <div className="grid grid-cols-1 gap-3">
            {leads.map((lead) => (
              <Card
                key={lead.id}
                className="cursor-pointer hover:shadow-md transition"
                onClick={() => openDetail(lead.id)}
              >
                <CardContent className="pt-5 pb-5">
                  <div className="flex items-start justify-between gap-4">
                    <div className="flex-1 min-w-0">
                      <h3 className="text-base font-semibold text-gray-900 truncate">
                        {lead.contact_name || '—'}
                      </h3>
                      {lead.company_name && (
                        <p className="text-sm text-gray-600 truncate">{lead.company_name}</p>
                      )}
                      <div className="flex flex-wrap items-center gap-3 mt-2 text-xs text-gray-600">
                        {lead.contact_email && (
                          <span className="flex items-center gap-1">
                            <Mail className="w-3.5 h-3.5" />{lead.contact_email}
                          </span>
                        )}
                        {lead.contact_phone && (
                          <span className="flex items-center gap-1">
                            <Phone className="w-3.5 h-3.5" />{lead.contact_phone}
                          </span>
                        )}
                        {lead.estimated_rooms ? (
                          <span>Oda: {lead.estimated_rooms}</span>
                        ) : null}
                      </div>
                    </div>
                    <div className="text-right whitespace-nowrap">
                      {Number(lead.estimated_value) > 0 && (
                        <p className="text-lg font-bold text-green-700">
                          {fmtTL(lead.estimated_value)}
                        </p>
                      )}
                      <span className={`inline-block mt-1 px-2 py-0.5 rounded-full text-xs font-medium ${stageBadgeClass[lead.status] || 'bg-gray-100 text-gray-700'}`}>
                        {STAGE_LABEL[lead.status] || lead.status}
                      </span>
                    </div>
                  </div>
                </CardContent>
              </Card>
            ))}
          </div>
        )}

        {/* Detay diyaloğu */}
        <Dialog open={detailOpen} onOpenChange={(v) => { if (!v) { setDetailOpen(false); setDetail(null); } }}>
          <DialogContent className="max-w-2xl max-h-[85vh] overflow-y-auto">
            <DialogHeader>
              <DialogTitle>Lead Detayı</DialogTitle>
            </DialogHeader>
            {detailLoading || !detail ? (
              <div className="py-10 text-center text-gray-500">Yükleniyor…</div>
            ) : (
              <div className="space-y-4">
                <div>
                  <h3 className="text-lg font-semibold">{detail.lead.contact_name}</h3>
                  {detail.lead.company_name && (
                    <p className="text-sm text-gray-600">{detail.lead.company_name}</p>
                  )}
                  <div className="flex flex-wrap gap-3 mt-2 text-sm text-gray-700">
                    {detail.lead.contact_email && (
                      <span className="flex items-center gap-1">
                        <Mail className="w-4 h-4" />{detail.lead.contact_email}
                      </span>
                    )}
                    {detail.lead.contact_phone && (
                      <span className="flex items-center gap-1">
                        <Phone className="w-4 h-4" />{detail.lead.contact_phone}
                      </span>
                    )}
                  </div>
                  <div className="grid grid-cols-3 gap-3 mt-3 text-sm">
                    <div>
                      <p className="text-gray-500">Tahmini Değer</p>
                      <p className="font-semibold">{fmtTL(detail.lead.estimated_value)}</p>
                    </div>
                    <div>
                      <p className="text-gray-500">Tahmini Oda</p>
                      <p className="font-semibold">{detail.lead.estimated_rooms || 0}</p>
                    </div>
                    <div>
                      <p className="text-gray-500">Öncelik</p>
                      <p className="font-semibold capitalize">{detail.lead.priority || '—'}</p>
                    </div>
                  </div>
                  {detail.lead.notes && (
                    <div className="mt-3 text-sm">
                      <p className="text-gray-500">Notlar</p>
                      <p className="text-gray-800 whitespace-pre-wrap">{detail.lead.notes}</p>
                    </div>
                  )}
                </div>

                {/* Aşama */}
                <div className="border-t pt-3">
                  <Label className="block mb-1">Aşama</Label>
                  <div className="flex items-center gap-2">
                    <Select
                      value={detail.lead.status}
                      onValueChange={changeStage}
                      disabled={stageSaving}
                    >
                      <SelectTrigger className="w-56"><SelectValue /></SelectTrigger>
                      <SelectContent>
                        {STAGES.map((s) => (
                          <SelectItem key={s.key} value={s.key}>{s.label}</SelectItem>
                        ))}
                      </SelectContent>
                    </Select>
                    {stageSaving && <span className="text-xs text-gray-500">Kaydediliyor…</span>}
                  </div>
                </div>

                {/* Aktivite ekle */}
                <form onSubmit={logActivity} className="border-t pt-3 space-y-2">
                  <Label className="block">Aktivite Ekle</Label>
                  <div className="grid grid-cols-3 gap-2">
                    <Select
                      value={actDraft.activity_type}
                      onValueChange={(v) => setActDraft({ ...actDraft, activity_type: v })}
                    >
                      <SelectTrigger><SelectValue /></SelectTrigger>
                      <SelectContent>
                        {ACTIVITY_TYPES.map((a) => (
                          <SelectItem key={a.key} value={a.key}>{a.label}</SelectItem>
                        ))}
                      </SelectContent>
                    </Select>
                    <Input
                      className="col-span-2"
                      placeholder="Konu"
                      value={actDraft.subject}
                      onChange={(e) => setActDraft({ ...actDraft, subject: e.target.value })}
                      required
                    />
                  </div>
                  <Textarea
                    rows={2}
                    placeholder="Açıklama (opsiyonel)"
                    value={actDraft.description}
                    onChange={(e) => setActDraft({ ...actDraft, description: e.target.value })}
                  />
                  <Button type="submit" size="sm" disabled={actSaving}>
                    {actSaving ? 'Kaydediliyor…' : 'Aktivite Kaydet'}
                  </Button>
                </form>

                {/* Aktivite log */}
                <div className="border-t pt-3">
                  <div className="flex items-center gap-2 mb-2">
                    <Activity className="w-4 h-4 text-gray-500" />
                    <h4 className="text-sm font-semibold">Aktivite Geçmişi ({detail.activities.length})</h4>
                  </div>
                  {detail.activities.length === 0 ? (
                    <p className="text-xs text-gray-500">Henüz aktivite yok.</p>
                  ) : (
                    <ul className="space-y-2 max-h-48 overflow-y-auto">
                      {detail.activities.map((a) => (
                        <li key={a.id} className="text-sm border-l-2 border-gray-200 pl-3 py-1">
                          <div className="flex items-center justify-between">
                            <span className="font-medium">
                              {ACTIVITY_LABEL[a.activity_type] || a.activity_type}: {a.subject}
                            </span>
                            <span className="text-xs text-gray-500">
                              {a.created_at ? new Date(a.created_at).toLocaleString('tr-TR') : ''}
                            </span>
                          </div>
                          {a.description && (
                            <p className="text-xs text-gray-600 mt-0.5">{a.description}</p>
                          )}
                        </li>
                      ))}
                    </ul>
                  )}
                </div>

                <DialogFooter className="border-t pt-3">
                  <Button
                    variant="destructive"
                    size="sm"
                    onClick={() => setConfirmDelete(true)}
                  >
                    <Trash2 className="w-4 h-4 mr-1" /> Lead Sil
                  </Button>
                </DialogFooter>
              </div>
            )}
          </DialogContent>
        </Dialog>

        {/* Silme onayı */}
        <Dialog open={confirmDelete} onOpenChange={setConfirmDelete}>
          <DialogContent className="max-w-sm">
            <DialogHeader>
              <DialogTitle>Lead silinsin mi?</DialogTitle>
            </DialogHeader>
            <p className="text-sm text-gray-600">
              Bu işlem geri alınamaz. Bağlı tüm aktiviteler de silinir.
            </p>
            <DialogFooter className="mt-3 gap-2">
              <Button variant="outline" onClick={() => setConfirmDelete(false)}>Vazgeç</Button>
              <Button variant="destructive" onClick={deleteLead}>Sil</Button>
            </DialogFooter>
          </DialogContent>
        </Dialog>
      </div>
    </Layout>
  );
};

export default SalesCRM;
