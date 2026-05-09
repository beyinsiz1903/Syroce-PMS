import React, { useState, useEffect, useCallback, useMemo } from 'react';
import axios from 'axios';

import { Card, CardContent } from '../components/ui/card';
import { Button } from '../components/ui/button';
import { Tabs, TabsContent, TabsList, TabsTrigger } from '../components/ui/tabs';
import { Input } from '../components/ui/input';
import { Label } from '../components/ui/label';
import { Textarea } from '../components/ui/textarea';
import {
  Select, SelectContent, SelectItem, SelectTrigger, SelectValue,
} from '../components/ui/select';
import {
  Dialog, DialogContent, DialogHeader, DialogTitle, DialogFooter,
} from '../components/ui/dialog';
import { Switch } from '../components/ui/switch';
import { PageHeader } from '../components/ui/page-header';
import { KpiCard } from '../components/ui/kpi-card';
import { StatusBadge } from '../components/ui/status-badge';
import {
  Mail, MessageSquare, RefreshCw, Send, Settings, FileText, BarChart3,
  Loader2, Plus, Trash2, CheckCircle2, XCircle, Clock, AlertTriangle,
  Pencil, TestTube, ArrowRight, Zap, Play, Power, Timer, Bell, Sparkles,
  Shield,
} from 'lucide-react';
import { toast } from 'sonner';
import { confirmDialog } from '@/lib/dialogs';
import { useTranslation } from 'react-i18next';

// ── HTTP wrapper (axios — silent refresh + uniform error toasts) ────────
const api = axios.create();
api.interceptors.request.use((cfg) => {
  const t = localStorage.getItem('token');
  if (t) cfg.headers.Authorization = `Bearer ${t}`;
  return cfg;
});
api.interceptors.response.use(
  (r) => r,
  (err) => {
    const status = err?.response?.status;
    if (status === 401) {
      toast.error('Oturum süresi doldu. Lütfen tekrar giriş yapın.');
    } else if (status === 403) {
      toast.error('Bu işlem için yetkiniz yok.');
    } else if (status >= 500) {
      toast.error('Sunucu hatası. Lütfen tekrar deneyin.');
    }
    return Promise.reject(err);
  },
);
const get  = async (p)    => (await api.get(p)).data;
const post = async (p, b) => (await api.post(p, b)).data;
const put  = async (p, b) => (await api.put(p, b)).data;
const del  = async (p)    => (await api.delete(p)).data;

// Safe wrapper — returns { ok, data, error } so call sites don't throw
const safe = async (fn) => {
  try { return { ok: true, data: await fn() }; }
  catch (e) { return { ok: false, error: e?.response?.data?.detail || e.message }; }
};

// ── Validation regexes (Bug #1) ─────────────────────────────────────────
// RFC 5322 simplified — practical email validation
const EMAIL_RE = /^[^\s@]+@[^\s@]+\.[^\s@]{2,}$/;
// E.164 — + then 8-15 digits (first non-zero)
const E164_RE = /^\+[1-9]\d{7,14}$/;

const validateRecipient = (channel, value) => {
  if (!value) return { ok: false, msg: 'Alıcı bilgisi gerekli' };
  if (channel === 'email') {
    return EMAIL_RE.test(value)
      ? { ok: true }
      : { ok: false, msg: 'Geçerli bir e-posta adresi girin (örn. ad@domain.com)' };
  }
  if (channel === 'whatsapp') {
    return E164_RE.test(value)
      ? { ok: true }
      : { ok: false, msg: 'WhatsApp numarası uluslararası formatta olmalı (örn. +905551234567)' };
  }
  return { ok: true };
};

// Bug #5 — Unicode-aware variable extraction (TR ı/ş/ç/ğ/ü/ö desteği)
const extractVariables = (body) => {
  const matches = body?.match(/\{\{([\p{L}\p{N}_]+)\}\}/gu) || [];
  return matches.map((v) => v.replace(/\{\{|\}\}/g, ''));
};

// ── i18n labels (TR — düzgün diakritiklerle) ────────────────────────────
const STATUS_INTENT = {
  sent: 'success', delivered: 'success', failed: 'danger', bounced: 'danger',
  queued: 'warning', sending: 'info',
};
const STATUS_LABELS = {
  sent: 'Gönderildi', delivered: 'Teslim Edildi', failed: 'Başarısız',
  queued: 'Kuyrukta', sending: 'Gönderiliyor', bounced: 'Geri Döndü',
};
const CHANNEL_ICONS = { email: Mail, whatsapp: MessageSquare };
const CHANNEL_LABELS = { email: 'E-posta', whatsapp: 'WhatsApp' };

const CATEGORY_LABELS = {
  hosgeldiniz: 'Hoş Geldiniz',
  yol_tarifi: 'Yol Tarifi',
  tesis_bilgi: 'Tesis Bilgileri',
  fatura: 'Fatura',
  kampanya: 'Kampanya',
  puan_degerlendirme: 'Değerlendirme',
  checkout: 'Check-out',
  rezervasyon_onay: 'Rezervasyon Onayı',
  iletisim: 'İletişim',
  genel: 'Genel',
};

// ── Health → 3-state badge (Bug #7) ─────────────────────────────────────
function ConnectionBadge({ provider }) {
  const { t } = useTranslation();
  if (!provider) {
    return <StatusBadge intent="neutral" icon={AlertTriangle}>{t('cm.pages_MessagingDashboard.yapilandirilmamis')}</StatusBadge>;
  }
  const h = provider.health_status;
  if (h === 'healthy') return <StatusBadge intent="success" icon={CheckCircle2}>{t('cm.pages_MessagingDashboard.bagli')}</StatusBadge>;
  if (h === 'unknown' || h == null) return <StatusBadge intent="warning" icon={Clock}>Test Edilmedi</StatusBadge>;
  return <StatusBadge intent="danger" icon={XCircle}>{t('cm.pages_MessagingDashboard.baglanti_yok')}</StatusBadge>;
}

// ════════════════════════════════════════════════
// Settings Tab
// ════════════════════════════════════════════════
function SettingsTab({ onChanged }) {
  const [settings, setSettings] = useState(null);
  const [loading, setLoading] = useState(true);
  const [saving, setSaving] = useState(false);
  const [emailForm, setEmailForm] = useState({
    smtp_host: '', smtp_port: 587, smtp_username: '', smtp_password: '',
    from_email: '', from_name: 'Otel', use_tls: true, is_sandbox: true, enabled: true,
  });
  const [waForm, setWaForm] = useState({
    access_token: '', phone_number_id: '', business_name: '',
    webhook_verify_token: '', app_secret: '',
    is_sandbox: true, enabled: true,
  });

  const load = useCallback(async () => {
    setLoading(true);
    const r = await safe(() => get('/api/messaging-center/settings'));
    if (r.ok) {
      setSettings(r.data);
      if (r.data.email?.credentials) {
        setEmailForm((prev) => ({
          ...prev,
          smtp_host: r.data.email.credentials.smtp_host || '',
          smtp_port: r.data.email.credentials.smtp_port || 587,
          smtp_username: '',  // masked — don't pre-fill
          smtp_password: '',  // masked
          from_email: r.data.email.credentials.from_email || '',
          from_name: r.data.email.credentials.from_name || 'Otel',
          use_tls: r.data.email.credentials.use_tls !== false,
          is_sandbox: r.data.email.is_sandbox,
          enabled: r.data.email.enabled,
        }));
      }
      if (r.data.whatsapp?.credentials) {
        setWaForm((prev) => ({
          ...prev,
          access_token: '',  // masked
          phone_number_id: r.data.whatsapp.credentials.phone_number_id || '',
          business_name: r.data.whatsapp.credentials.business_name || '',
          webhook_verify_token: '',  // masked
          app_secret: '',            // masked
          is_sandbox: r.data.whatsapp.is_sandbox,
          enabled: r.data.whatsapp.enabled,
        }));
      }
    }
    setLoading(false);
  }, []);
  useEffect(() => { load(); }, [load]);

  const saveEmail = async () => {
    setSaving(true);
    const r = await safe(() => post('/api/messaging-center/settings/email', emailForm));
    if (r.ok && r.data.success) {
      toast.success(`E-posta ayarları ${r.data.action === 'created' ? 'oluşturuldu' : 'güncellendi'}`);
      onChanged?.();
    } else if (r.ok) {
      toast.error('Kaydetme hatası');
    }
    setSaving(false);
    load();
  };

  const saveWhatsApp = async () => {
    setSaving(true);
    const r = await safe(() => post('/api/messaging-center/settings/whatsapp', waForm));
    if (r.ok && r.data.success) {
      toast.success(`WhatsApp ayarları ${r.data.action === 'created' ? 'oluşturuldu' : 'güncellendi'}`);
      onChanged?.();
    } else if (r.ok) {
      toast.error('Kaydetme hatası');
    }
    setSaving(false);
    load();
  };

  const testConnection = async () => {
    const r = await safe(() => post('/api/messaging-center/settings/test-connection', {}));
    if (!r.ok) return;
    if (!r.data.results || r.data.results.length === 0) {
      // Bug #9 — silent failure
      toast.warning('Yapılandırılmış sağlayıcı bulunamadı. Önce e-posta veya WhatsApp ayarlarını kaydedin.');
      return;
    }
    r.data.results.forEach((res) => {
      const label = res.provider_type === 'smtp_email' ? 'E-posta' : 'WhatsApp';
      if (res.status === 'healthy') toast.success(`${label}: Bağlantı başarılı`);
      else toast.error(`${label}: ${res.error || 'Bağlantı hatası'}`);
    });
    load();
  };

  if (loading) return <div className="flex items-center justify-center py-12"><Loader2 className="h-6 w-6 animate-spin text-slate-400" /></div>;

  return (
    <div className="space-y-6" data-testid="settings-tab">
      {/* Email SMTP */}
      <Card>
        <CardContent className="pt-6">
          <div className="flex items-center justify-between mb-4">
            <div className="flex items-center gap-2">
              <div className="w-9 h-9 rounded-lg bg-sky-50 flex items-center justify-center">
                <Mail className="h-4 w-4 text-sky-600" />
              </div>
              <h3 className="text-lg font-semibold text-slate-900">{t('cm.pages_MessagingDashboard.e_posta_smtp_ayarlari')}</h3>
            </div>
            <div className="flex items-center gap-2">
              <ConnectionBadge provider={settings?.email} />
              {settings?.email?.is_sandbox && <StatusBadge intent="warning">Sandbox</StatusBadge>}
            </div>
          </div>
          <div className="grid grid-cols-1 md:grid-cols-2 gap-4">
            <div>
              <Label>SMTP Sunucu</Label>
              <Input data-testid="smtp-host" placeholder="smtp.gmail.com" value={emailForm.smtp_host}
                onChange={(e) => setEmailForm((p) => ({ ...p, smtp_host: e.target.value }))} />
            </div>
            <div>
              <Label>Port</Label>
              <Input data-testid="smtp-port" type="number" value={emailForm.smtp_port}
                onChange={(e) => setEmailForm((p) => ({ ...p, smtp_port: parseInt(e.target.value, 10) || 587 }))} />
            </div>
            <div>
              <Label>{t('cm.pages_MessagingDashboard.kullanici_adi')}</Label>
              <Input data-testid="smtp-username" placeholder="email@domain.com" value={emailForm.smtp_username}
                onChange={(e) => setEmailForm((p) => ({ ...p, smtp_username: e.target.value }))} />
            </div>
            <div>
              <Label>{t('cm.pages_MessagingDashboard.sifre')} {settings?.email && <span className="text-xs text-slate-400 font-normal">{t('cm.pages_MessagingDashboard.bos_birakirsaniz_mevcut_sifre_korunur')}</span>}</Label>
              <Input data-testid="smtp-password" type="password" placeholder="••••••••" value={emailForm.smtp_password}
                onChange={(e) => setEmailForm((p) => ({ ...p, smtp_password: e.target.value }))} />
            </div>
            <div>
              <Label>{t('cm.pages_MessagingDashboard.gonderen_e_posta')}</Label>
              <Input data-testid="smtp-from-email" placeholder="info@oteliniz.com" value={emailForm.from_email}
                onChange={(e) => setEmailForm((p) => ({ ...p, from_email: e.target.value }))} />
            </div>
            <div>
              <Label>{t('cm.pages_MessagingDashboard.gonderen_adi')}</Label>
              <Input data-testid="smtp-from-name" placeholder={t('cm.pages_MessagingDashboard.otel_adiniz')} value={emailForm.from_name}
                onChange={(e) => setEmailForm((p) => ({ ...p, from_name: e.target.value }))} />
            </div>
          </div>
          <div className="flex flex-wrap items-center gap-6 mt-4">
            <div className="flex items-center gap-2">
              <Switch checked={emailForm.use_tls} onCheckedChange={(v) => setEmailForm((p) => ({ ...p, use_tls: v }))} />
              <Label>TLS</Label>
            </div>
            <div className="flex items-center gap-2">
              <Switch data-testid="smtp-sandbox" checked={emailForm.is_sandbox} onCheckedChange={(v) => setEmailForm((p) => ({ ...p, is_sandbox: v }))} />
              <Label>Sandbox Modu</Label>
            </div>
            <div className="flex items-center gap-2">
              <Switch checked={emailForm.enabled} onCheckedChange={(v) => setEmailForm((p) => ({ ...p, enabled: v }))} />
              <Label>{t('cm.pages_MessagingDashboard.aktif')}</Label>
            </div>
          </div>
          <div className="flex gap-2 mt-4">
            <Button data-testid="save-email-btn" onClick={saveEmail} disabled={saving}>
              {saving && <Loader2 className="h-4 w-4 animate-spin mr-1.5" />}
              {t('cm.pages_MessagingDashboard.kaydet')}
            </Button>
          </div>
          <p className="text-xs text-slate-500 mt-2">
            {t('cm.pages_MessagingDashboard.sandbox_modunda_gercek_e_posta_gonderilm')}
          </p>
        </CardContent>
      </Card>

      {/* WhatsApp */}
      <Card>
        <CardContent className="pt-6">
          <div className="flex items-center justify-between mb-4">
            <div className="flex items-center gap-2">
              <div className="w-9 h-9 rounded-lg bg-emerald-50 flex items-center justify-center">
                <MessageSquare className="h-4 w-4 text-emerald-600" />
              </div>
              <h3 className="text-lg font-semibold text-slate-900">{t('cm.pages_MessagingDashboard.whatsapp_business_api_ayarlari')}</h3>
            </div>
            <div className="flex items-center gap-2">
              <ConnectionBadge provider={settings?.whatsapp} />
              {settings?.whatsapp?.is_sandbox && <StatusBadge intent="warning">Sandbox</StatusBadge>}
            </div>
          </div>
          <div className="grid grid-cols-1 md:grid-cols-2 gap-4">
            <div>
              <Label>Access Token {settings?.whatsapp && <span className="text-xs text-slate-400 font-normal">{t('cm.pages_MessagingDashboard.bos_korunur')}</span>}</Label>
              <Input data-testid="wa-access-token" type="password" placeholder="Meta Business API Token" value={waForm.access_token}
                onChange={(e) => setWaForm((p) => ({ ...p, access_token: e.target.value }))} />
            </div>
            <div>
              <Label>Phone Number ID</Label>
              <Input data-testid="wa-phone-id" placeholder="Meta Phone Number ID" value={waForm.phone_number_id}
                onChange={(e) => setWaForm((p) => ({ ...p, phone_number_id: e.target.value }))} />
            </div>
            <div>
              <Label>{t('cm.pages_MessagingDashboard.isletme_adi')}</Label>
              <Input data-testid="wa-business-name" placeholder="Otel WhatsApp" value={waForm.business_name}
                onChange={(e) => setWaForm((p) => ({ ...p, business_name: e.target.value }))} />
            </div>
            <div>
              <Label>Webhook Verify Token {settings?.whatsapp && <span className="text-xs text-slate-400 font-normal">{t('cm.pages_MessagingDashboard.bos_korunur_fa8ab')}</span>}</Label>
              <Input data-testid="wa-webhook-verify" type="password" placeholder={t('cm.pages_MessagingDashboard.meta_panelinde_belirlediginiz_deger')} value={waForm.webhook_verify_token}
                onChange={(e) => setWaForm((p) => ({ ...p, webhook_verify_token: e.target.value }))} />
            </div>
            <div className="md:col-span-2">
              <Label>App Secret (HMAC) {settings?.whatsapp && <span className="text-xs text-slate-400 font-normal">{t('cm.pages_MessagingDashboard.bos_korunur_fa8ab')}</span>}</Label>
              <Input data-testid="wa-app-secret" type="password" placeholder="Meta App Settings → App Secret" value={waForm.app_secret}
                onChange={(e) => setWaForm((p) => ({ ...p, app_secret: e.target.value }))} />
              <p className="text-xs text-slate-500 mt-1 flex items-start gap-1">
                <Shield className="h-3 w-3 mt-0.5 text-amber-600 flex-shrink-0" />
                {t('cm.pages_MessagingDashboard.webhook_verify_token_app_secret_olmadan_')}
              </p>
            </div>
          </div>
          <div className="flex flex-wrap items-center gap-6 mt-4">
            <div className="flex items-center gap-2">
              <Switch data-testid="wa-sandbox" checked={waForm.is_sandbox} onCheckedChange={(v) => setWaForm((p) => ({ ...p, is_sandbox: v }))} />
              <Label>Sandbox Modu</Label>
            </div>
            <div className="flex items-center gap-2">
              <Switch checked={waForm.enabled} onCheckedChange={(v) => setWaForm((p) => ({ ...p, enabled: v }))} />
              <Label>{t('cm.pages_MessagingDashboard.aktif_81c33')}</Label>
            </div>
          </div>
          <div className="flex gap-2 mt-4">
            <Button data-testid="save-whatsapp-btn" onClick={saveWhatsApp} disabled={saving}>
              {saving && <Loader2 className="h-4 w-4 animate-spin mr-1.5" />}
              {t('cm.pages_MessagingDashboard.kaydet_a9270')}
            </Button>
          </div>
          <p className="text-xs text-slate-500 mt-2">
            {t('cm.pages_MessagingDashboard.meta_business_panelinden_token_phone_num')}
          </p>
        </CardContent>
      </Card>

      <div className="flex gap-2">
        <Button data-testid="test-connection-btn" variant="outline" onClick={testConnection}>
          <TestTube className="h-4 w-4 mr-1.5" /> {t('cm.pages_MessagingDashboard.baglanti_testi')}
        </Button>
      </div>
    </div>
  );
}

// ════════════════════════════════════════════════
// Templates Tab
// ════════════════════════════════════════════════
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
    const r = await safe(() => get(`/api/messaging-center/templates${params}`));
    if (r.ok) setTemplates(r.data.templates || []);
    setLoading(false);
  }, [filterChannel]);
  useEffect(() => { load(); }, [load]);

  const handleCreate = async () => {
    if (!form.name?.trim()) { toast.error('Şablon adı gerekli'); return; }
    if (!form.body_template?.trim()) { toast.error('Mesaj içeriği gerekli'); return; }
    const vars = extractVariables(form.body_template);
    const r = await safe(() => post('/api/messaging-center/templates', { ...form, variables: vars }));
    if (r.ok && r.data.id) {
      toast.success('Şablon oluşturuldu');
      setShowCreate(false);
      setForm({ name: '', category: 'genel', channel: 'whatsapp', subject: '', body_template: '', variables: [] });
      load();
    }
  };

  const handleUpdate = async () => {
    if (!editTemplate) return;
    const vars = extractVariables(form.body_template);
    // Bug #10 — channel da gönderilsin, kullanıcı kanal değiştirebilsin.
    const r = await safe(() => put(`/api/messaging-center/templates/${editTemplate.id}`, {
      name: form.name,
      subject: form.subject,
      body_template: form.body_template,
      variables: vars,
      category: form.category,
      channel: form.channel,
    }));
    if (r.ok) {
      toast.success('Şablon güncellendi');
      setEditTemplate(null);
      load();
    }
  };

  const handleDelete = async (id) => {
    if (!await confirmDialog({ message: 'Bu şablonu silmek istediğinizden emin misiniz?' })) return;
    const r = await safe(() => del(`/api/messaging-center/templates/${id}`));
    if (r.ok) { toast.success('Şablon silindi'); load(); }
  };

  const openEdit = (t) => {
    setForm({
      name: t.name, category: t.category, channel: t.channel,
      subject: t.subject || '', body_template: t.body_template, variables: t.variables || [],
    });
    setEditTemplate(t);
  };
  const openCreate = () => {
    setForm({ name: '', category: 'genel', channel: 'whatsapp', subject: '', body_template: '', variables: [] });
    setShowCreate(true);
  };

  if (loading) return <div className="flex items-center justify-center py-12"><Loader2 className="h-6 w-6 animate-spin text-slate-400" /></div>;

  return (
    <div className="space-y-4" data-testid="templates-tab">
      <div className="flex justify-between items-center">
        <div className="flex gap-1">
          {['all', 'email', 'whatsapp'].map((f) => (
            <Button key={f} size="sm" variant={filterChannel === f ? 'default' : 'outline'}
              onClick={() => setFilterChannel(f)}>
              {f === 'all' ? 'Tümü' : CHANNEL_LABELS[f]}
            </Button>
          ))}
        </div>
        <Button data-testid="create-template-btn" size="sm" onClick={openCreate}>
          <Plus className="h-4 w-4 mr-1.5" /> {t('cm.pages_MessagingDashboard.yeni_sablon')}
        </Button>
      </div>

      {templates.length === 0 ? (
        <Card><CardContent className="py-10 text-center text-slate-500">
          <FileText className="h-8 w-8 mx-auto mb-2 opacity-40" />
          <p className="font-medium">{t('cm.pages_MessagingDashboard.henuz_sablon_yok')}</p>
          <p className="text-xs mt-1">{t('cm.pages_MessagingDashboard.otomasyon_ve_hizli_gonderim_icin_ilk_sab')}</p>
          <Button size="sm" className="mt-3" onClick={openCreate}>
            <Plus className="h-4 w-4 mr-1.5" /> {t('cm.pages_MessagingDashboard.ilk_sablonu_olustur')}
          </Button>
        </CardContent></Card>
      ) : (
        <div className="grid gap-3">
          {templates.map((t) => {
            const Icon = CHANNEL_ICONS[t.channel] || Mail;
            const isWA = t.channel === 'whatsapp';
            return (
              <Card key={t.id} data-testid={`template-${t.id}`}>
                <CardContent className="py-4">
                  <div className="flex items-start justify-between">
                    <div className="flex items-start gap-3">
                      <div className={`p-2 rounded-lg ${isWA ? 'bg-emerald-50' : 'bg-sky-50'}`}>
                        <Icon className={`h-4 w-4 ${isWA ? 'text-emerald-600' : 'text-sky-600'}`} />
                      </div>
                      <div>
                        <p className="font-medium text-slate-900">{t.name}</p>
                        <p className="text-xs text-slate-500 mt-0.5">
                          {CHANNEL_LABELS[t.channel]} · {CATEGORY_LABELS[t.category] || t.category}
                          {t.subject && <span> · {t.subject}</span>}
                        </p>
                        <p className="text-xs text-slate-500 mt-1 line-clamp-2">
                          {t.body_template?.replace(/<[^>]*>/g, '').substring(0, 120)}...
                        </p>
                        {t.variables?.length > 0 && (
                          <div className="flex flex-wrap gap-1 mt-1.5">
                            {t.variables.map((v) => (
                              <span key={v} className="text-[10px] px-1.5 py-0.5 bg-slate-100 text-slate-700 rounded">{`{{${v}}}`}</span>
                            ))}
                          </div>
                        )}
                      </div>
                    </div>
                    <div className="flex gap-1">
                      <Button size="sm" variant="ghost" onClick={() => openEdit(t)}><Pencil className="h-3.5 w-3.5" /></Button>
                      <Button size="sm" variant="ghost" onClick={() => handleDelete(t.id)}><Trash2 className="h-3.5 w-3.5 text-rose-500" /></Button>
                    </div>
                  </div>
                </CardContent>
              </Card>
            );
          })}
        </div>
      )}

      <Dialog open={showCreate || !!editTemplate} onOpenChange={(v) => { if (!v) { setShowCreate(false); setEditTemplate(null); } }}>
        <DialogContent className="max-w-lg">
          <DialogHeader>
            <DialogTitle>{editTemplate ? 'Şablonu Düzenle' : 'Yeni Şablon Oluştur'}</DialogTitle>
          </DialogHeader>
          <div className="space-y-3">
            <div>
              <Label>{t('cm.pages_MessagingDashboard.sablon_adi')}</Label>
              <Input data-testid="template-name" value={form.name} onChange={(e) => setForm((p) => ({ ...p, name: e.target.value }))} placeholder={t('cm.pages_MessagingDashboard.hos_geldiniz_mesaji')} />
            </div>
            <div className="grid grid-cols-2 gap-3">
              <div>
                <Label>Kanal</Label>
                <Select value={form.channel} onValueChange={(v) => setForm((p) => ({ ...p, channel: v }))}>
                  <SelectTrigger data-testid="template-channel"><SelectValue /></SelectTrigger>
                  <SelectContent>
                    <SelectItem value="whatsapp">WhatsApp</SelectItem>
                    <SelectItem value="email">E-posta</SelectItem>
                  </SelectContent>
                </Select>
              </div>
              <div>
                <Label>Kategori</Label>
                <Select value={form.category} onValueChange={(v) => setForm((p) => ({ ...p, category: v }))}>
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
                <Input data-testid="template-subject" value={form.subject} onChange={(e) => setForm((p) => ({ ...p, subject: e.target.value }))} placeholder={t('cm.pages_MessagingDashboard.rezervasyon_onayiniz')} />
              </div>
            )}
            <div>
              <Label>{t('cm.pages_MessagingDashboard.mesaj_icerigi')}</Label>
              <Textarea data-testid="template-body" className="min-h-[120px]" value={form.body_template}
                onChange={(e) => setForm((p) => ({ ...p, body_template: e.target.value }))}
                placeholder={t('cm.pages_MessagingDashboard.merhaba_misafir_adi_otelimize_hos_geldin')} />
              <p className="text-xs text-slate-500 mt-1">{t('cm.pages_MessagingDashboard.degisken_kullanimi')} {'{{degisken_adi}}'} {t('cm.pages_MessagingDashboard.turkce_karakterler_desteklenir')}</p>
            </div>
          </div>
          <DialogFooter>
            <Button variant="outline" onClick={() => { setShowCreate(false); setEditTemplate(null); }}>{t('cm.pages_MessagingDashboard.iptal')}</Button>
            <Button data-testid="template-save-btn" onClick={editTemplate ? handleUpdate : handleCreate}>
              {editTemplate ? 'Güncelle' : 'Oluştur'}
            </Button>
          </DialogFooter>
        </DialogContent>
      </Dialog>
    </div>
  );
}

// ════════════════════════════════════════════════
// Send Message Tab
// ════════════════════════════════════════════════
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
      const r = await safe(() => get('/api/messaging-center/templates'));
      if (r.ok) setTemplates(r.data.templates || []);
    })();
  }, []);

  const filteredTemplates = useMemo(
    () => templates.filter((t) => t.channel === form.channel),
    [templates, form.channel],
  );

  const recipientCheck = useMemo(
    () => validateRecipient(form.channel, form.recipient),
    [form.channel, form.recipient],
  );

  const selectTemplate = (templateId) => {
    // Bug #4 — "none" sentinel handling
    if (templateId === 'none') {
      setSelectedTemplate(null);
      setForm((p) => ({ ...p, template_id: '', subject: '', body: '' }));
      setVariables({});
      return;
    }
    const tmpl = templates.find((t) => t.id === templateId);
    setSelectedTemplate(tmpl);
    if (tmpl) {
      setForm((p) => ({ ...p, template_id: templateId, subject: tmpl.subject || '', body: tmpl.body_template || '' }));
      const vars = {};
      (tmpl.variables || []).forEach((v) => { vars[v] = ''; });
      setVariables(vars);
    }
  };

  const handleSend = async () => {
    // Bug #1 — strict format validation
    if (!recipientCheck.ok) { toast.error(recipientCheck.msg); return; }
    if (!form.body && !form.template_id) { toast.error('Mesaj içeriği veya şablon seçin'); return; }

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
    const r = await safe(() => post('/api/messaging-center/send', payload));
    if (r.ok && r.data.success) {
      toast.success(`Mesaj gönderildi (${form.channel})`);
      setForm((p) => ({ ...p, recipient: '', body: '', template_id: '', subject: '' }));
      setVariables({});
      setSelectedTemplate(null);
    } else if (r.ok) {
      toast.error(r.data.error || 'Gönderim hatası');
    }
    setSending(false);
  };

  const recipientLabel = form.channel === 'email' ? 'E-posta Adresi' : 'Telefon Numarası (uluslararası format)';
  const recipientPlaceholder = form.channel === 'email' ? 'misafir@email.com' : '+905551234567';

  return (
    <div className="space-y-4" data-testid="send-tab">
      <Card>
        <CardContent className="pt-6 space-y-4">
          <div className="grid grid-cols-1 md:grid-cols-2 gap-4">
            <div>
              <Label>Kanal</Label>
              <Select value={form.channel} onValueChange={(v) => { setForm((p) => ({ ...p, channel: v, template_id: '', recipient: '' })); setSelectedTemplate(null); setVariables({}); }}>
                <SelectTrigger data-testid="send-channel"><SelectValue /></SelectTrigger>
                <SelectContent>
                  <SelectItem value="whatsapp">WhatsApp</SelectItem>
                  <SelectItem value="email">E-posta</SelectItem>
                </SelectContent>
              </Select>
            </div>
            <div>
              <Label>{recipientLabel}</Label>
              <Input
                data-testid="send-recipient"
                value={form.recipient}
                onChange={(e) => setForm((p) => ({ ...p, recipient: e.target.value }))}
                placeholder={recipientPlaceholder}
                className={form.recipient && !recipientCheck.ok ? 'border-rose-400 focus-visible:ring-rose-400' : ''}
              />
              {form.recipient && !recipientCheck.ok && (
                <p className="text-xs text-rose-600 mt-1 flex items-center gap-1">
                  <AlertTriangle className="h-3 w-3" /> {recipientCheck.msg}
                </p>
              )}
            </div>
          </div>

          <div>
            <Label>{t('cm.pages_MessagingDashboard.sablon_opsiyonel')}</Label>
            <Select value={form.template_id || 'none'} onValueChange={selectTemplate}>
              <SelectTrigger data-testid="send-template"><SelectValue placeholder={t('cm.pages_MessagingDashboard.sablon_secin_veya_serbest_yazin')} /></SelectTrigger>
              <SelectContent>
                <SelectItem value="none">{t('cm.pages_MessagingDashboard.sablon_kullanma')}</SelectItem>
                {filteredTemplates.map((t) => (
                  <SelectItem key={t.id} value={t.id}>{t.name} ({CATEGORY_LABELS[t.category] || t.category})</SelectItem>
                ))}
              </SelectContent>
            </Select>
          </div>

          {selectedTemplate && selectedTemplate.variables?.length > 0 && (
            <div className="bg-slate-50 p-3 rounded-lg space-y-2">
              <Label className="text-sm font-medium">{t('cm.pages_MessagingDashboard.degiskenler')}</Label>
              <div className="grid grid-cols-1 md:grid-cols-2 gap-2">
                {selectedTemplate.variables.map((v) => (
                  <div key={v}>
                    <Label className="text-xs">{v}</Label>
                    <Input placeholder={v} value={variables[v] || ''}
                      onChange={(e) => setVariables((p) => ({ ...p, [v]: e.target.value }))} />
                  </div>
                ))}
              </div>
            </div>
          )}

          {form.channel === 'email' && (
            <div>
              <Label>Konu</Label>
              <Input data-testid="send-subject" value={form.subject}
                onChange={(e) => setForm((p) => ({ ...p, subject: e.target.value }))} placeholder="E-posta konusu" />
            </div>
          )}

          <div>
            <Label>{t('cm.pages_MessagingDashboard.mesaj_icerigi_e9429')}</Label>
            <Textarea data-testid="send-body" className="min-h-[100px]" value={form.body}
              onChange={(e) => setForm((p) => ({ ...p, body: e.target.value }))}
              placeholder={form.channel === 'email' ? 'HTML veya düz metin...' : 'Mesajınızı yazın...'} />
          </div>

          <Button
            data-testid="send-message-btn"
            className="w-full"
            onClick={handleSend}
            disabled={sending || !recipientCheck.ok || (!form.body && !form.template_id)}
          >
            {sending ? <Loader2 className="h-4 w-4 animate-spin mr-2" /> : <Send className="h-4 w-4 mr-2" />}
            {t('cm.pages_MessagingDashboard.mesaj_gonder')}
          </Button>
          {form.channel === 'whatsapp' && (
            <p className="text-xs text-slate-500 flex items-start gap-1">
              <Shield className="h-3 w-3 mt-0.5 text-amber-600 flex-shrink-0" />
              {t('cm.pages_MessagingDashboard.ilk_temas_24_saatlik_konusma_penceresi_d')}
            </p>
          )}
        </CardContent>
      </Card>
    </div>
  );
}

// ════════════════════════════════════════════════
// Delivery Logs Tab
// ════════════════════════════════════════════════
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
    const r = await safe(() => get(`/api/messaging-center/delivery-logs${q}`));
    if (r.ok) setLogs(r.data.logs || []);
    else setLogs([]);
    setLoading(false);
  }, [filter, channelFilter]);
  useEffect(() => { load(); }, [load]);

  const retry = async (id) => {
    const r = await safe(() => post(`/api/messaging-center/retry/${id}`, {}));
    if (r.ok && r.data.success) toast.success('Yeniden gönderildi');
    else if (r.ok) toast.error(r.data.error || 'Yeniden gönderim hatası');
    load();
  };

  return (
    <div className="space-y-4" data-testid="delivery-logs-tab">
      <div className="flex flex-wrap gap-2 justify-between items-center">
        <div className="flex gap-1 flex-wrap">
          {['all', 'sent', 'delivered', 'failed', 'queued'].map((f) => (
            <Button key={f} size="sm" variant={filter === f ? 'default' : 'outline'} onClick={() => setFilter(f)}>
              {f === 'all' ? 'Tümü' : STATUS_LABELS[f] || f}
            </Button>
          ))}
        </div>
        <div className="flex gap-1 items-center">
          {['all', 'email', 'whatsapp'].map((f) => (
            <Button key={f} size="sm" variant={channelFilter === f ? 'default' : 'outline'} onClick={() => setChannelFilter(f)}>
              {f === 'all' ? 'Tüm Kanallar' : CHANNEL_LABELS[f]}
            </Button>
          ))}
          <Button size="sm" variant="outline" onClick={load}>
            <RefreshCw className="w-4 h-4 mr-1.5" /> {t('cm.pages_MessagingDashboard.yenile')}
          </Button>
        </div>
      </div>
      {loading ? (
        <div className="flex items-center justify-center py-12"><Loader2 className="h-6 w-6 animate-spin text-slate-400" /></div>
      ) : logs.length === 0 ? (
        <Card><CardContent className="py-10 text-center text-slate-500">
          <Clock className="h-8 w-8 mx-auto mb-2 opacity-40" />
          <p>{t('cm.pages_MessagingDashboard.bu_filtre_icin_kayit_yok')}</p>
        </CardContent></Card>
      ) : (
        <div className="space-y-2">
          {logs.map((l) => {
            const Icon = CHANNEL_ICONS[l.channel] || Mail;
            const isWA = l.channel === 'whatsapp';
            return (
              <Card key={l.id} data-testid={`delivery-log-${l.id}`}>
                <CardContent className="py-3 flex items-center gap-3">
                  <div className={`p-1.5 rounded ${isWA ? 'bg-emerald-50' : 'bg-sky-50'}`}>
                    <Icon className={`h-4 w-4 ${isWA ? 'text-emerald-600' : 'text-sky-600'}`} />
                  </div>
                  <div className="flex-1 min-w-0">
                    <p className="text-sm font-medium truncate text-slate-900">{l.recipient}</p>
                    <p className="text-xs text-slate-500 truncate">
                      {CATEGORY_LABELS[l.use_case] || l.use_case || l.channel}
                      {l.subject && ` · ${l.subject}`}
                      {' · '}
                      {new Date(l.created_at).toLocaleString('tr-TR')}
                    </p>
                  </div>
                  <StatusBadge intent={STATUS_INTENT[l.status] || 'neutral'}>
                    {STATUS_LABELS[l.status] || l.status}
                  </StatusBadge>
                  {l.status === 'failed' && l.retry_count < (l.max_retries || 3) && (
                    <Button size="sm" variant="ghost" onClick={() => retry(l.id)} title={t('cm.pages_MessagingDashboard.yeniden_gonder')}>
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

// ════════════════════════════════════════════════
// Metrics Tab
// ════════════════════════════════════════════════
function MetricsTab() {
  const [metrics, setMetrics] = useState(null);
  const [loading, setLoading] = useState(true);

  const load = useCallback(async () => {
    setLoading(true);
    const r = await safe(() => get('/api/messaging-center/metrics?days=30'));
    if (r.ok) setMetrics(r.data);
    setLoading(false);
  }, []);
  useEffect(() => { load(); }, [load]);

  if (loading || !metrics) return <div className="flex items-center justify-center py-12"><Loader2 className="h-6 w-6 animate-spin text-slate-400" /></div>;

  const channels = Object.entries(metrics.metrics_by_channel || {});
  const totalSent = channels.reduce((a, [, s]) => a + (s.sent || 0) + (s.delivered || 0), 0);
  const totalFailed = channels.reduce((a, [, s]) => a + (s.failed || 0), 0);
  const totalQueued = channels.reduce((a, [, s]) => a + (s.queued || 0), 0);
  const successRate = metrics.total_messages > 0 ? Math.round((totalSent / metrics.total_messages) * 100) : 0;

  return (
    <div className="space-y-4" data-testid="metrics-tab">
      <div className="grid grid-cols-2 md:grid-cols-4 gap-3">
        <KpiCard icon={BarChart3} label={t('cm.pages_MessagingDashboard.toplam_mesaj')} value={metrics.total_messages} intent="default" />
        <KpiCard icon={CheckCircle2} label={t('cm.pages_MessagingDashboard.basarili')} value={totalSent} intent="success" />
        <KpiCard icon={XCircle} label={t('cm.pages_MessagingDashboard.basarisiz')} value={totalFailed} intent="danger" />
        <KpiCard icon={Sparkles} label={t('cm.pages_MessagingDashboard.basari_orani')} value={`%${successRate}`} intent={successRate >= 90 ? 'success' : successRate >= 60 ? 'warning' : 'danger'} />
      </div>

      <h3 className="text-base font-semibold mt-4 text-slate-900">{t('cm.pages_MessagingDashboard.kanal_bazli_dagilim')}</h3>
      <div className="grid grid-cols-1 md:grid-cols-2 gap-3">
        {channels.length === 0 && (
          <Card className="md:col-span-2"><CardContent className="py-8 text-center text-slate-500">
            <p>{t('cm.pages_MessagingDashboard.bu_donem_icin_kanal_verisi_yok')}</p>
          </CardContent></Card>
        )}
        {channels.map(([ch, stats]) => {
          const Icon = CHANNEL_ICONS[ch] || Mail;
          const isWA = ch === 'whatsapp';
          const total = Object.values(stats).reduce((a, b) => a + b, 0);
          return (
            <Card key={ch}>
              <CardContent className="py-4">
                <div className="flex items-center gap-2 mb-3">
                  <Icon className={`h-5 w-5 ${isWA ? 'text-emerald-600' : 'text-sky-600'}`} />
                  <span className="font-medium text-slate-900">{CHANNEL_LABELS[ch] || ch.toUpperCase()}</span>
                  <StatusBadge intent="neutral" className="ml-auto">{total} mesaj</StatusBadge>
                </div>
                <div className="grid grid-cols-3 gap-2 text-center">
                  <div className="bg-emerald-50 rounded p-2">
                    <p className="text-sm font-bold text-emerald-700">{(stats.sent || 0) + (stats.delivered || 0)}</p>
                    <p className="text-[10px] text-emerald-600">{t('cm.pages_MessagingDashboard.gonderildi')}</p>
                  </div>
                  <div className="bg-rose-50 rounded p-2">
                    <p className="text-sm font-bold text-rose-700">{stats.failed || 0}</p>
                    <p className="text-[10px] text-rose-600">{t('cm.pages_MessagingDashboard.basarisiz_3260d')}</p>
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
      <p className="text-xs text-slate-500">Son {metrics.period_days} {t('cm.pages_MessagingDashboard.gunluk_veriler_kuyrukta_toplam')} {totalQueued}</p>
    </div>
  );
}

// ════════════════════════════════════════════════
// Automation Tab
// ════════════════════════════════════════════════
const TRIGGER_LABELS = {
  booking_confirmed: 'Rezervasyon Onaylandı',
  pre_arrival: 'Check-in Öncesi',
  checked_in: 'Check-in Yapıldı',
  checked_out: 'Check-out Yapıldı',
};
const TRIGGER_INTENT = {
  booking_confirmed: 'info',
  pre_arrival: 'warning',
  checked_in: 'success',
  checked_out: 'default',
};

function AutomationTab() {
  const [rules, setRules] = useState([]);
  const [templates, setTemplates] = useState([]);
  const [loading, setLoading] = useState(true);
  const [showCreate, setShowCreate] = useState(false);
  const [editRule, setEditRule] = useState(null);
  const [form, setForm] = useState({
    trigger_event: 'checked_in', template_id: '', channel: 'whatsapp', name: '', enabled: true, delay_minutes: 0,
  });

  const load = useCallback(async () => {
    setLoading(true);
    const [rulesR, tmplR] = await Promise.all([
      safe(() => get('/api/messaging-center/automation/rules')),
      safe(() => get('/api/messaging-center/templates')),
    ]);
    if (rulesR.ok) setRules(rulesR.data.rules || []);
    if (tmplR.ok) setTemplates(tmplR.data.templates || []);
    setLoading(false);
  }, []);
  useEffect(() => { load(); }, [load]);

  const filteredTemplates = useMemo(
    () => templates.filter((t) => t.channel === form.channel),
    [templates, form.channel],
  );
  const tmplMap = useMemo(() => Object.fromEntries(templates.map((t) => [t.id, t])), [templates]);

  const handleCreate = async () => {
    if (!form.name?.trim()) { toast.error('Kural adı gerekli'); return; }
    if (!form.template_id) { toast.error('Şablon seçilmelidir'); return; }
    const r = await safe(() => post('/api/messaging-center/automation/rules', form));
    if (r.ok && r.data.id) { toast.success('Otomasyon kuralı oluşturuldu'); setShowCreate(false); load(); }
  };

  const handleUpdate = async () => {
    if (!editRule) return;
    const r = await safe(() => put(`/api/messaging-center/automation/rules/${editRule.id}`, form));
    if (r.ok) { toast.success('Kural güncellendi'); setEditRule(null); load(); }
  };

  const handleDelete = async (id) => {
    if (!await confirmDialog({ message: 'Bu kuralı silmek istediğinizden emin misiniz?' })) return;
    const r = await safe(() => del(`/api/messaging-center/automation/rules/${id}`));
    if (r.ok) { toast.success('Kural silindi'); load(); }
  };

  const toggleEnabled = async (rule) => {
    await safe(() => put(`/api/messaging-center/automation/rules/${rule.id}`, { enabled: !rule.enabled }));
    load();
  };

  const testRule = async (rule) => {
    const r = await safe(() => post(`/api/messaging-center/automation/test/${rule.id}`, {}));
    if (r.ok && r.data.success) {
      toast.success(r.data.message || `Test tetiklendi: ${rule.name}`);
    } else if (r.ok) {
      toast.error(r.data.message || 'Test hatası');
    }
  };

  const openEdit = (r) => {
    setForm({
      trigger_event: r.trigger_event, template_id: r.template_id, channel: r.channel,
      name: r.name, enabled: r.enabled, delay_minutes: r.delay_minutes || 0,
    });
    setEditRule(r);
  };
  const openCreate = () => {
    setForm({ trigger_event: 'checked_in', template_id: '', channel: 'whatsapp', name: '', enabled: true, delay_minutes: 0 });
    setShowCreate(true);
  };

  if (loading) return <div className="flex items-center justify-center py-12"><Loader2 className="h-6 w-6 animate-spin text-slate-400" /></div>;

  const noTemplates = templates.length === 0;

  return (
    <div className="space-y-4" data-testid="automation-tab">
      <div className="grid grid-cols-2 md:grid-cols-4 gap-3">
        <KpiCard icon={Zap} label={t('cm.pages_MessagingDashboard.toplam_kural')} value={rules.length} intent="default" />
        <KpiCard icon={CheckCircle2} label={t('cm.pages_MessagingDashboard.aktif_81c33')} value={rules.filter((r) => r.enabled).length} intent="success" />
        <KpiCard icon={Send} label={t('cm.pages_MessagingDashboard.toplam_gonderim')} value={rules.reduce((a, r) => a + (r.total_sent || 0), 0)} intent="info" />
        <KpiCard icon={XCircle} label={t('cm.pages_MessagingDashboard.basarisiz_3260d')} value={rules.reduce((a, r) => a + (r.total_failed || 0), 0)} intent="danger" />
      </div>

      {noTemplates && (
        <Card className="border-amber-200 bg-amber-50">
          <CardContent className="py-3 flex items-start gap-3">
            <AlertTriangle className="h-5 w-5 text-amber-600 flex-shrink-0 mt-0.5" />
            <div className="flex-1">
              <p className="text-sm font-medium text-amber-900">{t('cm.pages_MessagingDashboard.henuz_sablon_yok_78b56')}</p>
              <p className="text-xs text-amber-700">{t('cm.pages_MessagingDashboard.otomasyon_kurali_olusturmak_icin_once_sa')}</p>
            </div>
          </CardContent>
        </Card>
      )}

      <div className="flex justify-between items-center">
        <h3 className="font-semibold text-slate-900">{t('cm.pages_MessagingDashboard.otomasyon_kurallari')}</h3>
        <Button data-testid="create-automation-btn" size="sm" onClick={openCreate} disabled={noTemplates}>
          <Plus className="h-4 w-4 mr-1.5" /> {t('cm.pages_MessagingDashboard.yeni_kural')}
        </Button>
      </div>

      {rules.length === 0 ? (
        <Card><CardContent className="py-10 text-center text-slate-500">
          <Zap className="h-8 w-8 mx-auto mb-2 opacity-40" />
          <p className="font-medium">{t('cm.pages_MessagingDashboard.henuz_otomasyon_kurali_yok')}</p>
          <p className="text-xs mt-1">{t('cm.pages_MessagingDashboard.check_in_check_out_olaylarinda_otomatik_')}</p>
        </CardContent></Card>
      ) : (
        <div className="space-y-2">
          {rules.map((r) => {
            const tmpl = tmplMap[r.template_id];
            const Icon = CHANNEL_ICONS[r.channel] || Mail;
            const isWA = r.channel === 'whatsapp';
            return (
              <Card key={r.id} data-testid={`automation-rule-${r.id}`} className={!r.enabled ? 'opacity-60' : ''}>
                <CardContent className="py-4">
                  <div className="flex items-center gap-3 flex-wrap">
                    <StatusBadge intent={TRIGGER_INTENT[r.trigger_event] || 'default'}>
                      {TRIGGER_LABELS[r.trigger_event] || r.trigger_event}
                    </StatusBadge>
                    <ArrowRight className="h-3.5 w-3.5 text-slate-400" />
                    <div className={`p-1.5 rounded ${isWA ? 'bg-emerald-50' : 'bg-sky-50'}`}>
                      <Icon className={`h-4 w-4 ${isWA ? 'text-emerald-600' : 'text-sky-600'}`} />
                    </div>
                    <div className="flex-1 min-w-0">
                      <p className="font-medium text-sm text-slate-900">{r.name}</p>
                      <p className="text-xs text-slate-500 truncate">
                        {t('cm.pages_MessagingDashboard.sablon')} {tmpl?.name || 'Bilinmiyor'}
                        {r.delay_minutes > 0 && ` · ${r.delay_minutes} dk gecikme`}
                      </p>
                    </div>
                    <div className="text-right text-xs text-slate-500 hidden md:block">
                      <span className="text-emerald-600 font-medium">{r.total_sent || 0}</span> {t('cm.pages_MessagingDashboard.gonderim')}
                      {(r.total_failed || 0) > 0 && <span className="text-rose-500 ml-2">{r.total_failed} {t('cm.pages_MessagingDashboard.basarisiz_f592b')}</span>}
                    </div>
                    <div className="flex items-center gap-1">
                      <Button size="sm" variant="ghost" onClick={() => toggleEnabled(r)} title={r.enabled ? 'Devre dışı bırak' : 'Aktif et'}>
                        <Power className={`h-3.5 w-3.5 ${r.enabled ? 'text-emerald-600' : 'text-slate-400'}`} />
                      </Button>
                      <Button size="sm" variant="ghost" onClick={() => testRule(r)} title="Test et">
                        <Play className="h-3.5 w-3.5 text-sky-600" />
                      </Button>
                      <Button size="sm" variant="ghost" onClick={() => openEdit(r)}><Pencil className="h-3.5 w-3.5" /></Button>
                      <Button size="sm" variant="ghost" onClick={() => handleDelete(r.id)}><Trash2 className="h-3.5 w-3.5 text-rose-500" /></Button>
                    </div>
                  </div>
                </CardContent>
              </Card>
            );
          })}
        </div>
      )}

      {/* Pre-Arrival Scheduler */}
      <SchedulerCard />

      {/* Create/Edit Dialog */}
      <Dialog open={showCreate || !!editRule} onOpenChange={(v) => { if (!v) { setShowCreate(false); setEditRule(null); } }}>
        <DialogContent className="max-w-lg">
          <DialogHeader>
            <DialogTitle>{editRule ? 'Kuralı Düzenle' : 'Yeni Otomasyon Kuralı'}</DialogTitle>
          </DialogHeader>
          <div className="space-y-3">
            <div>
              <Label>{t('cm.pages_MessagingDashboard.kural_adi')}</Label>
              <Input data-testid="automation-name" value={form.name} onChange={(e) => setForm((p) => ({ ...p, name: e.target.value }))} placeholder={t('cm.pages_MessagingDashboard.hos_geldiniz_mesaji_959cf')} />
            </div>
            <div className="grid grid-cols-2 gap-3">
              <div>
                <Label>{t('cm.pages_MessagingDashboard.tetikleme_olayi')}</Label>
                <Select value={form.trigger_event} onValueChange={(v) => setForm((p) => ({ ...p, trigger_event: v }))}>
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
                <Select value={form.channel} onValueChange={(v) => setForm((p) => ({ ...p, channel: v, template_id: '' }))}>
                  <SelectTrigger data-testid="automation-channel"><SelectValue /></SelectTrigger>
                  <SelectContent>
                    <SelectItem value="whatsapp">WhatsApp</SelectItem>
                    <SelectItem value="email">E-posta</SelectItem>
                  </SelectContent>
                </Select>
              </div>
            </div>
            <div>
              <Label>{t('cm.pages_MessagingDashboard.sablon_68cce')}</Label>
              <Select value={form.template_id} onValueChange={(v) => setForm((p) => ({ ...p, template_id: v }))}>
                <SelectTrigger data-testid="automation-template"><SelectValue placeholder={t('cm.pages_MessagingDashboard.sablon_secin')} /></SelectTrigger>
                <SelectContent>
                  {filteredTemplates.length === 0 ? (
                    <SelectItem value="__none" disabled>{t('cm.pages_MessagingDashboard.bu_kanal_icin_sablon_yok')}</SelectItem>
                  ) : filteredTemplates.map((t) => (
                    <SelectItem key={t.id} value={t.id}>{t.name} ({CATEGORY_LABELS[t.category] || t.category})</SelectItem>
                  ))}
                </SelectContent>
              </Select>
            </div>
            <div className="flex items-center gap-2">
              <Switch checked={form.enabled} onCheckedChange={(v) => setForm((p) => ({ ...p, enabled: v }))} />
              <Label>{t('cm.pages_MessagingDashboard.aktif_81c33')}</Label>
            </div>
          </div>
          <DialogFooter>
            <Button variant="outline" onClick={() => { setShowCreate(false); setEditRule(null); }}>{t('cm.pages_MessagingDashboard.iptal_25174')}</Button>
            <Button data-testid="automation-save-btn" onClick={editRule ? handleUpdate : handleCreate}>
              {editRule ? 'Güncelle' : 'Oluştur'}
            </Button>
          </DialogFooter>
        </DialogContent>
      </Dialog>
    </div>
  );
}

// ════════════════════════════════════════════════
// Scheduler Card (inside Automation Tab)
// ════════════════════════════════════════════════
function SchedulerCard() {
  const [status, setStatus] = useState(null);
  const [loading, setLoading] = useState(true);
  const [actionLoading, setActionLoading] = useState(false);

  const load = useCallback(async () => {
    setLoading(true);
    const r = await safe(() => get('/api/messaging-center/scheduler/status'));
    if (r.ok) setStatus(r.data);
    setLoading(false);
  }, []);
  useEffect(() => { load(); }, [load]);

  const toggleScheduler = async () => {
    setActionLoading(true);
    if (status?.status === 'running') {
      await safe(() => post('/api/messaging-center/scheduler/stop', {}));
      toast.success('Zamanlayıcı durduruldu');
    } else {
      await safe(() => post('/api/messaging-center/scheduler/start', {}));
      toast.success('Zamanlayıcı başlatıldı');
    }
    await load();
    setActionLoading(false);
  };

  const runNow = async () => {
    setActionLoading(true);
    const r = await safe(() => post('/api/messaging-center/scheduler/run-now', {}));
    if (r.ok && r.data.success) {
      const x = r.data.result || {};
      toast.success(`Tarama tamamlandı: ${x.events_fired || 0} mesaj tetiklendi, ${x.bookings_scanned || 0} rezervasyon tarandı`);
    } else if (r.ok) {
      toast.error('Tarama hatası');
    }
    await load();
    setActionLoading(false);
  };

  if (loading) return null;

  const isRunning = status?.status === 'running';

  return (
    <Card data-testid="scheduler-card" className="border-dashed">
      <CardContent className="py-4">
        <div className="flex items-center justify-between flex-wrap gap-2">
          <div className="flex items-center gap-3">
            <div className={`p-2 rounded-lg ${isRunning ? 'bg-emerald-50' : 'bg-slate-100'}`}>
              <Timer className={`h-5 w-5 ${isRunning ? 'text-emerald-600' : 'text-slate-400'}`} />
            </div>
            <div>
              <h4 className="text-sm font-semibold flex items-center gap-2 text-slate-900">
                {t('cm.pages_MessagingDashboard.pre_arrival_zamanlayici')}
                <StatusBadge intent={isRunning ? 'success' : 'neutral'}>
                  {isRunning ? 'Aktif' : 'Durduruldu'}
                </StatusBadge>
              </h4>
              <p className="text-xs text-slate-500">
                {t('cm.pages_MessagingDashboard.yarinki_check_in_leri_tarayip_otomatik_y')}
              </p>
            </div>
          </div>
          <div className="flex items-center gap-2">
            <Button data-testid="scheduler-run-now-btn" size="sm" variant="outline" onClick={runNow} disabled={actionLoading}>
              {actionLoading ? <Loader2 className="h-3.5 w-3.5 animate-spin" /> : <Play className="h-3.5 w-3.5" />}
              <span className="ml-1">{t('cm.pages_MessagingDashboard.simdi_tara')}</span>
            </Button>
            <Button
              data-testid="scheduler-toggle-btn"
              size="sm"
              variant={isRunning ? 'destructive' : 'default'}
              onClick={toggleScheduler}
              disabled={actionLoading}
            >
              <Power className="h-3.5 w-3.5 mr-1" />
              {isRunning ? 'Durdur' : 'Başlat'}
            </Button>
          </div>
        </div>
        {status?.last_run_result && (
          <div className="mt-3 grid grid-cols-4 gap-2 text-center text-xs">
            <div className="bg-slate-50 rounded p-2">
              <p className="font-bold text-slate-700">{status.total_runs || 0}</p>
              <p className="text-slate-500">{t('cm.pages_MessagingDashboard.toplam_tarama')}</p>
            </div>
            <div className="bg-emerald-50 rounded p-2">
              <p className="font-bold text-emerald-700">{status.total_sent || 0}</p>
              <p className="text-emerald-600">{t('cm.pages_MessagingDashboard.gonderilen')}</p>
            </div>
            <div className="bg-amber-50 rounded p-2">
              <p className="font-bold text-amber-700">{status.total_skipped || 0}</p>
              <p className="text-amber-600">{t('cm.pages_MessagingDashboard.zaten_gonderilmis')}</p>
            </div>
            <div className="bg-rose-50 rounded p-2">
              <p className="font-bold text-rose-700">{status.total_errors || 0}</p>
              <p className="text-rose-600">{t('cm.pages_MessagingDashboard.hata')}</p>
            </div>
          </div>
        )}
        {status?.last_run_at && (
          <p className="text-[10px] text-slate-500 mt-2">
            Son tarama: {new Date(status.last_run_at).toLocaleString('tr-TR')}
            {status.interval_hours && ` · Her ${status.interval_hours} saatte bir`}
          </p>
        )}
      </CardContent>
    </Card>
  );
}

// ════════════════════════════════════════════════
// WhatsApp HSM Template Tab (Bug #13)
// ════════════════════════════════════════════════
function WhatsAppTemplateTab() {
  const [recipient, setRecipient] = useState('');
  const [templateName, setTemplateName] = useState('');
  const [languageCode, setLanguageCode] = useState('tr');
  const [paramsText, setParamsText] = useState('');
  const [sending, setSending] = useState(false);

  const recipientCheck = useMemo(() => validateRecipient('whatsapp', recipient), [recipient]);

  const handleSend = async () => {
    if (!recipientCheck.ok) { toast.error(recipientCheck.msg); return; }
    if (!templateName.trim()) { toast.error('Template adı (Meta panelinde onaylı) gerekli'); return; }
    const params = paramsText.split('\n').map((s) => s.trim()).filter(Boolean);
    const components = params.length
      ? [{ type: 'body', parameters: params.map((t) => ({ type: 'text', text: t })) }]
      : [];
    setSending(true);
    const r = await safe(() => post('/api/messaging-center/send-template', {
      recipient,
      template_name: templateName,
      language_code: languageCode,
      components,
    }));
    if (r.ok && r.data.success) {
      toast.success('Template gönderildi');
      setRecipient(''); setParamsText('');
    } else if (r.ok) {
      toast.error(r.data.error || 'Template gönderim hatası');
    }
    setSending(false);
  };

  return (
    <div className="space-y-4" data-testid="hsm-tab">
      <Card className="border-amber-200 bg-amber-50">
        <CardContent className="py-3 flex items-start gap-3">
          <Shield className="h-5 w-5 text-amber-600 flex-shrink-0 mt-0.5" />
          <div className="flex-1">
            <p className="text-sm font-medium text-amber-900">{t('cm.pages_MessagingDashboard.whatsapp_hsm_onayli_template_gonderimi')}</p>
            <p className="text-xs text-amber-700">
              {t('cm.pages_MessagingDashboard.ilk_temas_24_saatlik_konusma_penceresi_d_13772')} <strong>APPROVED</strong> {t('cm.pages_MessagingDashboard.durumda_olmalidir')}
            </p>
          </div>
        </CardContent>
      </Card>
      <Card>
        <CardContent className="pt-6 space-y-4">
          <div className="grid grid-cols-1 md:grid-cols-2 gap-4">
            <div>
              <Label>{t('cm.pages_MessagingDashboard.telefon_numarasi_e_164')}</Label>
              <Input value={recipient} onChange={(e) => setRecipient(e.target.value)} placeholder="+905551234567"
                className={recipient && !recipientCheck.ok ? 'border-rose-400' : ''} />
              {recipient && !recipientCheck.ok && (
                <p className="text-xs text-rose-600 mt-1">{recipientCheck.msg}</p>
              )}
            </div>
            <div>
              <Label>Dil Kodu</Label>
              <Select value={languageCode} onValueChange={setLanguageCode}>
                <SelectTrigger><SelectValue /></SelectTrigger>
                <SelectContent>
                  <SelectItem value="tr">{t('cm.pages_MessagingDashboard.turkce_tr')}</SelectItem>
                  <SelectItem value="en">English (en)</SelectItem>
                  <SelectItem value="en_US">English US (en_US)</SelectItem>
                </SelectContent>
              </Select>
            </div>
          </div>
          <div>
            <Label>{t('cm.pages_MessagingDashboard.template_adi_meta_da_onayli')}</Label>
            <Input value={templateName} onChange={(e) => setTemplateName(e.target.value)} placeholder="hello_world" />
          </div>
          <div>
            <Label>{t('cm.pages_MessagingDashboard.body_parametreleri_her_satir_bir_paramet')}</Label>
            <Textarea
              className="min-h-[100px] font-mono text-xs"
              value={paramsText}
              onChange={(e) => setParamsText(e.target.value)}
              placeholder={'Ahmet\n16:00\nDeluxe Oda'}
            />
            <p className="text-xs text-slate-500 mt-1">
              Template body'sindeki {'{{1}}'}, {'{{2}}'} {t('cm.pages_MessagingDashboard.placeholder_sirasiyla_bu_parametrelerle_')}
            </p>
          </div>
          <Button onClick={handleSend} disabled={sending || !recipientCheck.ok || !templateName.trim()} className="w-full">
            {sending ? <Loader2 className="h-4 w-4 animate-spin mr-2" /> : <Send className="h-4 w-4 mr-2" />}
            {t('cm.pages_MessagingDashboard.template_gonder')}
          </Button>
        </CardContent>
      </Card>
    </div>
  );
}

// ════════════════════════════════════════════════
// Activity Tab
// ════════════════════════════════════════════════
function ActivityTab() {
  const [activities, setActivities] = useState([]);
  const [loading, setLoading] = useState(true);

  const load = useCallback(async () => {
    setLoading(true);
    const r = await safe(() => get('/api/messaging-center/activity?limit=30'));
    if (r.ok) setActivities(r.data.activities || []);
    setLoading(false);
  }, []);

  useEffect(() => {
    load();
    const interval = setInterval(load, 10000);
    return () => clearInterval(interval);
  }, [load]);

  if (loading && activities.length === 0) {
    return <div className="flex items-center justify-center py-12"><Loader2 className="h-6 w-6 animate-spin text-slate-400" /></div>;
  }

  const getIcon = (a) => {
    if (a.type === 'automation') return a.priority === 'high' ? XCircle : CheckCircle2;
    if (a.status === 'sent' || a.status === 'delivered') return CheckCircle2;
    if (a.status === 'failed') return XCircle;
    return Clock;
  };
  const getIntent = (a) => {
    if (a.priority === 'high' || a.status === 'failed') return 'danger';
    if (a.status === 'sent' || a.status === 'delivered') return 'success';
    if (a.type === 'automation' && a.priority === 'normal') return 'info';
    return 'warning';
  };
  const intentBg = {
    danger: 'bg-rose-50 text-rose-600',
    success: 'bg-emerald-50 text-emerald-600',
    info: 'bg-sky-50 text-sky-600',
    warning: 'bg-amber-50 text-amber-600',
  };

  return (
    <div className="space-y-3" data-testid="activity-tab">
      <div className="flex items-center justify-between">
        <h3 className="font-semibold text-sm text-slate-900">{t('cm.pages_MessagingDashboard.canli_aktivite')}</h3>
        <Button variant="outline" size="sm" onClick={load} data-testid="activity-refresh-btn">
          <RefreshCw className="w-4 h-4 mr-1.5" /> {t('cm.pages_MessagingDashboard.yenile_aedf3')}
        </Button>
      </div>

      {activities.length === 0 ? (
        <Card><CardContent className="py-10 text-center text-slate-500">
          <Bell className="h-8 w-8 mx-auto mb-2 opacity-40" />
          <p className="font-medium">{t('cm.pages_MessagingDashboard.henuz_aktivite_yok')}</p>
          <p className="text-xs mt-1">{t('cm.pages_MessagingDashboard.otomasyon_tetiklendikce_ve_mesajlar_gond')}</p>
        </CardContent></Card>
      ) : (
        <div className="space-y-1.5">
          {activities.map((a, i) => {
            const Icon = getIcon(a);
            const intent = getIntent(a);
            return (
              <Card key={`${a.id}-${i}`} className="border-0 shadow-none bg-transparent">
                <CardContent className="py-2 px-3">
                  <div className="flex items-center gap-3">
                    <div className={`p-1.5 rounded ${intentBg[intent]}`}>
                      <Icon className="h-3.5 w-3.5" />
                    </div>
                    <div className="flex-1 min-w-0">
                      <p className="text-sm font-medium truncate text-slate-900">{a.title}</p>
                      <p className="text-xs text-slate-500 truncate">{a.message}</p>
                    </div>
                    <div className="flex items-center gap-2">
                      <StatusBadge intent="neutral">
                        {a.type === 'automation' ? 'Otomasyon' : 'Gönderim'}
                      </StatusBadge>
                      <span className="text-[10px] text-slate-500 whitespace-nowrap">
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

// ════════════════════════════════════════════════
// Main Dashboard
// ════════════════════════════════════════════════
export default function MessagingDashboard() {
  const [refreshKey, setRefreshKey] = useState(0);
  const refresh = useCallback(() => setRefreshKey((k) => k + 1), []);

  useEffect(() => {
    // Auto-seed demo data on first load (only when truly empty)
    (async () => {
      const r = await safe(() => get('/api/messaging-center/delivery-logs?limit=1'));
      if (r.ok && (!r.data.logs || r.data.logs.length === 0)) {
        await safe(() => post('/api/messaging-center/seed-demo', {}));
      }
    })();
  }, []);

  return (
    <div data-testid="messaging-dashboard" className="p-4 lg:p-6 max-w-7xl mx-auto" key={refreshKey}>
      <PageHeader
        icon={MessageSquare}
        title={t('cm.pages_MessagingDashboard.mesajlasma_merkezi')}
        subtitle={t('cm.pages_MessagingDashboard.e_posta_smtp_ve_whatsapp_business_ile_mi')}
        actions={
          <Button variant="outline" size="sm" onClick={refresh}>
            <RefreshCw className="w-4 h-4 mr-1.5" /> {t('cm.pages_MessagingDashboard.yenile_aedf3')}
          </Button>
        }
      />

      <Card className="border-sky-200 bg-sky-50 mb-4">
        <CardContent className="py-3 flex items-start gap-3">
          <AlertTriangle className="h-5 w-5 text-sky-600 flex-shrink-0 mt-0.5" />
          <div className="flex-1 text-xs text-sky-900">
            <strong>Not:</strong> {t('cm.pages_MessagingDashboard.bu_modul_operasyonel_transactional_mesaj')} <strong>Mailing</strong> {t('cm.pages_MessagingDashboard.modulunu_resend_tabanli_kredi_sistemli_k')}
          </div>
        </CardContent>
      </Card>

      <Tabs defaultValue="send">
        <TabsList className="grid w-full grid-cols-4 md:grid-cols-8 max-w-5xl" data-testid="messaging-tabs">
          <TabsTrigger data-testid="tab-send" value="send" className="flex items-center gap-1.5">
            <Send className="h-3.5 w-3.5" /> {t('cm.pages_MessagingDashboard.gonder')}
          </TabsTrigger>
          <TabsTrigger data-testid="tab-templates" value="templates" className="flex items-center gap-1.5">
            <FileText className="h-3.5 w-3.5" /> {t('cm.pages_MessagingDashboard.sablonlar')}
          </TabsTrigger>
          <TabsTrigger data-testid="tab-automation" value="automation" className="flex items-center gap-1.5">
            <Zap className="h-3.5 w-3.5" /> Otomasyon
          </TabsTrigger>
          <TabsTrigger data-testid="tab-hsm" value="hsm" className="flex items-center gap-1.5">
            <Shield className="h-3.5 w-3.5" /> HSM
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
        <TabsContent value="hsm"><WhatsAppTemplateTab /></TabsContent>
        <TabsContent value="activity"><ActivityTab /></TabsContent>
        <TabsContent value="logs"><DeliveryLogsTab /></TabsContent>
        <TabsContent value="metrics"><MetricsTab /></TabsContent>
        <TabsContent value="settings"><SettingsTab onChanged={refresh} /></TabsContent>
      </Tabs>
    </div>
  );
}
