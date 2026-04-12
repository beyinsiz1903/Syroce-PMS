import React, { useState, useEffect, useCallback } from 'react';
import Layout from '@/components/Layout';
import { Card, CardContent } from '../components/ui/card';
import { Badge } from '../components/ui/badge';
import { Button } from '../components/ui/button';
import { Tabs, TabsContent, TabsList, TabsTrigger } from '../components/ui/tabs';
import { Input } from '../components/ui/input';
import { Label } from '../components/ui/label';
import { Textarea } from '../components/ui/textarea';
import {
  Select,
  SelectContent,
  SelectItem,
  SelectTrigger,
  SelectValue,
} from '../components/ui/select';
import {
  Dialog,
  DialogContent,
  DialogHeader,
  DialogTitle,
  DialogFooter,
} from '../components/ui/dialog';
import { Switch } from '../components/ui/switch';
import {
  Mail, MessageSquare, Phone, Shield, RefreshCw, Send,
  Settings, FileText, BarChart3, Loader2, Plus, Trash2,
  CheckCircle2, XCircle, Clock, AlertTriangle, Eye,
  Pencil, TestTube, ArrowRight, Zap, Play, Power, Timer, Bell,
} from 'lucide-react';
import { toast } from 'sonner';

const API = "";
const headers = () => ({
  Authorization: `Bearer ${localStorage.getItem('token')}`,
  'Content-Type': 'application/json',
});
const get = async (p) => { const r = await fetch(`${API}${p}`, { headers: headers() }); return r.json(); };
const post = async (p, b) => { const r = await fetch(`${API}${p}`, { method: 'POST', headers: headers(), body: JSON.stringify(b) }); return r.json(); };
const put = async (p, b) => { const r = await fetch(`${API}${p}`, { method: 'PUT', headers: headers(), body: JSON.stringify(b) }); return r.json(); };
const del = async (p) => { const r = await fetch(`${API}${p}`, { method: 'DELETE', headers: headers() }); return r.json(); };

const STATUS_COLORS = {
  sent: 'bg-emerald-100 text-emerald-800',
  delivered: 'bg-emerald-100 text-emerald-800',
  failed: 'bg-red-100 text-red-800',
  bounced: 'bg-red-100 text-red-800',
  queued: 'bg-amber-100 text-amber-800',
  sending: 'bg-blue-100 text-blue-800',
};

const STATUS_LABELS = {
  sent: 'Gonderildi',
  delivered: 'Teslim Edildi',
  failed: 'Basarisiz',
  queued: 'Kuyrukta',
  sending: 'Gonderiliyor',
  bounced: 'Geri Dondu',
};

const CHANNEL_ICONS = { email: Mail, whatsapp: MessageSquare };
const CHANNEL_LABELS = { email: 'Email', whatsapp: 'WhatsApp' };

const CATEGORY_LABELS = {
  hosgeldiniz: 'Hos Geldiniz',
  yol_tarifi: 'Yol Tarifi',
  tesis_bilgi: 'Tesis Bilgileri',
  fatura: 'Fatura',
  kampanya: 'Kampanya',
  puan_degerlendirme: 'Degerlendirme',
  checkout: 'Check-out',
  rezervasyon_onay: 'Rezervasyon Onay',
  iletisim: 'Iletisim',
  genel: 'Genel',
};


// ═══════════════════════════════════════════════
// Settings Tab
// ═══════════════════════════════════════════════
function SettingsTab() {
  const [settings, setSettings] = useState(null);
  const [loading, setLoading] = useState(true);
  const [saving, setSaving] = useState(false);
  const [emailForm, setEmailForm] = useState({
    smtp_host: '', smtp_port: 587, smtp_username: '', smtp_password: '',
    from_email: '', from_name: 'Otel', use_tls: true, is_sandbox: true, enabled: true,
  });
  const [waForm, setWaForm] = useState({
    access_token: '', phone_number_id: '', business_name: '', is_sandbox: true, enabled: true,
  });

  const load = useCallback(async () => {
    setLoading(true);
    const d = await get('/api/messaging-center/settings');
    setSettings(d);
    if (d.email?.credentials) {
      setEmailForm(prev => ({
        ...prev,
        smtp_host: d.email.credentials.smtp_host || '',
        smtp_port: d.email.credentials.smtp_port || 587,
        from_email: d.email.credentials.from_email || '',
        from_name: d.email.credentials.from_name || 'Otel',
        use_tls: d.email.credentials.use_tls !== false,
        is_sandbox: d.email.is_sandbox,
        enabled: d.email.enabled,
      }));
    }
    if (d.whatsapp?.credentials) {
      setWaForm(prev => ({
        ...prev,
        phone_number_id: d.whatsapp.credentials.phone_number_id || '',
        business_name: d.whatsapp.credentials.business_name || '',
        is_sandbox: d.whatsapp.is_sandbox,
        enabled: d.whatsapp.enabled,
      }));
    }
    setLoading(false);
  }, []);
  useEffect(() => { load(); }, [load]);

  const saveEmail = async () => {
    setSaving(true);
    const res = await post('/api/messaging-center/settings/email', emailForm);
    if (res.success) toast.success(`Email ayarlari ${res.action === 'created' ? 'olusturuldu' : 'guncellendi'}`);
    else toast.error('Kaydetme hatasi');
    setSaving(false);
    load();
  };

  const saveWhatsApp = async () => {
    setSaving(true);
    const res = await post('/api/messaging-center/settings/whatsapp', waForm);
    if (res.success) toast.success(`WhatsApp ayarlari ${res.action === 'created' ? 'olusturuldu' : 'guncellendi'}`);
    else toast.error('Kaydetme hatasi');
    setSaving(false);
    load();
  };

  const testConnection = async () => {
    const res = await post('/api/messaging-center/settings/test-connection', {});
    if (res.results) {
      res.results.forEach(r => {
        if (r.status === 'healthy') toast.success(`${r.provider_type}: Baglanti basarili`);
        else toast.error(`${r.provider_type}: ${r.error || 'Baglanti hatasi'}`);
      });
    }
  };

  if (loading) return <div className="flex items-center justify-center py-12"><Loader2 className="h-6 w-6 animate-spin text-muted-foreground" /></div>;

  return (
    <div className="space-y-6" data-testid="settings-tab">
      {/* Email SMTP Settings */}
      <Card>
        <CardContent className="pt-6">
          <div className="flex items-center justify-between mb-4">
            <div className="flex items-center gap-2">
              <Mail className="h-5 w-5 text-blue-600" />
              <h3 className="text-lg font-semibold">Email (SMTP) Ayarlari</h3>
            </div>
            <div className="flex items-center gap-2">
              {settings?.email && (
                <Badge variant={settings.email.health_status === 'healthy' ? 'default' : 'destructive'}>
                  {settings.email.health_status === 'healthy' ? 'Bagli' : 'Baglanti Yok'}
                </Badge>
              )}
              {settings?.email?.is_sandbox && <Badge variant="outline">Sandbox</Badge>}
            </div>
          </div>
          <div className="grid grid-cols-1 md:grid-cols-2 gap-4">
            <div>
              <Label>SMTP Sunucu</Label>
              <Input data-testid="smtp-host" placeholder="smtp.gmail.com" value={emailForm.smtp_host}
                onChange={e => setEmailForm(p => ({ ...p, smtp_host: e.target.value }))} />
            </div>
            <div>
              <Label>Port</Label>
              <Input data-testid="smtp-port" type="number" value={emailForm.smtp_port}
                onChange={e => setEmailForm(p => ({ ...p, smtp_port: parseInt(e.target.value) || 587 }))} />
            </div>
            <div>
              <Label>Kullanici Adi</Label>
              <Input data-testid="smtp-username" placeholder="email@domain.com" value={emailForm.smtp_username}
                onChange={e => setEmailForm(p => ({ ...p, smtp_username: e.target.value }))} />
            </div>
            <div>
              <Label>Sifre</Label>
              <Input data-testid="smtp-password" type="password" placeholder="********" value={emailForm.smtp_password}
                onChange={e => setEmailForm(p => ({ ...p, smtp_password: e.target.value }))} />
            </div>
            <div>
              <Label>Gonderen Email</Label>
              <Input data-testid="smtp-from-email" placeholder="info@oteliniz.com" value={emailForm.from_email}
                onChange={e => setEmailForm(p => ({ ...p, from_email: e.target.value }))} />
            </div>
            <div>
              <Label>Gonderen Adi</Label>
              <Input data-testid="smtp-from-name" placeholder="Otel Adiniz" value={emailForm.from_name}
                onChange={e => setEmailForm(p => ({ ...p, from_name: e.target.value }))} />
            </div>
          </div>
          <div className="flex items-center gap-6 mt-4">
            <div className="flex items-center gap-2">
              <Switch checked={emailForm.use_tls} onCheckedChange={v => setEmailForm(p => ({ ...p, use_tls: v }))} />
              <Label>TLS</Label>
            </div>
            <div className="flex items-center gap-2">
              <Switch data-testid="smtp-sandbox" checked={emailForm.is_sandbox} onCheckedChange={v => setEmailForm(p => ({ ...p, is_sandbox: v }))} />
              <Label>Sandbox Modu</Label>
            </div>
            <div className="flex items-center gap-2">
              <Switch checked={emailForm.enabled} onCheckedChange={v => setEmailForm(p => ({ ...p, enabled: v }))} />
              <Label>Aktif</Label>
            </div>
          </div>
          <div className="flex gap-2 mt-4">
            <Button data-testid="save-email-btn" onClick={saveEmail} disabled={saving}>
              {saving ? <Loader2 className="h-4 w-4 animate-spin mr-1" /> : null} Kaydet
            </Button>
          </div>
          <p className="text-xs text-muted-foreground mt-2">
            Sandbox modunda gercek email gonderilmez, simule edilir. API bilgilerinizi girdikten sonra sandbox'u kapatin.
          </p>
        </CardContent>
      </Card>

      {/* WhatsApp Settings */}
      <Card>
        <CardContent className="pt-6">
          <div className="flex items-center justify-between mb-4">
            <div className="flex items-center gap-2">
              <MessageSquare className="h-5 w-5 text-green-600" />
              <h3 className="text-lg font-semibold">WhatsApp Business API Ayarlari</h3>
            </div>
            <div className="flex items-center gap-2">
              {settings?.whatsapp && (
                <Badge variant={settings.whatsapp.health_status === 'healthy' ? 'default' : 'destructive'}>
                  {settings.whatsapp.health_status === 'healthy' ? 'Bagli' : 'Baglanti Yok'}
                </Badge>
              )}
              {settings?.whatsapp?.is_sandbox && <Badge variant="outline">Sandbox</Badge>}
            </div>
          </div>
          <div className="grid grid-cols-1 md:grid-cols-2 gap-4">
            <div>
              <Label>Access Token</Label>
              <Input data-testid="wa-access-token" type="password" placeholder="Meta Business API Token" value={waForm.access_token}
                onChange={e => setWaForm(p => ({ ...p, access_token: e.target.value }))} />
            </div>
            <div>
              <Label>Phone Number ID</Label>
              <Input data-testid="wa-phone-id" placeholder="Meta Phone Number ID" value={waForm.phone_number_id}
                onChange={e => setWaForm(p => ({ ...p, phone_number_id: e.target.value }))} />
            </div>
            <div>
              <Label>Isletme Adi</Label>
              <Input data-testid="wa-business-name" placeholder="Otel WhatsApp" value={waForm.business_name}
                onChange={e => setWaForm(p => ({ ...p, business_name: e.target.value }))} />
            </div>
          </div>
          <div className="flex items-center gap-6 mt-4">
            <div className="flex items-center gap-2">
              <Switch data-testid="wa-sandbox" checked={waForm.is_sandbox} onCheckedChange={v => setWaForm(p => ({ ...p, is_sandbox: v }))} />
              <Label>Sandbox Modu</Label>
            </div>
            <div className="flex items-center gap-2">
              <Switch checked={waForm.enabled} onCheckedChange={v => setWaForm(p => ({ ...p, enabled: v }))} />
              <Label>Aktif</Label>
            </div>
          </div>
          <div className="flex gap-2 mt-4">
            <Button data-testid="save-whatsapp-btn" onClick={saveWhatsApp} disabled={saving}>
              {saving ? <Loader2 className="h-4 w-4 animate-spin mr-1" /> : null} Kaydet
            </Button>
          </div>
          <p className="text-xs text-muted-foreground mt-2">
            Meta Business panelinden WhatsApp Business API token ve Phone Number ID bilgilerinizi alin.
            Sandbox modunda gercek mesaj gonderilmez.
          </p>
        </CardContent>
      </Card>

      {/* Test Connection */}
      <div className="flex gap-2">
        <Button data-testid="test-connection-btn" variant="outline" onClick={testConnection}>
          <TestTube className="h-4 w-4 mr-1" /> Baglanti Testi
        </Button>
      </div>
    </div>
  );
}


// ═══════════════════════════════════════════════
// Templates Tab
// ═══════════════════════════════════════════════
function TemplatesTab() {
  const [templates, setTemplates] = useState([]);
  const [loading, setLoading] = useState(true);
  const [filterChannel, setFilterChannel] = useState('all');
  const [showCreate, setShowCreate] = useState(false);
  const [editTemplate, setEditTemplate] = useState(null);
  const [form, setForm] = useState({
    name: '', category: 'genel', channel: 'whatsapp', subject: '', body_template: '', variables: [],
  });

  const load = useCallback(async () => {
    setLoading(true);
    const params = filterChannel !== 'all' ? `?channel=${filterChannel}` : '';
    const d = await get(`/api/messaging-center/templates${params}`);
    setTemplates(d.templates || []);
    setLoading(false);
  }, [filterChannel]);
  useEffect(() => { load(); }, [load]);

  const handleCreate = async () => {
    const vars = form.body_template.match(/\{\{(\w+)\}\}/g)?.map(v => v.replace(/\{\{|\}\}/g, '')) || [];
    const res = await post('/api/messaging-center/templates', { ...form, variables: vars });
    if (res.id) {
      toast.success('Sablon olusturuldu');
      setShowCreate(false);
      setForm({ name: '', category: 'genel', channel: 'whatsapp', subject: '', body_template: '', variables: [] });
      load();
    }
  };

  const handleUpdate = async () => {
    if (!editTemplate) return;
    const vars = form.body_template.match(/\{\{(\w+)\}\}/g)?.map(v => v.replace(/\{\{|\}\}/g, '')) || [];
    await put(`/api/messaging-center/templates/${editTemplate.id}`, {
      name: form.name, subject: form.subject, body_template: form.body_template, variables: vars, category: form.category,
    });
    toast.success('Sablon guncellendi');
    setEditTemplate(null);
    load();
  };

  const handleDelete = async (id) => {
    if (!confirm('Bu sablonu silmek istediginizden emin misiniz?')) return;
    await del(`/api/messaging-center/templates/${id}`);
    toast.success('Sablon silindi');
    load();
  };

  const openEdit = (t) => {
    setForm({ name: t.name, category: t.category, channel: t.channel, subject: t.subject || '', body_template: t.body_template, variables: t.variables || [] });
    setEditTemplate(t);
  };

  const openCreate = () => {
    setForm({ name: '', category: 'genel', channel: 'whatsapp', subject: '', body_template: '', variables: [] });
    setShowCreate(true);
  };

  if (loading) return <div className="flex items-center justify-center py-12"><Loader2 className="h-6 w-6 animate-spin" /></div>;

  return (
    <div className="space-y-4" data-testid="templates-tab">
      <div className="flex justify-between items-center">
        <div className="flex gap-1">
          {['all', 'email', 'whatsapp'].map(f => (
            <Button key={f} size="sm" variant={filterChannel === f ? 'default' : 'outline'}
              onClick={() => setFilterChannel(f)}>
              {f === 'all' ? 'Tumu' : CHANNEL_LABELS[f]}
            </Button>
          ))}
        </div>
        <Button data-testid="create-template-btn" size="sm" onClick={openCreate}>
          <Plus className="h-4 w-4 mr-1" /> Yeni Sablon
        </Button>
      </div>

      {templates.length === 0 ? (
        <Card><CardContent className="py-8 text-center text-muted-foreground">
          <FileText className="h-8 w-8 mx-auto mb-2 opacity-50" />
          <p>Sablon bulunamadi.</p>
        </CardContent></Card>
      ) : (
        <div className="grid gap-3">
          {templates.map(t => {
            const Icon = CHANNEL_ICONS[t.channel] || Mail;
            return (
              <Card key={t.id} data-testid={`template-${t.id}`}>
                <CardContent className="py-4">
                  <div className="flex items-start justify-between">
                    <div className="flex items-start gap-3">
                      <div className={`p-2 rounded-lg ${t.channel === 'whatsapp' ? 'bg-green-50' : 'bg-blue-50'}`}>
                        <Icon className={`h-4 w-4 ${t.channel === 'whatsapp' ? 'text-green-600' : 'text-blue-600'}`} />
                      </div>
                      <div>
                        <p className="font-medium">{t.name}</p>
                        <p className="text-xs text-muted-foreground mt-0.5">
                          {CHANNEL_LABELS[t.channel]} · {CATEGORY_LABELS[t.category] || t.category}
                          {t.subject && <span> · {t.subject}</span>}
                        </p>
                        <p className="text-xs text-muted-foreground mt-1 line-clamp-2">{t.body_template?.replace(/<[^>]*>/g, '').substring(0, 120)}...</p>
                        {t.variables?.length > 0 && (
                          <div className="flex flex-wrap gap-1 mt-1.5">
                            {t.variables.map(v => (
                              <span key={v} className="text-[10px] px-1.5 py-0.5 bg-slate-100 rounded">{`{{${v}}}`}</span>
                            ))}
                          </div>
                        )}
                      </div>
                    </div>
                    <div className="flex gap-1">
                      <Button size="sm" variant="ghost" onClick={() => openEdit(t)}><Pencil className="h-3.5 w-3.5" /></Button>
                      <Button size="sm" variant="ghost" onClick={() => handleDelete(t.id)}><Trash2 className="h-3.5 w-3.5 text-red-500" /></Button>
                    </div>
                  </div>
                </CardContent>
              </Card>
            );
          })}
        </div>
      )}

      {/* Create/Edit Dialog */}
      <Dialog open={showCreate || !!editTemplate} onOpenChange={v => { if (!v) { setShowCreate(false); setEditTemplate(null); } }}>
        <DialogContent className="max-w-lg">
          <DialogHeader>
            <DialogTitle>{editTemplate ? 'Sablonu Duzenle' : 'Yeni Sablon Olustur'}</DialogTitle>
          </DialogHeader>
          <div className="space-y-3">
            <div>
              <Label>Sablon Adi</Label>
              <Input data-testid="template-name" value={form.name} onChange={e => setForm(p => ({ ...p, name: e.target.value }))} placeholder="Hos Geldiniz Mesaji" />
            </div>
            <div className="grid grid-cols-2 gap-3">
              <div>
                <Label>Kanal</Label>
                <Select value={form.channel} onValueChange={v => setForm(p => ({ ...p, channel: v }))}>
                  <SelectTrigger data-testid="template-channel"><SelectValue /></SelectTrigger>
                  <SelectContent>
                    <SelectItem value="whatsapp">WhatsApp</SelectItem>
                    <SelectItem value="email">Email</SelectItem>
                  </SelectContent>
                </Select>
              </div>
              <div>
                <Label>Kategori</Label>
                <Select value={form.category} onValueChange={v => setForm(p => ({ ...p, category: v }))}>
                  <SelectTrigger data-testid="template-category"><SelectValue /></SelectTrigger>
                  <SelectContent>
                    {Object.entries(CATEGORY_LABELS).map(([k, v]) => (
                      <SelectItem key={k} value={k}>{v}</SelectItem>
                    ))}
                  </SelectContent>
                </Select>
              </div>
            </div>
            {form.channel === 'email' && (
              <div>
                <Label>Konu</Label>
                <Input data-testid="template-subject" value={form.subject} onChange={e => setForm(p => ({ ...p, subject: e.target.value }))} placeholder="Rezervasyon Onayiniz" />
              </div>
            )}
            <div>
              <Label>Mesaj Icerigi</Label>
              <Textarea data-testid="template-body" className="min-h-[120px]" value={form.body_template}
                onChange={e => setForm(p => ({ ...p, body_template: e.target.value }))}
                placeholder="Merhaba {{misafir_adi}}, otelemize hos geldiniz!" />
              <p className="text-xs text-muted-foreground mt-1">Degisken kullanimi: {'{{degisken_adi}}'}</p>
            </div>
          </div>
          <DialogFooter>
            <Button variant="outline" onClick={() => { setShowCreate(false); setEditTemplate(null); }}>Iptal</Button>
            <Button data-testid="template-save-btn" onClick={editTemplate ? handleUpdate : handleCreate}>
              {editTemplate ? 'Guncelle' : 'Olustur'}
            </Button>
          </DialogFooter>
        </DialogContent>
      </Dialog>
    </div>
  );
}


// ═══════════════════════════════════════════════
// Send Message Tab
// ═══════════════════════════════════════════════
function SendTab() {
  const [templates, setTemplates] = useState([]);
  const [sending, setSending] = useState(false);
  const [form, setForm] = useState({
    channel: 'whatsapp', recipient: '', template_id: '', subject: '', body: '', use_case: '',
  });
  const [variables, setVariables] = useState({});
  const [selectedTemplate, setSelectedTemplate] = useState(null);

  useEffect(() => {
    (async () => {
      const d = await get('/api/messaging-center/templates');
      setTemplates(d.templates || []);
    })();
  }, []);

  const filteredTemplates = templates.filter(t => t.channel === form.channel);

  const selectTemplate = (templateId) => {
    const tmpl = templates.find(t => t.id === templateId);
    setSelectedTemplate(tmpl);
    if (tmpl) {
      setForm(p => ({ ...p, template_id: templateId, subject: tmpl.subject || '', body: tmpl.body_template || '' }));
      const vars = {};
      (tmpl.variables || []).forEach(v => { vars[v] = ''; });
      setVariables(vars);
    }
  };

  const handleSend = async () => {
    if (!form.recipient) { toast.error('Alici gerekli'); return; }
    if (!form.body && !form.template_id) { toast.error('Mesaj icerigi veya sablon secin'); return; }
    setSending(true);
    const payload = {
      channel: form.channel,
      recipient: form.recipient,
      subject: form.subject || undefined,
      body: form.body || undefined,
      template_id: form.template_id || undefined,
      variables: Object.keys(variables).length > 0 ? variables : undefined,
      use_case: form.use_case || undefined,
    };
    const res = await post('/api/messaging-center/send', payload);
    if (res.success) {
      toast.success(`Mesaj gonderildi (${form.channel})`);
      setForm(p => ({ ...p, recipient: '', body: '', template_id: '', subject: '' }));
      setVariables({});
      setSelectedTemplate(null);
    } else {
      toast.error(res.error || 'Gonderim hatasi');
    }
    setSending(false);
  };

  return (
    <div className="space-y-4" data-testid="send-tab">
      <Card>
        <CardContent className="pt-6 space-y-4">
          <div className="grid grid-cols-1 md:grid-cols-2 gap-4">
            <div>
              <Label>Kanal</Label>
              <Select value={form.channel} onValueChange={v => { setForm(p => ({ ...p, channel: v, template_id: '' })); setSelectedTemplate(null); setVariables({}); }}>
                <SelectTrigger data-testid="send-channel"><SelectValue /></SelectTrigger>
                <SelectContent>
                  <SelectItem value="whatsapp">WhatsApp</SelectItem>
                  <SelectItem value="email">Email</SelectItem>
                </SelectContent>
              </Select>
            </div>
            <div>
              <Label>{form.channel === 'email' ? 'Email Adresi' : 'Telefon Numarasi'}</Label>
              <Input data-testid="send-recipient" value={form.recipient}
                onChange={e => setForm(p => ({ ...p, recipient: e.target.value }))}
                placeholder={form.channel === 'email' ? 'misafir@email.com' : '+905xxxxxxxxx'} />
            </div>
          </div>

          <div>
            <Label>Sablon (Opsiyonel)</Label>
            <Select value={form.template_id} onValueChange={selectTemplate}>
              <SelectTrigger data-testid="send-template"><SelectValue placeholder="Sablon secin veya serbest yazin" /></SelectTrigger>
              <SelectContent>
                <SelectItem value="none">Sablon kullanma</SelectItem>
                {filteredTemplates.map(t => (
                  <SelectItem key={t.id} value={t.id}>{t.name} ({CATEGORY_LABELS[t.category] || t.category})</SelectItem>
                ))}
              </SelectContent>
            </Select>
          </div>

          {selectedTemplate && selectedTemplate.variables?.length > 0 && (
            <div className="bg-slate-50 p-3 rounded-lg space-y-2">
              <Label className="text-sm font-medium">Degiskenler</Label>
              <div className="grid grid-cols-1 md:grid-cols-2 gap-2">
                {selectedTemplate.variables.map(v => (
                  <div key={v}>
                    <Label className="text-xs">{v}</Label>
                    <Input size="sm" placeholder={v} value={variables[v] || ''}
                      onChange={e => setVariables(p => ({ ...p, [v]: e.target.value }))} />
                  </div>
                ))}
              </div>
            </div>
          )}

          {form.channel === 'email' && (
            <div>
              <Label>Konu</Label>
              <Input data-testid="send-subject" value={form.subject}
                onChange={e => setForm(p => ({ ...p, subject: e.target.value }))} placeholder="Email konusu" />
            </div>
          )}

          <div>
            <Label>Mesaj Icerigi</Label>
            <Textarea data-testid="send-body" className="min-h-[100px]" value={form.body}
              onChange={e => setForm(p => ({ ...p, body: e.target.value }))}
              placeholder={form.channel === 'email' ? 'HTML veya duz metin...' : 'Mesajinizi yazin...'} />
          </div>

          <Button data-testid="send-message-btn" className="w-full" onClick={handleSend} disabled={sending}>
            {sending ? <Loader2 className="h-4 w-4 animate-spin mr-2" /> : <Send className="h-4 w-4 mr-2" />}
            Mesaj Gonder
          </Button>
        </CardContent>
      </Card>
    </div>
  );
}


// ═══════════════════════════════════════════════
// Delivery Logs Tab
// ═══════════════════════════════════════════════
function DeliveryLogsTab() {
  const [logs, setLogs] = useState([]);
  const [loading, setLoading] = useState(true);
  const [filter, setFilter] = useState('all');
  const [channelFilter, setChannelFilter] = useState('all');

  const load = useCallback(async () => {
    setLoading(true);
    const params = new URLSearchParams();
    if (filter !== 'all') params.set('status', filter);
    if (channelFilter !== 'all') params.set('channel', channelFilter);
    const q = params.toString() ? `?${params.toString()}` : '';
    const d = await get(`/api/messaging-center/delivery-logs${q}`);
    setLogs(d.logs || []);
    setLoading(false);
  }, [filter, channelFilter]);
  useEffect(() => { load(); }, [load]);

  const retry = async (id) => {
    const res = await post(`/api/messaging-center/retry/${id}`, {});
    if (res.success) toast.success('Yeniden gonderildi');
    else toast.error(res.error || 'Yeniden gonderim hatasi');
    load();
  };

  return (
    <div className="space-y-4" data-testid="delivery-logs-tab">
      <div className="flex flex-wrap gap-2 justify-between items-center">
        <div className="flex gap-1">
          {['all', 'sent', 'delivered', 'failed', 'queued'].map(f => (
            <Button key={f} size="sm" variant={filter === f ? 'default' : 'outline'} onClick={() => setFilter(f)}>
              {f === 'all' ? 'Tumu' : STATUS_LABELS[f] || f}
            </Button>
          ))}
        </div>
        <div className="flex gap-1">
          {['all', 'email', 'whatsapp'].map(f => (
            <Button key={f} size="sm" variant={channelFilter === f ? 'default' : 'outline'} onClick={() => setChannelFilter(f)}>
              {f === 'all' ? 'Tum Kanallar' : CHANNEL_LABELS[f]}
            </Button>
          ))}
        </div>
      </div>
      {loading ? (
        <div className="flex items-center justify-center py-12"><Loader2 className="h-6 w-6 animate-spin" /></div>
      ) : logs.length === 0 ? (
        <Card><CardContent className="py-8 text-center text-muted-foreground">Kayit yok</CardContent></Card>
      ) : (
        <div className="space-y-2">
          {logs.map(l => {
            const Icon = CHANNEL_ICONS[l.channel] || Mail;
            return (
              <Card key={l.id} data-testid={`delivery-log-${l.id}`}>
                <CardContent className="py-3 flex items-center gap-3">
                  <div className={`p-1.5 rounded ${l.channel === 'whatsapp' ? 'bg-green-50' : 'bg-blue-50'}`}>
                    <Icon className={`h-4 w-4 ${l.channel === 'whatsapp' ? 'text-green-600' : 'text-blue-600'}`} />
                  </div>
                  <div className="flex-1 min-w-0">
                    <p className="text-sm font-medium truncate">{l.recipient}</p>
                    <p className="text-xs text-muted-foreground truncate">
                      {CATEGORY_LABELS[l.use_case] || l.use_case || l.channel}
                      {l.subject && ` · ${l.subject}`}
                      {' · '}
                      {new Date(l.created_at).toLocaleString('tr-TR')}
                    </p>
                  </div>
                  <Badge className={STATUS_COLORS[l.status] || 'bg-gray-100'}>{STATUS_LABELS[l.status] || l.status}</Badge>
                  {l.status === 'failed' && l.retry_count < (l.max_retries || 3) && (
                    <Button size="sm" variant="ghost" onClick={() => retry(l.id)} title="Yeniden gonder">
                      <RefreshCw className="h-3 w-3" />
                    </Button>
                  )}
                </CardContent>
              </Card>
            );
          })}
        </div>
      )}
    </div>
  );
}


// ═══════════════════════════════════════════════
// Metrics Tab
// ═══════════════════════════════════════════════
function MetricsTab() {
  const [metrics, setMetrics] = useState(null);
  useEffect(() => {
    (async () => { const d = await get('/api/messaging-center/metrics?days=30'); setMetrics(d); })();
  }, []);

  if (!metrics) return <div className="flex items-center justify-center py-12"><Loader2 className="h-6 w-6 animate-spin" /></div>;

  const channels = Object.entries(metrics.metrics_by_channel || {});
  const totalSent = channels.reduce((a, [, s]) => a + (s.sent || 0) + (s.delivered || 0), 0);
  const totalFailed = channels.reduce((a, [, s]) => a + (s.failed || 0), 0);
  const successRate = metrics.total_messages > 0 ? Math.round((totalSent / metrics.total_messages) * 100) : 0;

  return (
    <div className="space-y-4" data-testid="metrics-tab">
      <div className="grid grid-cols-2 md:grid-cols-4 gap-3">
        <Card>
          <CardContent className="py-4 text-center">
            <p className="text-2xl font-bold">{metrics.total_messages}</p>
            <p className="text-xs text-muted-foreground">Toplam Mesaj</p>
          </CardContent>
        </Card>
        <Card>
          <CardContent className="py-4 text-center">
            <p className="text-2xl font-bold text-emerald-600">{totalSent}</p>
            <p className="text-xs text-muted-foreground">Basarili</p>
          </CardContent>
        </Card>
        <Card>
          <CardContent className="py-4 text-center">
            <p className="text-2xl font-bold text-red-600">{totalFailed}</p>
            <p className="text-xs text-muted-foreground">Basarisiz</p>
          </CardContent>
        </Card>
        <Card>
          <CardContent className="py-4 text-center">
            <p className="text-2xl font-bold">%{successRate}</p>
            <p className="text-xs text-muted-foreground">Basari Orani</p>
          </CardContent>
        </Card>
      </div>

      <h3 className="text-base font-semibold mt-4">Kanal Bazli Dagilim</h3>
      <div className="grid grid-cols-1 md:grid-cols-2 gap-3">
        {channels.map(([ch, stats]) => {
          const Icon = CHANNEL_ICONS[ch] || Mail;
          const total = Object.values(stats).reduce((a, b) => a + b, 0);
          return (
            <Card key={ch}>
              <CardContent className="py-4">
                <div className="flex items-center gap-2 mb-3">
                  <Icon className={`h-5 w-5 ${ch === 'whatsapp' ? 'text-green-600' : 'text-blue-600'}`} />
                  <span className="font-medium">{CHANNEL_LABELS[ch] || ch.toUpperCase()}</span>
                  <Badge variant="outline" className="ml-auto">{total} mesaj</Badge>
                </div>
                <div className="grid grid-cols-3 gap-2 text-center">
                  <div className="bg-emerald-50 rounded p-2">
                    <p className="text-sm font-bold text-emerald-700">{(stats.sent || 0) + (stats.delivered || 0)}</p>
                    <p className="text-[10px] text-emerald-600">Gonderildi</p>
                  </div>
                  <div className="bg-red-50 rounded p-2">
                    <p className="text-sm font-bold text-red-700">{stats.failed || 0}</p>
                    <p className="text-[10px] text-red-600">Basarisiz</p>
                  </div>
                  <div className="bg-amber-50 rounded p-2">
                    <p className="text-sm font-bold text-amber-700">{stats.queued || 0}</p>
                    <p className="text-[10px] text-amber-600">Kuyrukta</p>
                  </div>
                </div>
              </CardContent>
            </Card>
          );
        })}
      </div>
      <p className="text-xs text-muted-foreground">Son {metrics.period_days} gunluk veriler.</p>
    </div>
  );
}


// ═══════════════════════════════════════════════
// Automation Tab
// ═══════════════════════════════════════════════
const TRIGGER_LABELS = {
  booking_confirmed: 'Rezervasyon Onaylandi',
  pre_arrival: 'Check-in Oncesi',
  checked_in: 'Check-in Yapildi',
  checked_out: 'Check-out Yapildi',
};
const TRIGGER_COLORS = {
  booking_confirmed: 'bg-blue-50 text-blue-700',
  pre_arrival: 'bg-amber-50 text-amber-700',
  checked_in: 'bg-green-50 text-green-700',
  checked_out: 'bg-purple-50 text-purple-700',
};

function AutomationTab() {
  const [rules, setRules] = useState([]);
  const [templates, setTemplates] = useState([]);
  const [triggers, setTriggers] = useState({});
  const [loading, setLoading] = useState(true);
  const [showCreate, setShowCreate] = useState(false);
  const [editRule, setEditRule] = useState(null);
  const [form, setForm] = useState({
    trigger_event: 'checked_in', template_id: '', channel: 'whatsapp', name: '', enabled: true, delay_minutes: 0,
  });

  const load = useCallback(async () => {
    setLoading(true);
    const [rulesRes, tmplRes, trigRes] = await Promise.all([
      get('/api/messaging-center/automation/rules'),
      get('/api/messaging-center/templates'),
      get('/api/messaging-center/automation/triggers'),
    ]);
    setRules(rulesRes.rules || []);
    setTemplates(tmplRes.templates || []);
    setTriggers(trigRes.triggers || {});
    setLoading(false);
  }, []);
  useEffect(() => { load(); }, [load]);

  const filteredTemplates = templates.filter(t => t.channel === form.channel);
  const tmplMap = Object.fromEntries(templates.map(t => [t.id, t]));

  const handleCreate = async () => {
    if (!form.name || !form.template_id) { toast.error('Ad ve sablon gerekli'); return; }
    const res = await post('/api/messaging-center/automation/rules', form);
    if (res.id) { toast.success('Otomasyon kurali olusturuldu'); setShowCreate(false); load(); }
  };

  const handleUpdate = async () => {
    if (!editRule) return;
    await put(`/api/messaging-center/automation/rules/${editRule.id}`, form);
    toast.success('Kural guncellendi');
    setEditRule(null);
    load();
  };

  const handleDelete = async (id) => {
    if (!confirm('Bu kurali silmek istediginizden emin misiniz?')) return;
    await del(`/api/messaging-center/automation/rules/${id}`);
    toast.success('Kural silindi');
    load();
  };

  const toggleEnabled = async (rule) => {
    await put(`/api/messaging-center/automation/rules/${rule.id}`, { enabled: !rule.enabled });
    load();
  };

  const testRule = async (rule) => {
    const res = await post(`/api/messaging-center/automation/test/${rule.id}`, {});
    if (res.success) toast.success(`Test tetiklendi: ${rule.name}`);
    else toast.error('Test hatasi');
  };

  const openEdit = (r) => {
    setForm({ trigger_event: r.trigger_event, template_id: r.template_id, channel: r.channel, name: r.name, enabled: r.enabled, delay_minutes: r.delay_minutes || 0 });
    setEditRule(r);
  };

  const openCreate = () => {
    setForm({ trigger_event: 'checked_in', template_id: '', channel: 'whatsapp', name: '', enabled: true, delay_minutes: 0 });
    setShowCreate(true);
  };

  if (loading) return <div className="flex items-center justify-center py-12"><Loader2 className="h-6 w-6 animate-spin" /></div>;

  return (
    <div className="space-y-4" data-testid="automation-tab">
      {/* Summary Cards */}
      <div className="grid grid-cols-2 md:grid-cols-4 gap-3">
        <Card><CardContent className="py-4 text-center">
          <p className="text-2xl font-bold">{rules.length}</p>
          <p className="text-xs text-muted-foreground">Toplam Kural</p>
        </CardContent></Card>
        <Card><CardContent className="py-4 text-center">
          <p className="text-2xl font-bold text-emerald-600">{rules.filter(r => r.enabled).length}</p>
          <p className="text-xs text-muted-foreground">Aktif</p>
        </CardContent></Card>
        <Card><CardContent className="py-4 text-center">
          <p className="text-2xl font-bold text-blue-600">{rules.reduce((a, r) => a + (r.total_sent || 0), 0)}</p>
          <p className="text-xs text-muted-foreground">Toplam Gonderim</p>
        </CardContent></Card>
        <Card><CardContent className="py-4 text-center">
          <p className="text-2xl font-bold text-red-600">{rules.reduce((a, r) => a + (r.total_failed || 0), 0)}</p>
          <p className="text-xs text-muted-foreground">Basarisiz</p>
        </CardContent></Card>
      </div>

      <div className="flex justify-between items-center">
        <h3 className="font-semibold">Otomasyon Kurallari</h3>
        <Button data-testid="create-automation-btn" size="sm" onClick={openCreate}>
          <Plus className="h-4 w-4 mr-1" /> Yeni Kural
        </Button>
      </div>

      {rules.length === 0 ? (
        <Card><CardContent className="py-8 text-center text-muted-foreground">
          <Zap className="h-8 w-8 mx-auto mb-2 opacity-50" />
          <p>Henuz otomasyon kurali yok.</p>
          <p className="text-xs mt-1">Yeni kural ekleyerek check-in/check-out olaylarinda otomatik mesaj gonderimi baslatin.</p>
        </CardContent></Card>
      ) : (
        <div className="space-y-2">
          {rules.map(r => {
            const tmpl = tmplMap[r.template_id];
            const Icon = CHANNEL_ICONS[r.channel] || Mail;
            return (
              <Card key={r.id} data-testid={`automation-rule-${r.id}`} className={!r.enabled ? 'opacity-60' : ''}>
                <CardContent className="py-4">
                  <div className="flex items-center gap-3">
                    {/* Trigger Badge */}
                    <div className={`px-2 py-1 rounded text-xs font-medium ${TRIGGER_COLORS[r.trigger_event] || 'bg-gray-100'}`}>
                      {TRIGGER_LABELS[r.trigger_event] || r.trigger_event}
                    </div>
                    <ArrowRight className="h-3.5 w-3.5 text-muted-foreground" />
                    {/* Channel + Template */}
                    <div className={`p-1.5 rounded ${r.channel === 'whatsapp' ? 'bg-green-50' : 'bg-blue-50'}`}>
                      <Icon className={`h-4 w-4 ${r.channel === 'whatsapp' ? 'text-green-600' : 'text-blue-600'}`} />
                    </div>
                    <div className="flex-1 min-w-0">
                      <p className="font-medium text-sm">{r.name}</p>
                      <p className="text-xs text-muted-foreground truncate">
                        Sablon: {tmpl?.name || 'Bilinmiyor'}
                        {r.delay_minutes > 0 && ` · ${r.delay_minutes} dk gecikme`}
                      </p>
                    </div>
                    {/* Stats */}
                    <div className="text-right text-xs text-muted-foreground hidden md:block">
                      <span className="text-emerald-600 font-medium">{r.total_sent || 0}</span> gonderim
                      {(r.total_failed || 0) > 0 && <span className="text-red-500 ml-2">{r.total_failed} basarisiz</span>}
                    </div>
                    {/* Actions */}
                    <div className="flex items-center gap-1">
                      <Button size="sm" variant="ghost" onClick={() => toggleEnabled(r)} title={r.enabled ? 'Devre disi birak' : 'Aktif et'}>
                        <Power className={`h-3.5 w-3.5 ${r.enabled ? 'text-emerald-600' : 'text-gray-400'}`} />
                      </Button>
                      <Button size="sm" variant="ghost" onClick={() => testRule(r)} title="Test et">
                        <Play className="h-3.5 w-3.5 text-blue-500" />
                      </Button>
                      <Button size="sm" variant="ghost" onClick={() => openEdit(r)}><Pencil className="h-3.5 w-3.5" /></Button>
                      <Button size="sm" variant="ghost" onClick={() => handleDelete(r.id)}><Trash2 className="h-3.5 w-3.5 text-red-500" /></Button>
                    </div>
                  </div>
                </CardContent>
              </Card>
            );
          })}
        </div>
      )}

      {/* How it works */}
      <Card>
        <CardContent className="py-4">
          <h4 className="text-sm font-semibold mb-2">Nasil Calisir?</h4>
          <div className="grid grid-cols-1 md:grid-cols-4 gap-3 text-xs text-muted-foreground">
            <div className="flex items-start gap-2">
              <div className="w-6 h-6 rounded-full bg-blue-100 flex items-center justify-center flex-shrink-0 text-blue-700 font-bold">1</div>
              <div><strong>Rezervasyon Onaylandi</strong><br/>Misafire onay emaili gonderilir</div>
            </div>
            <div className="flex items-start gap-2">
              <div className="w-6 h-6 rounded-full bg-amber-100 flex items-center justify-center flex-shrink-0 text-amber-700 font-bold">2</div>
              <div><strong>Check-in Oncesi</strong><br/>Yol tarifi ve tesis bilgileri WhatsApp ile paylasilir</div>
            </div>
            <div className="flex items-start gap-2">
              <div className="w-6 h-6 rounded-full bg-green-100 flex items-center justify-center flex-shrink-0 text-green-700 font-bold">3</div>
              <div><strong>Check-in</strong><br/>Hos geldiniz mesaji, WiFi sifresi, restoran bilgileri</div>
            </div>
            <div className="flex items-start gap-2">
              <div className="w-6 h-6 rounded-full bg-purple-100 flex items-center justify-center flex-shrink-0 text-purple-700 font-bold">4</div>
              <div><strong>Check-out</strong><br/>Tesekkur emaili ve degerlendirme linki</div>
            </div>
          </div>
        </CardContent>
      </Card>

      {/* Pre-Arrival Scheduler */}
      <SchedulerCard />

      {/* Create/Edit Dialog */}
      <Dialog open={showCreate || !!editRule} onOpenChange={v => { if (!v) { setShowCreate(false); setEditRule(null); } }}>
        <DialogContent className="max-w-lg">
          <DialogHeader>
            <DialogTitle>{editRule ? 'Kurali Duzenle' : 'Yeni Otomasyon Kurali'}</DialogTitle>
          </DialogHeader>
          <div className="space-y-3">
            <div>
              <Label>Kural Adi</Label>
              <Input data-testid="automation-name" value={form.name} onChange={e => setForm(p => ({ ...p, name: e.target.value }))} placeholder="Hos Geldiniz Mesaji" />
            </div>
            <div className="grid grid-cols-2 gap-3">
              <div>
                <Label>Tetikleme Olayi</Label>
                <Select value={form.trigger_event} onValueChange={v => setForm(p => ({ ...p, trigger_event: v }))}>
                  <SelectTrigger data-testid="automation-trigger"><SelectValue /></SelectTrigger>
                  <SelectContent>
                    {Object.entries(TRIGGER_LABELS).map(([k, v]) => (
                      <SelectItem key={k} value={k}>{v}</SelectItem>
                    ))}
                  </SelectContent>
                </Select>
              </div>
              <div>
                <Label>Kanal</Label>
                <Select value={form.channel} onValueChange={v => setForm(p => ({ ...p, channel: v, template_id: '' }))}>
                  <SelectTrigger data-testid="automation-channel"><SelectValue /></SelectTrigger>
                  <SelectContent>
                    <SelectItem value="whatsapp">WhatsApp</SelectItem>
                    <SelectItem value="email">Email</SelectItem>
                  </SelectContent>
                </Select>
              </div>
            </div>
            <div>
              <Label>Sablon</Label>
              <Select value={form.template_id} onValueChange={v => setForm(p => ({ ...p, template_id: v }))}>
                <SelectTrigger data-testid="automation-template"><SelectValue placeholder="Sablon secin" /></SelectTrigger>
                <SelectContent>
                  {filteredTemplates.map(t => (
                    <SelectItem key={t.id} value={t.id}>{t.name} ({CATEGORY_LABELS[t.category] || t.category})</SelectItem>
                  ))}
                </SelectContent>
              </Select>
            </div>
            <div className="flex items-center gap-4">
              <div className="flex items-center gap-2">
                <Switch checked={form.enabled} onCheckedChange={v => setForm(p => ({ ...p, enabled: v }))} />
                <Label>Aktif</Label>
              </div>
            </div>
          </div>
          <DialogFooter>
            <Button variant="outline" onClick={() => { setShowCreate(false); setEditRule(null); }}>Iptal</Button>
            <Button data-testid="automation-save-btn" onClick={editRule ? handleUpdate : handleCreate}>
              {editRule ? 'Guncelle' : 'Olustur'}
            </Button>
          </DialogFooter>
        </DialogContent>
      </Dialog>
    </div>
  );
}


// ═══════════════════════════════════════════════
// Scheduler Card (inside Automation Tab)
// ═══════════════════════════════════════════════
function SchedulerCard() {
  const [status, setStatus] = useState(null);
  const [loading, setLoading] = useState(true);
  const [actionLoading, setActionLoading] = useState(false);

  const load = useCallback(async () => {
    setLoading(true);
    const d = await get('/api/messaging-center/scheduler/status');
    setStatus(d);
    setLoading(false);
  }, []);
  useEffect(() => { load(); }, [load]);

  const toggleScheduler = async () => {
    setActionLoading(true);
    if (status?.status === 'running') {
      await post('/api/messaging-center/scheduler/stop', {});
      toast.success('Zamanlayici durduruldu');
    } else {
      await post('/api/messaging-center/scheduler/start', {});
      toast.success('Zamanlayici baslatildi');
    }
    await load();
    setActionLoading(false);
  };

  const runNow = async () => {
    setActionLoading(true);
    const res = await post('/api/messaging-center/scheduler/run-now', {});
    if (res.success) {
      const r = res.result || {};
      toast.success(`Tarama tamamlandi: ${r.events_fired || 0} mesaj tetiklendi, ${r.bookings_scanned || 0} rezervasyon tarandi`);
    } else {
      toast.error('Tarama hatasi');
    }
    await load();
    setActionLoading(false);
  };

  if (loading) return null;

  const isRunning = status?.status === 'running';

  return (
    <Card data-testid="scheduler-card" className="border-dashed">
      <CardContent className="py-4">
        <div className="flex items-center justify-between">
          <div className="flex items-center gap-3">
            <div className={`p-2 rounded-lg ${isRunning ? 'bg-emerald-50' : 'bg-gray-100'}`}>
              <Timer className={`h-5 w-5 ${isRunning ? 'text-emerald-600' : 'text-gray-400'}`} />
            </div>
            <div>
              <h4 className="text-sm font-semibold flex items-center gap-2">
                Pre-Arrival Zamanlayici
                <Badge variant={isRunning ? 'default' : 'secondary'} className="text-[10px]">
                  {isRunning ? 'Aktif' : 'Durduruldu'}
                </Badge>
              </h4>
              <p className="text-xs text-muted-foreground">
                Yarinki check-in&apos;leri tarayip otomatik yol tarifi/tesis mesaji gonderir
              </p>
            </div>
          </div>
          <div className="flex items-center gap-2">
            <Button data-testid="scheduler-run-now-btn" size="sm" variant="outline" onClick={runNow} disabled={actionLoading}>
              {actionLoading ? <Loader2 className="h-3.5 w-3.5 animate-spin" /> : <Play className="h-3.5 w-3.5" />}
              <span className="ml-1">Simdi Tara</span>
            </Button>
            <Button
              data-testid="scheduler-toggle-btn"
              size="sm"
              variant={isRunning ? 'destructive' : 'default'}
              onClick={toggleScheduler}
              disabled={actionLoading}
            >
              <Power className="h-3.5 w-3.5 mr-1" />
              {isRunning ? 'Durdur' : 'Baslat'}
            </Button>
          </div>
        </div>
        {status?.last_run_result && (
          <div className="mt-3 grid grid-cols-4 gap-2 text-center text-xs">
            <div className="bg-gray-50 rounded p-2">
              <p className="font-bold">{status.total_runs || 0}</p>
              <p className="text-muted-foreground">Toplam Tarama</p>
            </div>
            <div className="bg-emerald-50 rounded p-2">
              <p className="font-bold text-emerald-700">{status.total_sent || 0}</p>
              <p className="text-muted-foreground">Gonderilen</p>
            </div>
            <div className="bg-amber-50 rounded p-2">
              <p className="font-bold text-amber-700">{status.total_skipped || 0}</p>
              <p className="text-muted-foreground">Zaten Gonderilmis</p>
            </div>
            <div className="bg-red-50 rounded p-2">
              <p className="font-bold text-red-700">{status.total_errors || 0}</p>
              <p className="text-muted-foreground">Hata</p>
            </div>
          </div>
        )}
        {status?.last_run_at && (
          <p className="text-[10px] text-muted-foreground mt-2">
            Son tarama: {new Date(status.last_run_at).toLocaleString('tr-TR')}
            {status.interval_hours && ` · Her ${status.interval_hours} saatte bir`}
          </p>
        )}
      </CardContent>
    </Card>
  );
}


// ═══════════════════════════════════════════════
// Activity Tab (Real-time Messaging Notifications)
// ═══════════════════════════════════════════════
function ActivityTab() {
  const [activities, setActivities] = useState([]);
  const [loading, setLoading] = useState(true);

  const load = useCallback(async () => {
    setLoading(true);
    const d = await get('/api/messaging-center/activity?limit=30');
    setActivities(d.activities || []);
    setLoading(false);
  }, []);

  useEffect(() => {
    load();
    const interval = setInterval(load, 10000); // Poll every 10s
    return () => clearInterval(interval);
  }, [load]);

  if (loading && activities.length === 0) return <div className="flex items-center justify-center py-12"><Loader2 className="h-6 w-6 animate-spin" /></div>;

  const getIcon = (activity) => {
    if (activity.type === 'automation') {
      return activity.priority === 'high' ? XCircle : CheckCircle2;
    }
    if (activity.status === 'sent' || activity.status === 'delivered') return CheckCircle2;
    if (activity.status === 'failed') return XCircle;
    return Clock;
  };

  const getColor = (activity) => {
    if (activity.priority === 'high' || activity.status === 'failed') return 'text-red-500';
    if (activity.status === 'sent' || activity.status === 'delivered') return 'text-emerald-500';
    if (activity.type === 'automation' && activity.priority === 'normal') return 'text-blue-500';
    return 'text-amber-500';
  };

  const getBg = (activity) => {
    if (activity.priority === 'high' || activity.status === 'failed') return 'bg-red-50';
    if (activity.status === 'sent' || activity.status === 'delivered') return 'bg-emerald-50';
    if (activity.type === 'automation' && activity.priority === 'normal') return 'bg-blue-50';
    return 'bg-amber-50';
  };

  return (
    <div className="space-y-3" data-testid="activity-tab">
      <div className="flex items-center justify-between">
        <h3 className="font-semibold text-sm">Canli Aktivite</h3>
        <Button size="sm" variant="ghost" onClick={load} data-testid="activity-refresh-btn">
          <RefreshCw className="h-3.5 w-3.5 mr-1" /> Yenile
        </Button>
      </div>

      {activities.length === 0 ? (
        <Card><CardContent className="py-8 text-center text-muted-foreground">
          <Bell className="h-8 w-8 mx-auto mb-2 opacity-50" />
          <p>Henuz aktivite yok.</p>
          <p className="text-xs mt-1">Otomasyon tetiklendikce ve mesajlar gonderildikce burada gorunecek.</p>
        </CardContent></Card>
      ) : (
        <div className="space-y-1.5">
          {activities.map((a, i) => {
            const Icon = getIcon(a);
            const color = getColor(a);
            const bg = getBg(a);
            return (
              <Card key={`${a.id}-${i}`} className="border-0 shadow-none bg-transparent">
                <CardContent className="py-2 px-3">
                  <div className="flex items-center gap-3">
                    <div className={`p-1.5 rounded ${bg}`}>
                      <Icon className={`h-3.5 w-3.5 ${color}`} />
                    </div>
                    <div className="flex-1 min-w-0">
                      <p className="text-sm font-medium truncate">{a.title}</p>
                      <p className="text-xs text-muted-foreground truncate">{a.message}</p>
                    </div>
                    <div className="flex items-center gap-2">
                      <Badge variant="outline" className="text-[10px]">
                        {a.type === 'automation' ? 'Otomasyon' : 'Gonderim'}
                      </Badge>
                      <span className="text-[10px] text-muted-foreground whitespace-nowrap">
                        {a.created_at ? new Date(a.created_at).toLocaleTimeString('tr-TR', { hour: '2-digit', minute: '2-digit' }) : ''}
                      </span>
                    </div>
                  </div>
                </CardContent>
              </Card>
            );
          })}
        </div>
      )}
    </div>
  );
}


// ═══════════════════════════════════════════════
// Main Dashboard
// ═══════════════════════════════════════════════
export default function MessagingDashboard({ user, tenant, onLogout }) {
  const [seeded, setSeeded] = useState(false);

  useEffect(() => {
    // Auto-seed demo data on first load
    (async () => {
      const d = await get('/api/messaging-center/delivery-logs?limit=1');
      if (!d.logs || d.logs.length === 0) {
        await post('/api/messaging-center/seed-demo', {});
        setSeeded(true);
      }
    })();
  }, []);

  return (
    <Layout user={user} tenant={tenant} onLogout={onLogout} currentModule="messaging">
      <div data-testid="messaging-dashboard" className="p-4 lg:p-6 space-y-4 max-w-7xl mx-auto">
        <div>
          <h1 className="text-2xl font-bold tracking-tight">Mesajlasma Merkezi</h1>
          <p className="text-sm text-muted-foreground">Email (SMTP) ve WhatsApp Business ile misafir iletisimi</p>
        </div>
        <Tabs defaultValue="send">
          <TabsList className="grid w-full grid-cols-7 max-w-5xl" data-testid="messaging-tabs">
            <TabsTrigger data-testid="tab-send" value="send" className="flex items-center gap-1.5">
              <Send className="h-3.5 w-3.5" /> Mesaj Gonder
            </TabsTrigger>
            <TabsTrigger data-testid="tab-templates" value="templates" className="flex items-center gap-1.5">
              <FileText className="h-3.5 w-3.5" /> Sablonlar
            </TabsTrigger>
            <TabsTrigger data-testid="tab-automation" value="automation" className="flex items-center gap-1.5">
              <Zap className="h-3.5 w-3.5" /> Otomasyon
            </TabsTrigger>
            <TabsTrigger data-testid="tab-activity" value="activity" className="flex items-center gap-1.5">
              <Bell className="h-3.5 w-3.5" /> Aktivite
            </TabsTrigger>
            <TabsTrigger data-testid="tab-logs" value="logs" className="flex items-center gap-1.5">
              <Clock className="h-3.5 w-3.5" /> Loglar
            </TabsTrigger>
            <TabsTrigger data-testid="tab-metrics" value="metrics" className="flex items-center gap-1.5">
              <BarChart3 className="h-3.5 w-3.5" /> Metrikler
            </TabsTrigger>
            <TabsTrigger data-testid="tab-settings" value="settings" className="flex items-center gap-1.5">
              <Settings className="h-3.5 w-3.5" /> Ayarlar
            </TabsTrigger>
          </TabsList>
          <TabsContent value="send"><SendTab /></TabsContent>
          <TabsContent value="templates"><TemplatesTab /></TabsContent>
          <TabsContent value="automation"><AutomationTab /></TabsContent>
          <TabsContent value="activity"><ActivityTab /></TabsContent>
          <TabsContent value="logs"><DeliveryLogsTab /></TabsContent>
          <TabsContent value="metrics"><MetricsTab /></TabsContent>
          <TabsContent value="settings"><SettingsTab /></TabsContent>
        </Tabs>
      </div>
    </Layout>
  );
}
