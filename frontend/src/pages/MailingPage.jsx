import { useState, useEffect, useCallback } from 'react';
import axios from 'axios';
import { toast } from 'sonner';
import { Card, CardContent, CardDescription, CardHeader, CardTitle } from '@/components/ui/card';
import { Input } from '@/components/ui/input';
import { Label } from '@/components/ui/label';
import { Button } from '@/components/ui/button';
import { Textarea } from '@/components/ui/textarea';
import { Tabs, TabsContent, TabsList, TabsTrigger } from '@/components/ui/tabs';
import { Badge } from '@/components/ui/badge';
import { Switch } from '@/components/ui/switch';
import { PageHeader } from '@/components/ui/page-header';
import { KpiCard } from '@/components/ui/kpi-card';
import { Mail, Users, FileText, Send, Trash2, Plus, Sparkles, AlertCircle, Zap, RefreshCw, Wallet, Gift, BarChart3 } from 'lucide-react';
import { useNavigate } from 'react-router-dom';

import { confirmDialog } from '@/lib/dialogs';
import { useTranslation } from 'react-i18next';
const API = '/mailing';

export default function MailingPage({ user, tenant, onLogout }) {
  const { t, i18n } = useTranslation();
  const [credits, setCredits] = useState(null);
  const [templates, setTemplates] = useState([]);
  const [recipients, setRecipients] = useState([]);
  const [campaigns, setCampaigns] = useState([]);
  const [automations, setAutomations] = useState([]);
  const [loading, setLoading] = useState(true);

  const refresh = useCallback(async () => {
    setLoading(true);
    // Promise.allSettled — bir endpoint düşse bile diğer sekmeler render olsun.
    // Daha önce Promise.all ile tek bir 5xx tüm sayfayı blank bırakıyordu
    // ("Mailing verileri yüklenemedi" toast + boş ekran).
    const results = await Promise.allSettled([
      axios.get(`${API}/credits`),
      axios.get(`${API}/templates`),
      axios.get(`${API}/recipients`),
      axios.get(`${API}/campaigns`),
      axios.get(`${API}/automations`),
    ]);
    const [c, t, r, cp, au] = results;
    if (c.status === 'fulfilled') setCredits(c.value.data);
    if (t.status === 'fulfilled') setTemplates(t.value.data || []);
    if (r.status === 'fulfilled') setRecipients(r.value.data || []);
    if (cp.status === 'fulfilled') setCampaigns(cp.value.data || []);
    if (au.status === 'fulfilled') setAutomations(au.value.data?.automations || []);
    const failedLabels = [
      [c, 'kredi'], [t, 'şablonlar'], [r, 'alıcılar'],
      [cp, 'kampanya geçmişi'], [au, 'otomasyon'],
    ].filter(([res]) => res.status === 'rejected').map(([, l]) => l);
    if (failedLabels.length === results.length) {
      toast.error('Mailing verileri yüklenemedi — sunucu yanıt vermiyor');
    } else if (failedLabels.length > 0) {
      toast.warning(`Bazı veriler yüklenemedi: ${failedLabels.join(', ')}`);
    }
    setLoading(false);
  }, []);

  useEffect(() => { refresh(); }, [refresh]);

  return (
    <div className="container mx-auto p-6 max-w-7xl space-y-6">
      <PageHeader
        icon={Mail}
        title="E-posta Pazarlama"
        subtitle={t('cm.pages_MailingPage.misafirlerinize_toplu_e_posta_gonderin_s')}
        actions={
          <Button variant="outline" size="sm" onClick={refresh} disabled={loading}>
            <RefreshCw className={`w-4 h-4 mr-1.5 ${loading ? 'animate-spin' : ''}`} />
            {t('cm.pages_MailingPage.yenile')}
          </Button>
        }
      />

      {credits && (
        <div className="grid grid-cols-1 sm:grid-cols-3 gap-3">
          <KpiCard
            icon={Wallet}
            label="Kalan Kredi"
            value={credits.balance.toLocaleString(i18n.language)}
            sub={credits.balance < 50 ? 'Düşük bakiye — yükleme önerilir' : 'Kullanıma hazır'}
            intent={credits.balance < 50 ? 'warning' : 'info'}
          />
          <KpiCard
            icon={Send}
            label={t('cm.pages_MailingPage.bugun_gonderilen')}
            value={(credits.sent_today ?? 0).toLocaleString(i18n.language)}
            sub="Son 24 saat"
            intent="default"
          />
          <KpiCard
            icon={BarChart3}
            label={t('cm.pages_MailingPage.toplam_gonderim')}
            value={(credits.lifetime_used ?? 0).toLocaleString(i18n.language)}
            sub="Hesabın açıldığı günden bu yana"
            intent="success"
          />
        </div>
      )}

      <Tabs defaultValue="campaign" className="space-y-4">
        <TabsList className="grid w-full grid-cols-5">
          <TabsTrigger value="campaign"><Send className="w-4 h-4 mr-1.5" />Kampanya</TabsTrigger>
          <TabsTrigger value="automations"><Zap className="w-4 h-4 mr-1.5" />Otomasyon</TabsTrigger>
          <TabsTrigger value="templates"><FileText className="w-4 h-4 mr-1.5" />{t('cm.pages_MailingPage.sablonlar')}</TabsTrigger>
          <TabsTrigger value="history"><Sparkles className="w-4 h-4 mr-1.5" />{t('cm.pages_MailingPage.gecmis')}</TabsTrigger>
          <TabsTrigger value="credits"><AlertCircle className="w-4 h-4 mr-1.5" />Krediler</TabsTrigger>
        </TabsList>

        <TabsContent value="campaign">
          <CampaignTab
            templates={templates}
            recipients={recipients}
            credits={credits}
            onSent={refresh}
          />
        </TabsContent>
        <TabsContent value="automations">
          <AutomationsTab automations={automations} templates={templates} onChanged={refresh} />
        </TabsContent>
        <TabsContent value="templates">
          <TemplatesTab templates={templates} onChanged={refresh} />
        </TabsContent>
        <TabsContent value="history">
          <HistoryTab campaigns={campaigns} loading={loading} />
        </TabsContent>
        <TabsContent value="credits">
          <CreditsTab credits={credits} />
        </TabsContent>
      </Tabs>
    </div>
  );
}

// ── Campaign Tab ──────────────────────────────────────────────
function CampaignTab({ templates, recipients, credits, onSent }) {
  const { t, i18n } = useTranslation();
  const [name, setName] = useState('');
  const [templateId, setTemplateId] = useState('');
  const [subject, setSubject] = useState('');
  const [html, setHtml] = useState('');
  const [selected, setSelected] = useState(new Set());
  const [search, setSearch] = useState('');
  const [testEmail, setTestEmail] = useState('');
  const [sending, setSending] = useState(false);

  const tpl = templates.find(t => t.id === templateId);
  useEffect(() => {
    if (tpl) { setSubject(tpl.subject); setHtml(tpl.html); }
  }, [templateId, tpl]);

  const filtered = recipients.filter(r =>
    !search || r.name.toLowerCase().includes(search.toLowerCase()) || r.email.toLowerCase().includes(search.toLowerCase())
  );

  const toggleAll = () => {
    if (selected.size === filtered.length) setSelected(new Set());
    else setSelected(new Set(filtered.map(r => r.id)));
  };

  const balance = credits?.balance ?? 0;
  const insufficientForTest = balance < 1;

  const sendTest = async () => {
    if (!testEmail) { toast.error('Test e-posta adresi girin'); return; }
    if (!subject || !html) { toast.error('Konu ve içerik gerekli'); return; }
    if (insufficientForTest) { toast.error('Yetersiz kredi: en az 1 kredi gerekli'); return; }
    setSending(true);
    try {
      const res = await axios.post(`${API}/campaigns`, {
        name: name || 'Test Gönderimi', subject, html, test_email: testEmail,
      });
      toast.success(`Test e-postası gönderildi (${res.data.sent_count}/1)`);
      onSent();
    } catch (e) {
      toast.error(e.response?.data?.detail || 'Test gönderilemedi');
    } finally { setSending(false); }
  };

  const sendCampaign = async () => {
    if (!name) { toast.error('Kampanya adı gerekli'); return; }
    if (selected.size === 0) { toast.error('En az 1 alıcı seçin'); return; }
    if (!subject || !html) { toast.error('Konu ve içerik gerekli'); return; }
    if (selected.size > balance) {
      toast.error(`Yetersiz kredi: ${selected.size} gerekli, ${balance} mevcut`);
      return;
    }
    if (!await confirmDialog({ message: `${selected.size} misafire e-posta gönderilecek. Onaylıyor musunuz?` })) return;
    setSending(true);
    try {
      const res = await axios.post(`${API}/campaigns`, {
        name, subject, html,
        template_id: templateId || null,
        recipient_ids: Array.from(selected),
      });
      toast.success(`Gönderildi: ${res.data.sent_count} başarılı, ${res.data.failed_count} hatalı`);
      setSelected(new Set()); setName('');
      onSent();
    } catch (e) {
      toast.error(e.response?.data?.detail || 'Gönderim başarısız');
    } finally { setSending(false); }
  };

  const insufficientForCampaign = selected.size === 0 || selected.size > balance;

  return (
    <div className="grid lg:grid-cols-2 gap-6">
      <Card>
        <CardHeader>
          <CardTitle>{t('cm.pages_MailingPage.1_icerik')}</CardTitle>
          <CardDescription>{t('cm.pages_MailingPage.sablon_secin_veya_yeni_icerik_yazin')}</CardDescription>
        </CardHeader>
        <CardContent className="space-y-4">
          <div>
            <Label>{t('cm.pages_MailingPage.kampanya_adi')}</Label>
            <Input value={name} onChange={e => setName(e.target.value)} placeholder={t('cm.pages_MailingPage.orn_mart_kampanyasi')} />
          </div>
          <div>
            <Label>{t('cm.pages_MailingPage.sablon_opsiyonel')}</Label>
            <select className="w-full border rounded px-3 py-2 text-sm"
              value={templateId} onChange={e => setTemplateId(e.target.value)}>
              <option value="">{t('cm.pages_MailingPage.sablonsuz')}</option>
              {templates.map(t => <option key={t.id} value={t.id}>{t.name}</option>)}
            </select>
          </div>
          <div>
            <Label>Konu</Label>
            <Input value={subject} onChange={e => setSubject(e.target.value)} placeholder="E-posta konusu" />
          </div>
          <div>
            <Label>{t('cm.pages_MailingPage.icerik_html')}</Label>
            <Textarea rows={10} value={html} onChange={e => setHtml(e.target.value)}
              placeholder="<h2>Merhaba {{name}},</h2><p>...</p>"
              className="font-mono text-xs" />
            <p className="text-xs text-muted-foreground mt-1">
              {t('cm.pages_MailingPage.degiskenler')} <code>{'{{name}}'}</code> {t('cm.pages_MailingPage.misafir_adi')} <code>{'{{hotel}}'}</code> {t('cm.pages_MailingPage.otel_adi')}
            </p>
          </div>
          <div className="border-t pt-3">
            <Label className="text-xs">{t('cm.pages_MailingPage.test_gonderimi_1_kredi')}</Label>
            <div className="flex gap-2 mt-1">
              <Input type="email" value={testEmail} onChange={e => setTestEmail(e.target.value)}
                placeholder="test@adresiniz.com" />
              <Button
                variant="outline"
                onClick={sendTest}
                disabled={sending || insufficientForTest}
                title={insufficientForTest ? 'Test göndermek için en az 1 kredi gerekli' : undefined}
              >
                {t('cm.pages_MailingPage.test_gonder')}
              </Button>
            </div>
            {insufficientForTest && (
              <p className="text-xs text-amber-700 mt-1">{t('cm.pages_MailingPage.test_gonderimi_icin_en_az_1_kredi_gerekl')}</p>
            )}
          </div>
        </CardContent>
      </Card>

      <Card>
        <CardHeader>
          <CardTitle>{t('cm.pages_MailingPage.2_alicilar')}</CardTitle>
          <CardDescription>{recipients.length} {t('cm.pages_MailingPage.misafir_e_postasi_mevcut')} {selected.size} {t('cm.pages_MailingPage.secili')}</CardDescription>
        </CardHeader>
        <CardContent>
          <div className="flex flex-wrap gap-2 mb-2">
            <Button size="sm" variant="secondary" type="button"
              onClick={async () => {
                try {
                  const r = await axios.get(`${API}/recipients/quick/today_in`);
                  const ids = (r.data.recipients || []).map(x => x.id);
                  setSelected(new Set(ids));
                  toast.success(`Bugün girişli ${ids.length} misafir seçildi`);
                } catch { toast.error('Filtre uygulanamadı'); }
              }}>{t('cm.pages_MailingPage.bugun_girisliler')}</Button>
            <Button size="sm" variant="secondary" type="button"
              onClick={async () => {
                try {
                  const r = await axios.get(`${API}/recipients/quick/today_out`);
                  const ids = (r.data.recipients || []).map(x => x.id);
                  setSelected(new Set(ids));
                  toast.success(`Bugün çıkışlı ${ids.length} misafir seçildi`);
                } catch { toast.error('Filtre uygulanamadı'); }
              }}>{t('cm.pages_MailingPage.bugun_cikislilar')}</Button>
            <Button size="sm" variant="secondary" type="button"
              onClick={async () => {
                try {
                  const r = await axios.get(`${API}/recipients/quick/in_house`);
                  const ids = (r.data.recipients || []).map(x => x.id);
                  setSelected(new Set(ids));
                  toast.success(`Otelde konaklayan ${ids.length} misafir seçildi`);
                } catch { toast.error('Filtre uygulanamadı'); }
              }}>{t('cm.pages_MailingPage.iceride_konaklayanlar')}</Button>
          </div>
          <div className="flex gap-2 mb-3">
            <Input placeholder={t('cm.pages_MailingPage.isim_veya_e_posta_ara')} value={search} onChange={e => setSearch(e.target.value)} />
            <Button variant="outline" onClick={toggleAll}>
              {selected.size === filtered.length && filtered.length > 0 ? 'Tümünü Kaldır' : 'Tümünü Seç'}
            </Button>
          </div>
          <div className="border rounded max-h-96 overflow-y-auto divide-y">
            {filtered.length === 0 && (
              <div className="p-8 text-center text-sm text-muted-foreground">
                <Users className="w-8 h-8 mx-auto mb-2 opacity-40" />
                {t('cm.pages_MailingPage.e_postali_misafir_bulunamadi')}
              </div>
            )}
            {filtered.map(r => (
              <label key={r.id} className="flex items-center gap-3 p-2 hover:bg-slate-50 cursor-pointer">
                <input
                  type="checkbox"
                  checked={selected.has(r.id)}
                  onChange={(e) => {
                    const ns = new Set(selected);
                    if (e.target.checked) ns.add(r.id); else ns.delete(r.id);
                    setSelected(ns);
                  }}
                />
                <div className="flex-1 min-w-0">
                  <div className="text-sm font-medium truncate">{r.name}</div>
                  <div className="text-xs text-muted-foreground truncate">{r.email}</div>
                </div>
              </label>
            ))}
          </div>
          <Button
            className="w-full mt-4"
            onClick={sendCampaign}
            disabled={sending || insufficientForCampaign}
            title={selected.size > balance ? `Yetersiz kredi (${selected.size}/${balance})` : undefined}
          >
            <Send className="w-4 h-4 mr-2" />
            {sending
              ? 'Gönderiliyor…'
              : `${selected.size} alıcıya gönder (${selected.size} kredi)`}
          </Button>
          {selected.size > balance && (
            <p className="text-xs text-amber-700 mt-2 text-center">
              Yetersiz kredi: {selected.size} gerekli, {balance} mevcut.
            </p>
          )}
        </CardContent>
      </Card>
    </div>
  );
}

// ── Automations Tab ──────────────────────────────────────────
function AutomationsTab({ automations, templates, onChanged }) {
  const { t, i18n } = useTranslation();
  const navigate = useNavigate();
  const noTemplates = templates.length === 0;

  const save = async (a, patch) => {
    try {
      await axios.put(`${API}/automations/${a.trigger_type}`, {
        enabled: patch.enabled ?? a.enabled,
        template_id: patch.template_id ?? a.template_id,
        offset_days: patch.offset_days ?? a.offset_days,
      });
      toast.success('Otomasyon güncellendi');
      onChanged();
    } catch (e) {
      toast.error(e.response?.data?.detail || 'Güncellenemedi');
    }
  };

  return (
    <div className="space-y-4">
      <Card className="bg-slate-50 border-slate-200">
        <CardContent className="pt-4">
          <p className="text-sm text-slate-700">
            <strong>{t('cm.pages_MailingPage.nasil_calisir')}</strong> {t('cm.pages_MailingPage.asagidan_bir_tetikleyici_secip_sablon_at')} <strong>bir kez</strong> {t('cm.pages_MailingPage.mail_gonderilir_kredi_yetersizse_otomasy')}
          </p>
        </CardContent>
      </Card>
      {noTemplates && (
        <Card className="border-amber-200 bg-amber-50">
          <CardContent className="pt-4 flex items-start justify-between gap-4">
            <div className="flex items-start gap-3">
              <FileText className="w-5 h-5 text-amber-600 mt-0.5 flex-shrink-0" />
              <div>
                <div className="font-semibold text-amber-900">{t('cm.pages_MailingPage.once_sablon_olusturun')}</div>
                <p className="text-sm text-amber-800 mt-1">
                  {t('cm.pages_MailingPage.otomasyonlari_aktif_edebilmek_icin_en_az')}
                </p>
              </div>
            </div>
            <Button variant="outline" size="sm" onClick={() => {
              const trigger = document.querySelector('[role="tab"][value="templates"]');
              trigger?.click();
            }}>
              <Plus className="w-4 h-4 mr-1.5" />
              {t('cm.pages_MailingPage.sablon_olustur')}
            </Button>
          </CardContent>
        </Card>
      )}
      {automations.length === 0 && !noTemplates && (
        <div className="text-center py-12 text-muted-foreground">{t('cm.pages_MailingPage.yukleniyor')}</div>
      )}
      {automations.map(a => (
        <Card key={a.trigger_type}>
          <CardContent className="pt-6">
            <div className="flex items-start justify-between gap-4">
              <div className="flex-1 min-w-0">
                <div className="flex items-center gap-2 mb-1">
                  <Zap className={`w-5 h-5 ${a.enabled ? 'text-emerald-600' : 'text-slate-400'}`} />
                  <h3 className="font-semibold text-lg">{a.label}</h3>
                  {a.enabled && (
                    <Badge className="bg-emerald-100 text-emerald-700 hover:bg-emerald-100">{t('cm.pages_MailingPage.aktif')}</Badge>
                  )}
                </div>
                <p className="text-sm text-muted-foreground mb-3">{a.description}</p>
                <div className="grid sm:grid-cols-2 gap-3">
                  <div>
                    <Label className="text-xs">{t('cm.pages_MailingPage.sablon')}</Label>
                    <select
                      className="w-full border rounded px-3 py-2 text-sm mt-1 disabled:opacity-50"
                      value={a.template_id || ''}
                      disabled={noTemplates}
                      onChange={e => save(a, { template_id: e.target.value || null })}>
                      <option value="">{t('cm.pages_MailingPage.sablon_secin')}</option>
                      {templates.map(t => <option key={t.id} value={t.id}>{t.name}</option>)}
                    </select>
                  </div>
                  <div>
                    <Label className="text-xs">
                      {t('cm.pages_MailingPage.gun_farki')} {a.trigger_type === 'checkin_reminder' ? '(check-in öncesi)' :
                                a.trigger_type === 'checkout_thanks' ? '(check-out sonrası)' : '(0 = anında)'}
                    </Label>
                    <Input type="number" className="mt-1" value={a.offset_days ?? 0}
                      onChange={e => save(a, { offset_days: parseInt(e.target.value || '0', 10) })} />
                  </div>
                </div>
                {a.last_run_at && (
                  <p className="text-xs text-muted-foreground mt-2">
                    {t('cm.pages_MailingPage.son_calisma')} {new Date(a.last_run_at).toLocaleString(i18n.language)} • {a.last_sent_count} {t('cm.pages_MailingPage.gonderim')}
                  </p>
                )}
              </div>
              <Switch
                checked={a.enabled}
                disabled={noTemplates && !a.enabled}
                onCheckedChange={(v) => save(a, { enabled: v })}
              />
            </div>
          </CardContent>
        </Card>
      ))}
    </div>
  );
}


// ── Templates Tab ──────────────────────────────────────────────
function TemplatesTab({ templates, onChanged }) {
  const { t, i18n } = useTranslation();
  const [editing, setEditing] = useState(null);
  const empty = { name: '', subject: '', html: '', description: '' };

  const save = async (data) => {
    try {
      if (data.id) await axios.put(`${API}/templates/${data.id}`, data);
      else await axios.post(`${API}/templates`, data);
      toast.success('Şablon kaydedildi');
      setEditing(null);
      onChanged();
    } catch (e) {
      toast.error(e.response?.data?.detail || 'Kaydedilemedi');
    }
  };

  const remove = async (id) => {
    if (!await confirmDialog({ message: 'Şablon silinecek, emin misiniz?', variant: 'danger' })) return;
    try {
      await axios.delete(`${API}/templates/${id}`);
      toast.success('Şablon silindi');
      onChanged();
    } catch (e) {
      toast.error('Silinemedi');
    }
  };

  if (editing) return <TemplateEditor initial={editing} onSave={save} onCancel={() => setEditing(null)} />;

  return (
    <Card>
      <CardHeader className="flex flex-row items-center justify-between">
        <div>
          <CardTitle>{t('cm.pages_MailingPage.sablonlar_cdaec')}</CardTitle>
          <CardDescription>{t('cm.pages_MailingPage.tekrar_tekrar_kullanacaginiz_e_posta_sab')}</CardDescription>
        </div>
        <Button onClick={() => setEditing(empty)}><Plus className="w-4 h-4 mr-1" />{t('cm.pages_MailingPage.yeni_sablon')}</Button>
      </CardHeader>
      <CardContent>
        {templates.length === 0 ? (
          <div className="text-center py-12 text-muted-foreground">
            <FileText className="w-12 h-12 mx-auto mb-3 opacity-40" />
            <p>{t('cm.pages_MailingPage.henuz_sablon_yok_ilk_sablonunuzu_olustur')}</p>
          </div>
        ) : (
          <div className="space-y-2">
            {templates.map(t => (
              <div key={t.id} className="flex items-center justify-between p-3 border rounded hover:bg-slate-50">
                <div className="min-w-0">
                  <div className="font-medium">{t.name}</div>
                  <div className="text-sm text-muted-foreground truncate">{t.subject}</div>
                </div>
                <div className="flex gap-2">
                  <Button variant="outline" size="sm" onClick={() => setEditing(t)}>{t('cm.pages_MailingPage.duzenle')}</Button>
                  <Button variant="outline" size="sm" onClick={() => remove(t.id)}>
                    <Trash2 className="w-4 h-4 text-rose-600" />
                  </Button>
                </div>
              </div>
            ))}
          </div>
        )}
      </CardContent>
    </Card>
  );
}

function TemplateEditor({ initial, onSave, onCancel }) {
  const { t, i18n } = useTranslation();
  const [d, setD] = useState(initial);
  return (
    <Card>
      <CardHeader>
        <CardTitle>{d.id ? 'Şablon Düzenle' : 'Yeni Şablon'}</CardTitle>
      </CardHeader>
      <CardContent className="space-y-4">
        <div>
          <Label>{t('cm.pages_MailingPage.sablon_adi')}</Label>
          <Input value={d.name} onChange={e => setD({ ...d, name: e.target.value })} placeholder={t('cm.pages_MailingPage.orn_hosgeldin_e_postasi')} />
        </div>
        <div>
          <Label>Konu</Label>
          <Input value={d.subject} onChange={e => setD({ ...d, subject: e.target.value })}
            placeholder={t('cm.pages_MailingPage.orn_hotel_rezervasyonunuz_onaylandi')} />
        </div>
        <div>
          <Label>{t('cm.pages_MailingPage.icerik_html_d3ce0')}</Label>
          <Textarea rows={14} value={d.html} onChange={e => setD({ ...d, html: e.target.value })}
            className="font-mono text-xs"
            placeholder="<h2>Merhaba {{name}},</h2><p>...</p>" />
        </div>
        <div className="flex gap-2 justify-end">
          <Button variant="outline" onClick={onCancel}>{t('cm.pages_MailingPage.vazgec')}</Button>
          <Button onClick={() => onSave(d)} disabled={!d.name || !d.subject || !d.html}>{t('cm.pages_MailingPage.kaydet')}</Button>
        </div>
      </CardContent>
    </Card>
  );
}

// ── History Tab ──────────────────────────────────────────────
function HistoryTab({ campaigns, loading }) {
  const { t, i18n } = useTranslation();
  const [stats, setStats] = useState(null);
  useEffect(() => {
    axios.get(`${API}/stats`).then(r => setStats(r.data)).catch((e) => {
      console.warn('[MailingPage] stats fetch failed (non-critical):', e?.response?.status ?? e?.message);
    });
  }, []);
  if (loading) return <div className="text-center py-8 text-muted-foreground">{t('cm.pages_MailingPage.yukleniyor_b597b')}</div>;
  return (
    <div className="space-y-4">
      {stats && (
        <Card>
          <CardHeader className="pb-3">
            <CardTitle className="text-base">{t('cm.pages_MailingPage.performans_son_90_gun')}</CardTitle>
          </CardHeader>
          <CardContent>
            <div className="grid grid-cols-2 md:grid-cols-5 gap-3">
              <StatBox label={t('cm.pages_MailingPage.gonderildi')}  value={stats.sent}      sub="" />
              <StatBox label={t('cm.pages_MailingPage.ulasti')}      value={stats.delivered} sub={`%${stats.delivery_rate}`} color="text-sky-600" />
              <StatBox label={t('cm.pages_MailingPage.acildi')}      value={stats.opened}    sub={`%${stats.open_rate}`}    color="text-emerald-600" />
              <StatBox label={t('cm.pages_MailingPage.tiklandi')}    value={stats.clicked}   sub={`%${stats.click_rate}`}   color="text-indigo-600" />
              <StatBox label={t('cm.pages_MailingPage.geri_dondu')}  value={stats.bounced}   sub={`%${stats.bounce_rate}`}  color="text-rose-600" />
            </div>
            {stats.sent === 0 && (
              <p className="text-xs text-muted-foreground mt-3">
                {t('cm.pages_MailingPage.henuz_takip_verisi_yok_acilma_tiklanma_i')}
                <code className="ml-1 px-1 bg-muted rounded text-[11px]">/api/mailing/webhook/resend</code>
              </p>
            )}
          </CardContent>
        </Card>
      )}
    <Card>
      <CardHeader>
        <CardTitle>{t('cm.pages_MailingPage.gonderim_gecmisi')}</CardTitle>
      </CardHeader>
      <CardContent>
        {campaigns.length === 0 ? (
          <div className="text-center py-12 text-muted-foreground">{t('cm.pages_MailingPage.henuz_kampanya_gonderimi_yok')}</div>
        ) : (
          <div className="space-y-2">
            {campaigns.map(c => (
              <div key={c.id} className="flex items-center justify-between p-3 border rounded">
                <div>
                  <div className="font-medium">{c.name} {c.is_test && <Badge variant="outline" className="ml-2">Test</Badge>}</div>
                  <div className="text-xs text-muted-foreground">
                    {new Date(c.created_at).toLocaleString(i18n.language)} • {c.subject}
                  </div>
                </div>
                <div className="text-right">
                  <div className="text-sm font-medium text-emerald-700">{c.sent_count} {t('cm.pages_MailingPage.gonderildi_e2364')}</div>
                  {c.failed_count > 0 && <div className="text-xs text-rose-600">{c.failed_count} {t('cm.pages_MailingPage.hatali')}</div>}
                </div>
              </div>
            ))}
          </div>
        )}
      </CardContent>
    </Card>
    </div>
  );
}

function StatBox({ label, value, sub, color = "text-foreground" }) {
  return (
    <div className="border rounded-lg p-3">
      <div className="text-xs text-muted-foreground">{label}</div>
      <div className={`text-2xl font-bold mt-1 ${color}`}>{value ?? 0}</div>
      {sub && <div className="text-xs text-muted-foreground mt-0.5">{sub}</div>}
    </div>
  );
}

// ── Credits Tab ──────────────────────────────────────────────
function CreditsTab({ credits }) {
  const { t, i18n } = useTranslation();
  const navigate = useNavigate();
  if (!credits) return null;

  return (
    <div className="space-y-6">
      <div className="grid md:grid-cols-3 gap-4">
        <KpiCard
          icon={Wallet}
          label="Kalan Kredi"
          value={(credits.balance ?? 0).toLocaleString(i18n.language)}
          sub="Hesabınızda kullanılabilir"
          intent="info"
        />
        <KpiCard
          icon={Send}
          label={t('cm.pages_MailingPage.toplam_gonderilen')}
          value={(credits.lifetime_used ?? 0).toLocaleString(i18n.language)}
          sub="Hesabın açıldığı günden bu yana"
          intent="default"
        />
        <KpiCard
          icon={Gift}
          label="Hediye Kredi"
          value={(credits.free_granted ?? 0).toLocaleString(i18n.language)}
          sub="Karşılama paketi"
          intent="success"
        />
      </div>

      <Card>
        <CardContent className="pt-6">
          <div className="flex items-start gap-4">
            <div className="w-10 h-10 rounded-lg bg-indigo-50 flex items-center justify-center flex-shrink-0">
              <Wallet className="w-5 h-5 text-indigo-600" />
            </div>
            <div className="flex-1">
              <h3 className="text-lg font-semibold mb-1">{t('cm.pages_MailingPage.kredi_yuklemek_ister_misiniz')}</h3>
              <p className="text-sm text-muted-foreground mb-4">
                {t('cm.pages_MailingPage.mailing_kredi_paketleri_artik')} <strong>{t('cm.pages_MailingPage.modul_pazari')}</strong> {t('cm.pages_MailingPage.uzerinden_satiliyor_tek_vitrinden_tum_mo')}
              </p>
              <Button onClick={() => navigate('/app/module-store')}>
                {t('cm.pages_MailingPage.modul_pazari_na_git')}
              </Button>
            </div>
          </div>
        </CardContent>
      </Card>
    </div>
  );
}
