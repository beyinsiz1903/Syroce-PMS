import { useEffect, useMemo, useState, useCallback, useRef } from 'react';
import axios from 'axios';
import { toast } from 'sonner';

import { Card, CardContent, CardDescription, CardHeader, CardTitle } from '@/components/ui/card';
import { Button } from '@/components/ui/button';
import { Input } from '@/components/ui/input';
import { Label } from '@/components/ui/label';
import { Switch } from '@/components/ui/switch';
import { Tabs, TabsContent, TabsList, TabsTrigger } from '@/components/ui/tabs';
import { Skeleton } from '@/components/ui/skeleton';
import {
  Dialog, DialogContent, DialogDescription, DialogFooter, DialogHeader, DialogTitle,
} from '@/components/ui/dialog';
import { Select, SelectContent, SelectItem, SelectTrigger, SelectValue } from '@/components/ui/select';
import { PageHeader } from '@/components/ui/page-header';
import { KpiCard } from '@/components/ui/kpi-card';
import { StatusBadge } from '@/components/ui/status-badge';
import { confirmDialog } from '@/lib/dialogs';
import {
  Network, CheckCircle2, XCircle, AlertTriangle, Settings2, RefreshCw,
  Server, Globe, Building2, Send, Inbox, Power, Eye, Trash2,
  ChevronLeft, ChevronRight, Filter, PlayCircle,
} from 'lucide-react';
import { useTranslation } from 'react-i18next';

const CATEGORY_META = {
  gds:     { label: 'GDS / CRS',      icon: Globe,    color: 'text-indigo-600' },
  erp:     { label: 'ERP / Finance',  icon: Building2, color: 'text-emerald-600' },
  generic: { label: 'Generic',        icon: Server,    color: 'text-slate-600' },
};

const CERT_META = {
  in_development: { label: 'Geliştirmede',     intent: 'neutral', tooltip: 'Adapter geliştirme aşamasında — üretim için hazır değil' },
  uat:            { label: 'UAT (Test)',        intent: 'warning', tooltip: 'User Acceptance Testing — partner sertifikasyon süreci sürüyor; test/UAT ortamında kullanılabilir, üretime alınmadan önce sertifika tamamlanmalı' },
  certified:      { label: 'Sertifikalı',       intent: 'success', tooltip: 'Partner tarafından üretim için onaylanmış adapter' },
};
// Generic kategorisinde "certified" labelı yanıltıcı olabilir → "Hazır" olarak göster
const certLabelFor = (partner) => {
  const meta = CERT_META[partner.cert_status] || CERT_META.in_development;
  if (partner.category === 'generic' && partner.cert_status === 'certified') {
    return { ...meta, label: 'Hazır', tooltip: 'Hazır adapter — endpoint konfigürasyonu kullanıcıya bağlıdır' };
  }
  return meta;
};

const STATUS_META = {
  delivered:   { label: 'Teslim edildi', intent: 'success', icon: CheckCircle2 },
  pending:     { label: 'Bekliyor',      intent: 'neutral', icon: RefreshCw },
  in_flight:   { label: 'Gönderiliyor',  intent: 'info',    icon: Send },
  failed:      { label: 'Başarısız',     intent: 'warning', icon: AlertTriangle },
  dead_letter: { label: 'Dead-Letter',   intent: 'danger',  icon: XCircle },
  skipped:     { label: 'Atlandı',       intent: 'neutral', icon: Power },
};

const TR_TZ = 'Europe/Istanbul';
const fmtTimestamp = (iso) => {
  if (!iso) return '—';
  try {
    return new Date(iso).toLocaleString('tr-TR', {
      timeZone: TR_TZ, year: 'numeric', month: '2-digit', day: '2-digit',
      hour: '2-digit', minute: '2-digit', second: '2-digit',
    });
  } catch { return iso; }
};

// P1 #2: message type kısaltması ama tam adı her zaman tooltip + ellipsis ile korunur
const shortMsg = (mt) => (mt || '').replace('OTA_Hotel', '').replace('Syroce.', '');

// SSRF / private-IP guard (UI hint — backend de doğrular)
const PRIVATE_HOST_PATTERN = /(localhost|127\.|0\.0\.0\.0|10\.|192\.168\.|169\.254\.|::1|fc00:|fe80:)/i;
const looksPrivate = (url) => {
  if (!url) return false;
  try { return PRIVATE_HOST_PATTERN.test(new URL(url).hostname); }
  catch { return false; }
};

export default function XchangePage() {
  const { t } = useTranslation();
  const [partners, setPartners] = useState([]);
  const [configs, setConfigs] = useState([]);
  const [deliveries, setDeliveries] = useState([]);
  const [counts, setCounts] = useState({});
  const [loading, setLoading] = useState(true);
  const [editing, setEditing] = useState(null);
  const [form, setForm] = useState({});
  const [enabled, setEnabled] = useState(true);
  const [saving, setSaving] = useState(false);
  const [detail, setDetail] = useState(null);
  const [activeTab, setActiveTab] = useState('partners');

  // Pagination + filters (P1 #8 / #9)
  const [filterPartner, setFilterPartner] = useState('all');
  const [filterStatus, setFilterStatus] = useState('all');
  const [pageCursor, setPageCursor] = useState(null);
  const [cursorStack, setCursorStack] = useState([]);
  const [nextCursor, setNextCursor] = useState(null);
  const [selected, setSelected] = useState(new Set());

  // Auto-refresh (#28)
  const [autoRefresh, setAutoRefresh] = useState(false);
  const refreshTimer = useRef(null);

  const loadCatalog = useCallback(async () => {
    const [pRes, cRes] = await Promise.all([
      axios.get('/xchange/partners'),
      axios.get('/xchange/configs'),
    ]);
    setPartners(pRes.data.partners || []);
    setConfigs(cRes.data.configs || []);
  }, []);

  const loadDeliveries = useCallback(async () => {
    const params = { limit: 50 };
    if (filterPartner !== 'all') params.partner = filterPartner;
    if (filterStatus !== 'all') params.status = filterStatus;
    if (pageCursor) params.cursor = pageCursor;
    const r = await axios.get('/xchange/deliveries', { params });
    setDeliveries(r.data.deliveries || []);
    setCounts(r.data.counts || {});
    setNextCursor(r.data.next_cursor || null);
  }, [filterPartner, filterStatus, pageCursor]);

  const loadAll = useCallback(async () => {
    setLoading(true);
    try {
      await Promise.all([loadCatalog(), loadDeliveries()]);
    } catch (e) {
      toast.error(e.response?.data?.detail || 'Yüklenemedi');
    } finally {
      setLoading(false);
    }
  }, [loadCatalog, loadDeliveries]);

  useEffect(() => { loadAll(); }, []); // eslint-disable-line react-hooks/exhaustive-deps
  useEffect(() => { loadDeliveries().catch(() => {}); }, [filterPartner, filterStatus, pageCursor, loadDeliveries]);

  // Auto-refresh interval
  useEffect(() => {
    if (refreshTimer.current) { clearInterval(refreshTimer.current); refreshTimer.current = null; }
    if (autoRefresh) {
      refreshTimer.current = setInterval(() => { loadDeliveries().catch(() => {}); }, 30000);
    }
    return () => { if (refreshTimer.current) clearInterval(refreshTimer.current); };
  }, [autoRefresh, loadDeliveries]);

  const cfgByCode = useMemo(() => {
    const m = {};
    for (const c of configs) m[c.partner_code] = c;
    return m;
  }, [configs]);

  const openEditor = (partner) => {
    const existing = cfgByCode[partner.code];
    const initial = {};
    Object.entries(partner.config_schema || {}).forEach(([k, meta]) => {
      initial[k] = (existing?.config?.[k]) ?? meta.default ?? '';
    });
    setForm(initial);
    setEnabled(existing?.enabled ?? true);
    setEditing(partner.code);
  };

  const save = async () => {
    setSaving(true);
    try {
      await axios.put(`/xchange/configs/${editing}`, { enabled, config: form });
      toast.success('Partner ayarı kaydedildi');
      setEditing(null);
      await loadCatalog();
    } catch (e) {
      toast.error(e.response?.data?.detail || 'Kaydedilemedi');
    } finally {
      setSaving(false);
    }
  };

  const removeConfig = async (code) => {
    if (!await confirmDialog({ message: `${code} bağlantısı silinsin mi?`, variant: 'danger' })) return;
    try {
      await axios.delete(`/xchange/configs/${code}`);
      toast.success('Bağlantı kaldırıldı');
      await loadCatalog();
    } catch (e) {
      toast.error(e.response?.data?.detail || 'Silinemedi');
    }
  };

  const replay = async (id) => {
    try {
      const r = await axios.post(`/xchange/deliveries/${id}/replay`);
      toast.success(`Replay: ${STATUS_META[r.data.status]?.label || r.data.status} (deneme #${r.data.attempts})`);
      await loadDeliveries();
    } catch (e) {
      toast.error(e.response?.data?.detail || 'Replay başarısız');
    }
  };

  const replayBulk = async () => {
    const ids = [...selected];
    if (!ids.length) return;
    if (!await confirmDialog({
      message: `${ids.length} mesaj yeniden gönderilsin mi? (yalnız failed/dead_letter olanlar işlenir)`,
      variant: 'warning',
    })) return;
    try {
      const r = await axios.post('/xchange/deliveries/replay-bulk', { delivery_ids: ids });
      toast.success(`Toplu replay: ${r.data.replayed} başarılı, ${r.data.skipped} atlandı`);
      setSelected(new Set());
      await loadDeliveries();
    } catch (e) {
      toast.error(e.response?.data?.detail || 'Toplu replay başarısız');
    }
  };

  const viewDetail = async (id) => {
    try {
      const r = await axios.get(`/xchange/deliveries/${id}`);
      setDetail(r.data);
    } catch (e) {
      toast.error(e.response?.data?.detail || 'Yüklenemedi');
    }
  };

  const toggleSelect = (id) => {
    setSelected((prev) => {
      const next = new Set(prev);
      if (next.has(id)) next.delete(id); else next.add(id);
      return next;
    });
  };

  const goNextPage = () => {
    if (!nextCursor) return;
    setCursorStack((s) => [...s, pageCursor]);
    setPageCursor(nextCursor);
    setSelected(new Set());
  };
  const goPrevPage = () => {
    if (!cursorStack.length) return;
    const stack = [...cursorStack];
    const prev = stack.pop();
    setCursorStack(stack);
    setPageCursor(prev || null);
    setSelected(new Set());
  };
  const resetPagination = () => {
    setPageCursor(null);
    setCursorStack([]);
    setSelected(new Set());
  };

  const partnerOpts = useMemo(() => [{ code: 'all', name: 'Tüm partnerlar' }, ...partners.map(p => ({ code: p.code, name: p.name }))], [partners]);

  const editingPartner = useMemo(
    () => partners.find((p) => p.code === editing) || null,
    [editing, partners],
  );

  // ── Render ─────────────────────────────────────────────────────
  if (loading && !partners.length) {
    return (
      <div className="max-w-7xl mx-auto p-4 space-y-4">
        <Skeleton className="h-12 w-full max-w-lg" />
        <div className="grid grid-cols-2 sm:grid-cols-3 lg:grid-cols-5 gap-3">
          {[0, 1, 2, 3, 4].map(i => <Skeleton key={i} className="h-24" />)}
        </div>
        {[0, 1, 2].map(i => <Skeleton key={i} className="h-32" />)}
      </div>
    );
  }

  return (
    <div className="max-w-7xl mx-auto p-4 space-y-4">
      <PageHeader
        icon={Network}
        title="Syroce Xchange"
        subtitle={`${partners.length} tanımlı partner — HTNG/OData/HMAC üzerinden çift yönlü mesaj akışı`}
        actions={
          <div className="flex items-center gap-2 flex-wrap">
            <label className="flex items-center gap-2 text-xs text-slate-600 select-none cursor-pointer">
              <Switch checked={autoRefresh} onCheckedChange={setAutoRefresh} aria-label="Otomatik yenile" />
              Otomatik (30s)
            </label>
            <Button variant="outline" size="sm" onClick={loadAll} disabled={loading}>
              <RefreshCw className={`w-4 h-4 mr-1.5 ${loading ? 'animate-spin' : ''}`} /> {t('cm.pages_XchangePage.yenile')}
            </Button>
          </div>
        }
      />

      {/* KPI grid — interactive (P2 #17) */}
      <div className="grid grid-cols-2 sm:grid-cols-3 lg:grid-cols-5 gap-3">
        <KpiCard
          icon={Server}
          label={t('cm.pages_XchangePage.tanimli_partner')}
          value={partners.length}
          intent="info"
          onClick={() => setActiveTab('partners')}
        />
        <KpiCard
          icon={CheckCircle2}
          label={t('cm.pages_XchangePage.aktif_baglanti')}
          value={configs.filter((c) => c.enabled).length}
          intent="success"
          onClick={() => setActiveTab('partners')}
        />
        <KpiCard
          icon={Send}
          label="Teslim Edildi"
          value={counts.delivered || 0}
          intent="success"
          onClick={() => { setActiveTab('messages'); setFilterStatus('delivered'); resetPagination(); }}
        />
        <KpiCard
          icon={AlertTriangle}
          label={t('cm.pages_XchangePage.hatali')}
          value={counts.failed || 0}
          intent="warning"
          onClick={() => { setActiveTab('messages'); setFilterStatus('failed'); resetPagination(); }}
        />
        <KpiCard
          icon={XCircle}
          label="Dead-Letter"
          value={counts.dead_letter || 0}
          intent="danger"
          onClick={() => { setActiveTab('messages'); setFilterStatus('dead_letter'); resetPagination(); }}
        />
      </div>

      <Tabs value={activeTab} onValueChange={setActiveTab}>
        <TabsList>
          <TabsTrigger value="partners">Partner'lar</TabsTrigger>
          <TabsTrigger value="messages">{t('cm.pages_XchangePage.mesaj_akisi')}</TabsTrigger>
        </TabsList>

        {/* ───── Partners ───── */}
        <TabsContent value="partners" className="space-y-3">
          {partners.map((p) => {
            const cfg = cfgByCode[p.code];
            const cat = CATEGORY_META[p.category] || CATEGORY_META.generic;
            const cert = certLabelFor(p);
            const Icon = cat.icon;
            return (
              <Card key={p.code}>
                <CardHeader className="pb-2">
                  <div className="flex items-start justify-between flex-wrap gap-2">
                    <div className="flex items-start gap-3 min-w-0">
                      <div className={`w-10 h-10 rounded-lg bg-slate-50 ${cat.color} flex items-center justify-center shrink-0`}>
                        <Icon className="w-5 h-5" />
                      </div>
                      <div className="min-w-0">
                        <CardTitle className="text-base flex items-center gap-2 flex-wrap">
                          <span className="truncate">{p.name}</span>
                          <StatusBadge intent="neutral">{cat.label}</StatusBadge>
                          <span title={cert.tooltip}>
                            <StatusBadge intent={cert.intent}>{cert.label}</StatusBadge>
                          </span>
                          {cfg?.enabled && (
                            <StatusBadge intent="success" icon={CheckCircle2}>{t('cm.pages_XchangePage.aktif')}</StatusBadge>
                          )}
                        </CardTitle>
                        <CardDescription className="mt-1">{p.description}</CardDescription>
                      </div>
                    </div>
                    <div className="flex gap-2 shrink-0">
                      <Button size="sm" variant="outline" onClick={() => openEditor(p)}>
                        <Settings2 className="w-4 h-4 mr-1.5" /> {t('cm.pages_XchangePage.yapilandir')}
                      </Button>
                      {cfg && (
                        <Button size="sm" variant="outline" onClick={() => removeConfig(p.code)}>
                          <Trash2 className="w-4 h-4 mr-1.5" /> {t('cm.pages_XchangePage.sil')}
                        </Button>
                      )}
                    </div>
                  </div>
                </CardHeader>
                <CardContent>
                  <div className="text-xs font-semibold text-slate-500 uppercase tracking-wide mb-2">
                    Yetenek Matrisi
                  </div>
                  <div className="flex flex-wrap gap-1.5">
                    {p.capabilities.map((c, i) => {
                      const isOut = c.direction === 'outbound';
                      const intent = isOut ? 'info' : 'success';
                      const ArrowIcon = isOut ? Send : Inbox;
                      const prefix = isOut ? 'OUT' : 'IN';
                      const text = shortMsg(c.message_type);
                      return (
                        <span
                          key={i}
                          title={`${c.message_type} — ${isOut ? 'Outbound' : 'Inbound'}`}
                          className="inline-flex max-w-[260px]"
                        >
                          <StatusBadge intent={intent} icon={ArrowIcon} className="truncate">
                            <span className="font-mono opacity-60 mr-1">{prefix}</span>
                            <span className="truncate">{text}</span>
                          </StatusBadge>
                        </span>
                      );
                    })}
                  </div>
                </CardContent>
              </Card>
            );
          })}
        </TabsContent>

        {/* ───── Messages ───── */}
        <TabsContent value="messages" className="space-y-3">
          {/* Filters */}
          <Card>
            <CardContent className="p-3 flex items-center gap-2 flex-wrap">
              <div className="flex items-center gap-1.5 text-sm text-slate-600">
                <Filter className="w-4 h-4" /> {t('cm.pages_XchangePage.filtre')}
              </div>
              <Select value={filterPartner} onValueChange={(v) => { setFilterPartner(v); resetPagination(); }}>
                <SelectTrigger className="w-[200px] h-8 text-sm"><SelectValue /></SelectTrigger>
                <SelectContent>
                  {partnerOpts.map((p) => (
                    <SelectItem key={p.code} value={p.code}>{p.name}</SelectItem>
                  ))}
                </SelectContent>
              </Select>
              <Select value={filterStatus} onValueChange={(v) => { setFilterStatus(v); resetPagination(); }}>
                <SelectTrigger className="w-[180px] h-8 text-sm"><SelectValue /></SelectTrigger>
                <SelectContent>
                  <SelectItem value="all">{t('cm.pages_XchangePage.tum_durumlar')}</SelectItem>
                  {Object.entries(STATUS_META).map(([k, m]) => (
                    <SelectItem key={k} value={k}>{m.label}</SelectItem>
                  ))}
                </SelectContent>
              </Select>
              {selected.size > 0 && (
                <Button size="sm" variant="outline" onClick={replayBulk}>
                  <PlayCircle className="w-4 h-4 mr-1.5" /> Toplu Replay ({selected.size})
                </Button>
              )}
              <div className="ml-auto flex items-center gap-2">
                <Button size="sm" variant="outline" onClick={goPrevPage} disabled={!cursorStack.length}>
                  <ChevronLeft className="w-4 h-4" />
                </Button>
                <Button size="sm" variant="outline" onClick={goNextPage} disabled={!nextCursor}>
                  <ChevronRight className="w-4 h-4" />
                </Button>
              </div>
            </CardContent>
          </Card>

          <Card>
            <CardContent className="p-0">
              <div className="overflow-x-auto">
                <table className="w-full text-sm">
                  <thead className="bg-slate-50 border-b">
                    <tr className="text-left">
                      <th className="p-2 w-8"></th>
                      <th className="p-2">Zaman</th>
                      <th className="p-2">Partner</th>
                      <th className="p-2">Mesaj</th>
                      <th className="p-2">{t('cm.pages_XchangePage.yon')}</th>
                      <th className="p-2">{t('cm.pages_XchangePage.durum')}</th>
                      <th className="p-2">Deneme</th>
                      <th className="p-2 text-right">{t('cm.pages_XchangePage.islem')}</th>
                    </tr>
                  </thead>
                  <tbody>
                    {deliveries.length === 0 && (
                      <tr><td colSpan={8} className="p-6 text-center text-slate-500">
                        Filtreye uyan mesaj yok.
                      </td></tr>
                    )}
                    {deliveries.map((d) => {
                      const sm = STATUS_META[d.status] || STATUS_META.pending;
                      const SIcon = sm.icon;
                      const replayable = d.status === 'failed' || d.status === 'dead_letter';
                      return (
                        <tr key={d.id} className="border-b hover:bg-slate-50">
                          <td className="p-2">
                            {replayable ? (
                              <input
                                type="checkbox"
                                aria-label={`${d.id} seç`}
                                checked={selected.has(d.id)}
                                onChange={() => toggleSelect(d.id)}
                                className="w-4 h-4"
                              />
                            ) : null}
                          </td>
                          <td className="p-2 text-xs whitespace-nowrap" title={d.created_at}>
                            {fmtTimestamp(d.created_at)}
                          </td>
                          <td className="p-2">{d.partner_code}</td>
                          <td className="p-2 text-xs max-w-[260px] truncate" title={d.message_type}>
                            {shortMsg(d.message_type)}
                          </td>
                          <td className="p-2 text-xs">
                            {d.direction === 'outbound' ? '↗ out' : '↙ in'}
                          </td>
                          <td className="p-2">
                            <StatusBadge intent={sm.intent} icon={SIcon}>
                              {sm.label}{d.dry_run ? ' • dry' : ''}
                            </StatusBadge>
                          </td>
                          <td className="p-2 text-xs">{d.attempts}</td>
                          <td className="p-2 text-right space-x-1 whitespace-nowrap">
                            <Button size="sm" variant="ghost" onClick={() => viewDetail(d.id)} aria-label="Detay">
                              <Eye className="w-3 h-3" />
                            </Button>
                            {replayable && (
                              <Button size="sm" variant="outline" onClick={() => replay(d.id)}>
                                <PlayCircle className="w-3 h-3 mr-1" /> Replay
                              </Button>
                            )}
                          </td>
                        </tr>
                      );
                    })}
                  </tbody>
                </table>
              </div>
            </CardContent>
          </Card>
        </TabsContent>
      </Tabs>

      {/* ───── Editor Dialog (P1 #5) ───── */}
      <Dialog open={!!editing} onOpenChange={(o) => { if (!o) setEditing(null); }}>
        <DialogContent className="max-w-lg max-h-[85vh] overflow-y-auto">
          <DialogHeader>
            <DialogTitle>{editingPartner?.name || ''}</DialogTitle>
            <DialogDescription>
              {t('cm.pages_XchangePage.bu_partner_icin_baglanti_bilgileri_secre')}
            </DialogDescription>
          </DialogHeader>
          {editingPartner && (
            <form onSubmit={(e) => { e.preventDefault(); save(); }} autoComplete="off" className="space-y-3">
              <div className="flex items-center justify-between rounded border p-2">
                <Label className="cursor-pointer">{t('cm.pages_XchangePage.aktif_81c33')}</Label>
                <Switch checked={enabled} onCheckedChange={setEnabled} />
              </div>
              {Object.entries(editingPartner.config_schema || {}).map(([k, meta]) => {
                const isSecret = meta.type === 'secret';
                const isUrl = meta.type === 'url';
                const val = form[k] || '';
                const sshWarn = isUrl && looksPrivate(val);
                return (
                  <div key={k}>
                    <Label htmlFor={`xch-${k}`}>{meta.label || k}</Label>
                    <Input
                      id={`xch-${k}`}
                      type={isSecret ? 'password' : 'text'}
                      value={val}
                      onChange={(e) => setForm((f) => ({ ...f, [k]: e.target.value }))}
                      placeholder={meta.default || ''}
                      autoComplete={isSecret ? 'new-password' : 'off'}
                      autoCorrect="off"
                      autoCapitalize="off"
                      spellCheck={false}
                      data-1p-ignore
                      data-lpignore="true"
                    />
                    {sshWarn && (
                      <p className="text-xs text-rose-700 mt-1">
                        {t('cm.pages_XchangePage.bu_url_ozel_loopback_bir_adres_gibi_goru')}
                      </p>
                    )}
                  </div>
                );
              })}
              <p className="text-xs text-slate-500">
                {t('cm.pages_XchangePage.secret_alanlar_maskelenmis_masked_gorunu')} <strong>{t('cm.pages_XchangePage.mevcut_deger_korunur')}</strong>{t('cm.pages_XchangePage.yeni_bir_kurulumda_tum_zorunlu_alanlar_b')} <strong>dry-run</strong> {t('cm.pages_XchangePage.moduna_duser_mesajlar_log_a_yazilir_dis_')}
              </p>
              <DialogFooter>
                <Button type="button" variant="outline" onClick={() => setEditing(null)}>{t('cm.pages_XchangePage.iptal')}</Button>
                <Button type="submit" disabled={saving}>
                  {saving ? 'Kaydediliyor…' : 'Kaydet'}
                </Button>
              </DialogFooter>
            </form>
          )}
        </DialogContent>
      </Dialog>

      {/* ───── Detail Dialog ───── */}
      <Dialog open={!!detail} onOpenChange={(o) => { if (!o) setDetail(null); }}>
        <DialogContent className="max-w-3xl max-h-[85vh] overflow-y-auto">
          <DialogHeader>
            <DialogTitle className="text-base font-mono break-all">{detail?.message_type}</DialogTitle>
            <DialogDescription>
              {detail?.partner_code} • {STATUS_META[detail?.status]?.label || detail?.status} • deneme: {detail?.attempts}
              {detail?.idempotency_key && (
                <span className="block mt-1 text-xs font-mono text-slate-500">
                  idempotency-key: {detail.idempotency_key}
                </span>
              )}
            </DialogDescription>
          </DialogHeader>
          {detail && (
            <div className="space-y-3 text-sm">
              {detail.last_error && (
                <div>
                  <div className="text-xs font-semibold text-rose-700 uppercase mb-1">{t('cm.pages_XchangePage.son_hata')}</div>
                  <pre className="text-xs bg-rose-50 text-rose-900 rounded p-2 overflow-x-auto whitespace-pre-wrap break-all max-h-48">
                    {detail.last_error}
                  </pre>
                </div>
              )}
              <Section label="Request Excerpt" body={detail.request_excerpt} />
              <Section label="Response Excerpt" body={detail.response_excerpt} />
              <details>
                <summary className="cursor-pointer text-slate-600 text-sm">{t('cm.pages_XchangePage.tam_envelope_secret_alanlar_maskelenmist')}</summary>
                <pre className="text-xs bg-slate-50 rounded p-2 overflow-x-auto mt-1 max-h-72">
                  {JSON.stringify(detail.envelope, null, 2)}
                </pre>
              </details>
              <DialogFooter>
                <Button variant="outline" onClick={() => setDetail(null)}>{t('cm.pages_XchangePage.kapat')}</Button>
              </DialogFooter>
            </div>
          )}
        </DialogContent>
      </Dialog>
    </div>
  );
}

const Section = ({ label, body }) => (
  <div>
    <div className="text-xs font-semibold text-slate-500 uppercase mb-1">{label}</div>
    <pre className="text-xs bg-slate-50 rounded p-2 overflow-x-auto whitespace-pre-wrap break-all max-h-48">
      {body || '—'}
    </pre>
  </div>
);
