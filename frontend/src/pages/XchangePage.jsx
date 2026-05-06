import { useEffect, useMemo, useState } from 'react';
import axios from 'axios';
import { toast } from 'sonner';

import { Card, CardContent, CardDescription, CardHeader, CardTitle } from '@/components/ui/card';
import { Button } from '@/components/ui/button';
import { Badge } from '@/components/ui/badge';
import { Input } from '@/components/ui/input';
import { Label } from '@/components/ui/label';
import { Switch } from '@/components/ui/switch';
import { Tabs, TabsContent, TabsList, TabsTrigger } from '@/components/ui/tabs';
import { confirmDialog } from '@/lib/dialogs';
import {
  Network, CheckCircle2, XCircle, AlertTriangle, Settings2, RefreshCw,
  Server, Globe, Building2, Send, Inbox, Power, Eye,
} from 'lucide-react';

const CATEGORY_META = {
  gds: { label: 'GDS / CRS', icon: Globe, color: 'text-indigo-600' },
  erp: { label: 'ERP / Finance', icon: Building2, color: 'text-emerald-600' },
  generic: { label: 'Generic', icon: Server, color: 'text-slate-600' },
};

const CERT_META = {
  in_development: { label: 'Geliştirmede', cls: 'bg-gray-100 text-gray-700' },
  uat: { label: 'UAT', cls: 'bg-amber-100 text-amber-800' },
  certified: { label: 'Sertifikalı', cls: 'bg-emerald-100 text-emerald-800' },
};

const STATUS_META = {
  delivered: { cls: 'bg-emerald-100 text-emerald-800', icon: CheckCircle2 },
  pending: { cls: 'bg-slate-100 text-slate-700', icon: RefreshCw },
  in_flight: { cls: 'bg-sky-100 text-sky-800', icon: Send },
  failed: { cls: 'bg-amber-100 text-amber-800', icon: AlertTriangle },
  dead_letter: { cls: 'bg-red-100 text-red-800', icon: XCircle },
  skipped: { cls: 'bg-gray-100 text-gray-600', icon: Power },
};

const XchangePage = ({ user, tenant, onLogout }) => {
  const [partners, setPartners] = useState([]);
  const [configs, setConfigs] = useState([]);
  const [deliveries, setDeliveries] = useState([]);
  const [counts, setCounts] = useState({});
  const [loading, setLoading] = useState(true);
  const [editing, setEditing] = useState(null); // partner code
  const [form, setForm] = useState({});
  const [enabled, setEnabled] = useState(true);
  const [saving, setSaving] = useState(false);
  const [detail, setDetail] = useState(null);

  const load = async () => {
    setLoading(true);
    try {
      const [pRes, cRes, dRes] = await Promise.all([
        axios.get('/xchange/partners'),
        axios.get('/xchange/configs'),
        axios.get('/xchange/deliveries?limit=100'),
      ]);
      setPartners(pRes.data.partners);
      setConfigs(cRes.data.configs);
      setDeliveries(dRes.data.deliveries);
      setCounts(dRes.data.counts || {});
    } catch (e) {
      toast.error(e.response?.data?.detail || 'Yüklenemedi');
    } finally {
      setLoading(false);
    }
  };
  useEffect(() => { load(); }, []);

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
      await load();
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
      await load();
    } catch (e) {
      toast.error(e.response?.data?.detail || 'Silinemedi');
    }
  };

  const replay = async (id) => {
    try {
      const r = await axios.post(`/xchange/deliveries/${id}/replay`);
      toast.success(`Replay: ${r.data.status} (deneme #${r.data.attempts})`);
      await load();
    } catch (e) {
      toast.error(e.response?.data?.detail || 'Replay başarısız');
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

  if (loading) {
    return (
      <div className="p-8 text-center text-gray-500">
        <RefreshCw className="w-6 h-6 animate-spin inline mr-2" /> Yükleniyor…
      </div>
    );
  }

  return (
    <>
    <div className="max-w-7xl mx-auto p-4 space-y-4">
      <div className="flex items-start justify-end flex-wrap gap-3">
        <div className="hidden"></div>
        <Button variant="outline" onClick={load}>
          <RefreshCw className="w-4 h-4 mr-2" /> Yenile
        </Button>
      </div>

      <div className="grid grid-cols-2 md:grid-cols-5 gap-3">
        <SummaryCard label="Tanımlı Partner" value={partners.length} />
        <SummaryCard label="Aktif Bağlantı" value={configs.filter((c) => c.enabled).length} />
        <SummaryCard label="Teslim Edildi" value={counts.delivered || 0} cls="text-emerald-600" />
        <SummaryCard label="Hatalı" value={counts.failed || 0} cls="text-amber-600" />
        <SummaryCard label="Dead-Letter" value={counts.dead_letter || 0} cls="text-red-600" />
      </div>

      <Tabs defaultValue="partners">
        <TabsList>
          <TabsTrigger value="partners">Partner'lar</TabsTrigger>
          <TabsTrigger value="messages">Mesaj Akışı</TabsTrigger>
        </TabsList>

        <TabsContent value="partners" className="space-y-3">
          {partners.map((p) => {
            const cfg = cfgByCode[p.code];
            const cat = CATEGORY_META[p.category] || CATEGORY_META.generic;
            const cert = CERT_META[p.cert_status] || CERT_META.in_development;
            const Icon = cat.icon;
            return (
              <Card key={p.code}>
                <CardHeader className="pb-2">
                  <div className="flex items-start justify-between flex-wrap gap-2">
                    <div className="flex items-start gap-3">
                      <div className={`w-10 h-10 rounded-lg bg-slate-50 ${cat.color} flex items-center justify-center`}>
                        <Icon className="w-5 h-5" />
                      </div>
                      <div>
                        <CardTitle className="text-base flex items-center gap-2">
                          {p.name}
                          <Badge variant="outline" className="text-xs">{cat.label}</Badge>
                          <Badge className={`${cert.cls} text-xs border-0`}>{cert.label}</Badge>
                          {cfg?.enabled && (
                            <Badge className="bg-emerald-100 text-emerald-800 border-0 text-xs">
                              <CheckCircle2 className="w-3 h-3 mr-1" /> Aktif
                            </Badge>
                          )}
                        </CardTitle>
                        <CardDescription className="mt-1">{p.description}</CardDescription>
                      </div>
                    </div>
                    <div className="flex gap-2">
                      <Button size="sm" variant="outline" onClick={() => openEditor(p)}>
                        <Settings2 className="w-4 h-4 mr-1" /> Yapılandır
                      </Button>
                      {cfg && (
                        <Button size="sm" variant="ghost" onClick={() => removeConfig(p.code)}>
                          Sil
                        </Button>
                      )}
                    </div>
                  </div>
                </CardHeader>
                <CardContent>
                  <div className="text-xs font-semibold text-gray-500 uppercase tracking-wide mb-2">
                    Yetenek Matrisi
                  </div>
                  <div className="flex flex-wrap gap-1">
                    {p.capabilities.map((c, i) => (
                      <Badge
                        key={i}
                        variant="outline"
                        className="text-[10px] font-mono bg-slate-50"
                        title={`${c.message_type} (${c.direction})`}
                      >
                        {c.direction === 'outbound' ? <Send className="w-2.5 h-2.5 mr-0.5 inline" /> : <Inbox className="w-2.5 h-2.5 mr-0.5 inline" />}
                        {c.message_type.replace('OTA_Hotel', '').replace('Syroce.', '').slice(0, 24)}
                      </Badge>
                    ))}
                  </div>
                </CardContent>
              </Card>
            );
          })}
        </TabsContent>

        <TabsContent value="messages">
          <Card>
            <CardContent className="p-0">
              <div className="overflow-x-auto">
                <table className="w-full text-sm">
                  <thead className="bg-slate-50 border-b">
                    <tr className="text-left">
                      <th className="p-2">Zaman</th>
                      <th className="p-2">Partner</th>
                      <th className="p-2">Mesaj</th>
                      <th className="p-2">Yön</th>
                      <th className="p-2">Durum</th>
                      <th className="p-2">Deneme</th>
                      <th className="p-2 text-right">İşlem</th>
                    </tr>
                  </thead>
                  <tbody>
                    {deliveries.length === 0 && (
                      <tr><td colSpan={7} className="p-6 text-center text-gray-500">
                        Henüz mesaj akışı yok.
                      </td></tr>
                    )}
                    {deliveries.map((d) => {
                      const sm = STATUS_META[d.status] || STATUS_META.pending;
                      const SIcon = sm.icon;
                      return (
                        <tr key={d.id} className="border-b hover:bg-slate-50">
                          <td className="p-2 font-mono text-xs">
                            {d.created_at?.slice(5, 19).replace('T', ' ')}
                          </td>
                          <td className="p-2">{d.partner_code}</td>
                          <td className="p-2 font-mono text-xs">{d.message_type}</td>
                          <td className="p-2 text-xs">
                            {d.direction === 'outbound' ? '↗ out' : '↙ in'}
                          </td>
                          <td className="p-2">
                            <Badge className={`${sm.cls} border-0`}>
                              <SIcon className="w-3 h-3 mr-1" />
                              {d.status}
                              {d.dry_run && ' • dry'}
                            </Badge>
                          </td>
                          <td className="p-2 text-xs">{d.attempts}</td>
                          <td className="p-2 text-right space-x-1">
                            <Button size="sm" variant="ghost" onClick={() => viewDetail(d.id)}>
                              <Eye className="w-3 h-3" />
                            </Button>
                            {(d.status === 'failed' || d.status === 'dead_letter') && (
                              <Button size="sm" variant="outline" onClick={() => replay(d.id)}>
                                Replay
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

      {/* Editor modal */}
      {editing && (() => {
        const partner = partners.find((p) => p.code === editing);
        if (!partner) return null;
        return (
          <div className="fixed inset-0 bg-black/40 z-50 flex items-center justify-center p-4">
            <Card className="w-full max-w-lg">
              <CardHeader>
                <CardTitle>{partner.name}</CardTitle>
                <CardDescription>Bu partner için bağlantı bilgileri</CardDescription>
              </CardHeader>
              <CardContent className="space-y-3">
                <div className="flex items-center justify-between rounded border p-2">
                  <Label className="cursor-pointer">Aktif</Label>
                  <Switch checked={enabled} onCheckedChange={setEnabled} />
                </div>
                {Object.entries(partner.config_schema || {}).map(([k, meta]) => (
                  <div key={k}>
                    <Label>{meta.label || k}</Label>
                    <Input
                      type={meta.type === 'secret' ? 'password' : 'text'}
                      value={form[k] || ''}
                      onChange={(e) => setForm((f) => ({ ...f, [k]: e.target.value }))}
                      placeholder={meta.default || ''}
                    />
                  </div>
                ))}
                <p className="text-xs text-gray-500">
                  Boş bırakılan bağlantı alanları için adapter dry-run modunda çalışır
                  (mesajlar üretilir ve log'a yazılır, dış servise gönderilmez).
                </p>
                <div className="flex justify-end gap-2 pt-2">
                  <Button variant="ghost" onClick={() => setEditing(null)}>İptal</Button>
                  <Button onClick={save} disabled={saving}>
                    {saving ? 'Kaydediliyor…' : 'Kaydet'}
                  </Button>
                </div>
              </CardContent>
            </Card>
          </div>
        );
      })()}

      {/* Detail modal */}
      {detail && (
        <div className="fixed inset-0 bg-black/40 z-50 flex items-center justify-center p-4"
             onClick={() => setDetail(null)}>
          <Card className="w-full max-w-3xl max-h-[80vh] overflow-y-auto" onClick={(e) => e.stopPropagation()}>
            <CardHeader>
              <CardTitle className="text-base font-mono">{detail.message_type}</CardTitle>
              <CardDescription>
                {detail.partner_code} • {detail.status} • deneme: {detail.attempts}
                {detail.last_error && ` • hata: ${detail.last_error}`}
              </CardDescription>
            </CardHeader>
            <CardContent className="space-y-3 text-sm">
              <Section label="Request Excerpt" body={detail.request_excerpt} />
              <Section label="Response Excerpt" body={detail.response_excerpt} />
              <details>
                <summary className="cursor-pointer text-gray-600">Tam Envelope</summary>
                <pre className="text-xs bg-slate-50 rounded p-2 overflow-x-auto mt-1">
                  {JSON.stringify(detail.envelope, null, 2)}
                </pre>
              </details>
              <div className="text-right">
                <Button variant="ghost" onClick={() => setDetail(null)}>Kapat</Button>
              </div>
            </CardContent>
          </Card>
        </div>
      )}
    </div>
    </>
  );
};

const SummaryCard = ({ label, value, cls = 'text-gray-900' }) => (
  <Card>
    <CardContent className="p-4">
      <div className="text-xs text-gray-500">{label}</div>
      <div className={`text-2xl font-bold ${cls}`}>{value}</div>
    </CardContent>
  </Card>
);

const Section = ({ label, body }) => (
  <div>
    <div className="text-xs font-semibold text-gray-500 uppercase mb-1">{label}</div>
    <pre className="text-xs bg-slate-50 rounded p-2 overflow-x-auto whitespace-pre-wrap break-all">
      {body || '—'}
    </pre>
  </div>
);

export default XchangePage;
