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
import { Mail, Users, FileText, Send, Trash2, Plus, Sparkles, AlertCircle, Zap } from 'lucide-react';
import { useNavigate } from 'react-router-dom';

import { confirmDialog } from '@/lib/dialogs';
const API = '/mailing';

export default function MailingPage({ user, tenant, onLogout }) {
  const [credits, setCredits] = useState(null);
  const [templates, setTemplates] = useState([]);
  const [recipients, setRecipients] = useState([]);
  const [campaigns, setCampaigns] = useState([]);
  const [automations, setAutomations] = useState([]);
  const [loading, setLoading] = useState(true);

  const refresh = useCallback(async () => {
    setLoading(true);
    try {
      const [c, t, r, cp, au] = await Promise.all([
        axios.get(`${API}/credits`),
        axios.get(`${API}/templates`),
        axios.get(`${API}/recipients`),
        axios.get(`${API}/campaigns`),
        axios.get(`${API}/automations`),
      ]);
      setCredits(c.data);
      setTemplates(t.data || []);
      setRecipients(r.data || []);
      setCampaigns(cp.data || []);
      setAutomations(au.data?.automations || []);
    } catch (e) {
      toast.error('Mailing verileri yüklenemedi');
    } finally {
      setLoading(false);
    }
  }, []);

  useEffect(() => { refresh(); }, [refresh]);

  return (
    <>
    <div className="container mx-auto p-6 max-w-7xl space-y-6">
      <div className="flex items-center justify-between">
        <div>
          <h1 className="text-3xl font-bold flex items-center gap-2">
            <Mail className="w-7 h-7 text-indigo-600" />
            E-posta Pazarlama
          </h1>
          <p className="text-muted-foreground mt-1">
            Misafirlerinize toplu e-posta gönderin, şablonları yönetin
          </p>
        </div>
        <CreditsBadge credits={credits} />
      </div>

      <Tabs defaultValue="campaign" className="space-y-4">
        <TabsList className="grid w-full grid-cols-5">
          <TabsTrigger value="campaign"><Send className="w-4 h-4 mr-1.5" />Kampanya</TabsTrigger>
          <TabsTrigger value="automations"><Zap className="w-4 h-4 mr-1.5" />Otomasyon</TabsTrigger>
          <TabsTrigger value="templates"><FileText className="w-4 h-4 mr-1.5" />Şablonlar</TabsTrigger>
          <TabsTrigger value="history"><Sparkles className="w-4 h-4 mr-1.5" />Geçmiş</TabsTrigger>
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
    </>
  );
}

function CreditsBadge({ credits }) {
  if (!credits) return null;
  const low = credits.balance < 50;
  return (
    <div className={`px-4 py-2 rounded-lg border ${low ? 'bg-amber-50 border-amber-300' : 'bg-indigo-50 border-indigo-200'}`}>
      <div className="text-xs text-muted-foreground">Kalan kredi</div>
      <div className={`text-2xl font-bold ${low ? 'text-amber-700' : 'text-indigo-700'}`}>
        {credits.balance.toLocaleString('tr-TR')}
      </div>
    </div>
  );
}

// ── Campaign Tab ──────────────────────────────────────────────
function CampaignTab({ templates, recipients, credits, onSent }) {
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

  const toggleAll = () => {
    if (selected.size === filtered.length) setSelected(new Set());
    else setSelected(new Set(filtered.map(r => r.id)));
  };

  const filtered = recipients.filter(r =>
    !search || r.name.toLowerCase().includes(search.toLowerCase()) || r.email.toLowerCase().includes(search.toLowerCase())
  );

  const sendTest = async () => {
    if (!testEmail) { toast.error('Test e-posta adresi girin'); return; }
    if (!subject || !html) { toast.error('Konu ve içerik gerekli'); return; }
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
    if (credits && selected.size > credits.balance) {
      toast.error(`Yetersiz kredi: ${selected.size} gerekli, ${credits.balance} mevcut`);
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

  return (
    <div className="grid lg:grid-cols-2 gap-6">
      <Card>
        <CardHeader>
          <CardTitle>1. İçerik</CardTitle>
          <CardDescription>Şablon seçin veya yeni içerik yazın</CardDescription>
        </CardHeader>
        <CardContent className="space-y-4">
          <div>
            <Label>Kampanya adı</Label>
            <Input value={name} onChange={e => setName(e.target.value)} placeholder="Örn: Mart kampanyası" />
          </div>
          <div>
            <Label>Şablon (opsiyonel)</Label>
            <select className="w-full border rounded px-3 py-2 text-sm"
              value={templateId} onChange={e => setTemplateId(e.target.value)}>
              <option value="">— Şablonsuz —</option>
              {templates.map(t => <option key={t.id} value={t.id}>{t.name}</option>)}
            </select>
          </div>
          <div>
            <Label>Konu</Label>
            <Input value={subject} onChange={e => setSubject(e.target.value)} placeholder="E-posta konusu" />
          </div>
          <div>
            <Label>İçerik (HTML)</Label>
            <Textarea rows={10} value={html} onChange={e => setHtml(e.target.value)}
              placeholder="<h2>Merhaba {{name}},</h2><p>...</p>"
              className="font-mono text-xs" />
            <p className="text-xs text-muted-foreground mt-1">
              Değişkenler: <code>{'{{name}}'}</code> = misafir adı, <code>{'{{hotel}}'}</code> = otel adı
            </p>
          </div>
          <div className="border-t pt-3">
            <Label className="text-xs">Test gönderimi (1 kredi)</Label>
            <div className="flex gap-2 mt-1">
              <Input type="email" value={testEmail} onChange={e => setTestEmail(e.target.value)}
                placeholder="test@adresiniz.com" />
              <Button variant="outline" onClick={sendTest} disabled={sending}>Test Gönder</Button>
            </div>
          </div>
        </CardContent>
      </Card>

      <Card>
        <CardHeader>
          <CardTitle>2. Alıcılar</CardTitle>
          <CardDescription>{recipients.length} misafir e-postası mevcut, {selected.size} seçili</CardDescription>
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
              }}>Bugün Girişliler</Button>
            <Button size="sm" variant="secondary" type="button"
              onClick={async () => {
                try {
                  const r = await axios.get(`${API}/recipients/quick/today_out`);
                  const ids = (r.data.recipients || []).map(x => x.id);
                  setSelected(new Set(ids));
                  toast.success(`Bugün çıkışlı ${ids.length} misafir seçildi`);
                } catch { toast.error('Filtre uygulanamadı'); }
              }}>Bugün Çıkışlılar</Button>
            <Button size="sm" variant="secondary" type="button"
              onClick={async () => {
                try {
                  const r = await axios.get(`${API}/recipients/quick/in_house`);
                  const ids = (r.data.recipients || []).map(x => x.id);
                  setSelected(new Set(ids));
                  toast.success(`Otelde konaklayan ${ids.length} misafir seçildi`);
                } catch { toast.error('Filtre uygulanamadı'); }
              }}>İçeride Konaklayanlar</Button>
          </div>
          <div className="flex gap-2 mb-3">
            <Input placeholder="İsim veya e-posta ara…" value={search} onChange={e => setSearch(e.target.value)} />
            <Button variant="outline" onClick={toggleAll}>
              {selected.size === filtered.length && filtered.length > 0 ? 'Tümünü Kaldır' : 'Tümünü Seç'}
            </Button>
          </div>
          <div className="border rounded max-h-96 overflow-y-auto divide-y">
            {filtered.length === 0 && (
              <div className="p-8 text-center text-sm text-muted-foreground">
                <Users className="w-8 h-8 mx-auto mb-2 opacity-40" />
                E-postalı misafir bulunamadı
              </div>
            )}
            {filtered.map(r => (
              <label key={r.id} className="flex items-center gap-3 p-2 hover:bg-gray-50 cursor-pointer">
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
          <Button className="w-full mt-4 bg-indigo-600 hover:bg-indigo-700"
            onClick={sendCampaign} disabled={sending || selected.size === 0}>
            <Send className="w-4 h-4 mr-2" />
            {sending ? 'Gönderiliyor…' : `${selected.size} alıcıya gönder (${selected.size} kredi)`}
          </Button>
        </CardContent>
      </Card>
    </div>
  );
}

// ── Automations Tab ──────────────────────────────────────────
function AutomationsTab({ automations, templates, onChanged }) {
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
      <Card className="bg-blue-50 border-blue-200">
        <CardContent className="pt-4">
          <p className="text-sm text-blue-900">
            <strong>Nasıl çalışır?</strong> Aşağıdan bir tetikleyici seçip şablon atayın.
            Sistem her 10 dakikada bir tarar ve uygun rezervasyonlara otomatik olarak e-posta gönderir.
            Aynı misafire aynı tetikleyici için sadece <strong>bir kez</strong> mail gönderilir.
            Kredi yetersizse otomasyon duraklar.
          </p>
        </CardContent>
      </Card>
      {automations.length === 0 && (
        <div className="text-center py-12 text-muted-foreground">Yükleniyor…</div>
      )}
      {automations.map(a => (
        <Card key={a.trigger_type}>
          <CardContent className="pt-6">
            <div className="flex items-start justify-between gap-4">
              <div className="flex-1 min-w-0">
                <div className="flex items-center gap-2 mb-1">
                  <Zap className={`w-5 h-5 ${a.enabled ? 'text-green-600' : 'text-gray-400'}`} />
                  <h3 className="font-semibold text-lg">{a.label}</h3>
                  {a.enabled && <Badge className="bg-green-100 text-green-800 hover:bg-green-100">Aktif</Badge>}
                </div>
                <p className="text-sm text-muted-foreground mb-3">{a.description}</p>
                <div className="grid sm:grid-cols-2 gap-3">
                  <div>
                    <Label className="text-xs">Şablon</Label>
                    <select className="w-full border rounded px-3 py-2 text-sm mt-1"
                      value={a.template_id || ''}
                      onChange={e => save(a, { template_id: e.target.value || null })}>
                      <option value="">— Şablon seçin —</option>
                      {templates.map(t => <option key={t.id} value={t.id}>{t.name}</option>)}
                    </select>
                  </div>
                  <div>
                    <Label className="text-xs">
                      Gün farkı {a.trigger_type === 'checkin_reminder' ? '(check-in öncesi)' :
                                a.trigger_type === 'checkout_thanks' ? '(check-out sonrası)' : '(0 = anında)'}
                    </Label>
                    <Input type="number" className="mt-1" value={a.offset_days ?? 0}
                      onChange={e => save(a, { offset_days: parseInt(e.target.value || '0', 10) })} />
                  </div>
                </div>
                {a.last_run_at && (
                  <p className="text-xs text-muted-foreground mt-2">
                    Son çalışma: {new Date(a.last_run_at).toLocaleString('tr-TR')} • {a.last_sent_count} gönderim
                  </p>
                )}
              </div>
              <Switch
                checked={a.enabled}
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
          <CardTitle>Şablonlar</CardTitle>
          <CardDescription>Tekrar tekrar kullanacağınız e-posta şablonları</CardDescription>
        </div>
        <Button onClick={() => setEditing(empty)}><Plus className="w-4 h-4 mr-1" />Yeni Şablon</Button>
      </CardHeader>
      <CardContent>
        {templates.length === 0 ? (
          <div className="text-center py-12 text-muted-foreground">
            <FileText className="w-12 h-12 mx-auto mb-3 opacity-40" />
            <p>Henüz şablon yok. İlk şablonunuzu oluşturun.</p>
          </div>
        ) : (
          <div className="space-y-2">
            {templates.map(t => (
              <div key={t.id} className="flex items-center justify-between p-3 border rounded hover:bg-gray-50">
                <div className="min-w-0">
                  <div className="font-medium">{t.name}</div>
                  <div className="text-sm text-muted-foreground truncate">{t.subject}</div>
                </div>
                <div className="flex gap-2">
                  <Button variant="outline" size="sm" onClick={() => setEditing(t)}>Düzenle</Button>
                  <Button variant="outline" size="sm" onClick={() => remove(t.id)}>
                    <Trash2 className="w-4 h-4 text-red-600" />
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
  const [d, setD] = useState(initial);
  return (
    <Card>
      <CardHeader>
        <CardTitle>{d.id ? 'Şablon Düzenle' : 'Yeni Şablon'}</CardTitle>
      </CardHeader>
      <CardContent className="space-y-4">
        <div>
          <Label>Şablon adı</Label>
          <Input value={d.name} onChange={e => setD({ ...d, name: e.target.value })} placeholder="Örn: Hoşgeldin e-postası" />
        </div>
        <div>
          <Label>Konu</Label>
          <Input value={d.subject} onChange={e => setD({ ...d, subject: e.target.value })}
            placeholder="Örn: {{hotel}} - Rezervasyonunuz onaylandı" />
        </div>
        <div>
          <Label>İçerik (HTML)</Label>
          <Textarea rows={14} value={d.html} onChange={e => setD({ ...d, html: e.target.value })}
            className="font-mono text-xs"
            placeholder="<h2>Merhaba {{name}},</h2><p>...</p>" />
        </div>
        <div className="flex gap-2 justify-end">
          <Button variant="outline" onClick={onCancel}>Vazgeç</Button>
          <Button onClick={() => onSave(d)} disabled={!d.name || !d.subject || !d.html}>Kaydet</Button>
        </div>
      </CardContent>
    </Card>
  );
}

// ── History Tab ──────────────────────────────────────────────
function HistoryTab({ campaigns, loading }) {
  const [stats, setStats] = useState(null);
  useEffect(() => {
    axios.get(`${API}/stats`).then(r => setStats(r.data)).catch(() => {});
  }, []);
  if (loading) return <div className="text-center py-8 text-muted-foreground">Yükleniyor…</div>;
  return (
    <div className="space-y-4">
      {stats && (
        <Card>
          <CardHeader className="pb-3">
            <CardTitle className="text-base">Performans (Son 90 gün)</CardTitle>
          </CardHeader>
          <CardContent>
            <div className="grid grid-cols-2 md:grid-cols-5 gap-3">
              <StatBox label="Gönderildi"  value={stats.sent}      sub="" />
              <StatBox label="Ulaştı"      value={stats.delivered} sub={`%${stats.delivery_rate}`} color="text-blue-600" />
              <StatBox label="Açıldı"      value={stats.opened}    sub={`%${stats.open_rate}`}    color="text-green-600" />
              <StatBox label="Tıklandı"    value={stats.clicked}   sub={`%${stats.click_rate}`}   color="text-indigo-600" />
              <StatBox label="Geri döndü"  value={stats.bounced}   sub={`%${stats.bounce_rate}`}  color="text-red-600" />
            </div>
            {stats.sent === 0 && (
              <p className="text-xs text-muted-foreground mt-3">
                Henüz takip verisi yok. Açılma/tıklanma izleme için Resend panelinde webhook tanımlayın:
                <code className="ml-1 px-1 bg-muted rounded text-[11px]">/api/mailing/webhook/resend</code>
              </p>
            )}
          </CardContent>
        </Card>
      )}
    <Card>
      <CardHeader>
        <CardTitle>Gönderim Geçmişi</CardTitle>
      </CardHeader>
      <CardContent>
        {campaigns.length === 0 ? (
          <div className="text-center py-12 text-muted-foreground">Henüz kampanya gönderimi yok</div>
        ) : (
          <div className="space-y-2">
            {campaigns.map(c => (
              <div key={c.id} className="flex items-center justify-between p-3 border rounded">
                <div>
                  <div className="font-medium">{c.name} {c.is_test && <Badge variant="outline" className="ml-2">Test</Badge>}</div>
                  <div className="text-xs text-muted-foreground">
                    {new Date(c.created_at).toLocaleString('tr-TR')} • {c.subject}
                  </div>
                </div>
                <div className="text-right">
                  <div className="text-sm font-medium text-green-700">{c.sent_count} gönderildi</div>
                  {c.failed_count > 0 && <div className="text-xs text-red-600">{c.failed_count} hatalı</div>}
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
  const navigate = useNavigate();
  if (!credits) return null;

  return (
    <div className="space-y-6">
      <div className="grid md:grid-cols-3 gap-4">
        <Card>
          <CardContent className="pt-6 text-center">
            <p className="text-sm text-muted-foreground">Kalan Kredi</p>
            <p className="font-bold text-3xl text-indigo-700 mt-1">{credits.balance}</p>
          </CardContent>
        </Card>
        <Card>
          <CardContent className="pt-6 text-center">
            <p className="text-sm text-muted-foreground">Toplam Gönderilen</p>
            <p className="font-bold text-3xl text-gray-700 mt-1">{credits.lifetime_used}</p>
          </CardContent>
        </Card>
        <Card>
          <CardContent className="pt-6 text-center">
            <p className="text-sm text-muted-foreground">Hediye Kredi</p>
            <p className="font-bold text-3xl text-green-700 mt-1">{credits.free_granted}</p>
          </CardContent>
        </Card>
      </div>

      <Card className="border-indigo-200 bg-gradient-to-br from-indigo-50 to-white">
        <CardContent className="pt-6">
          <div className="flex items-start gap-4">
            <div className="text-4xl"></div>
            <div className="flex-1">
              <h3 className="text-lg font-semibold mb-1">Kredi yüklemek ister misiniz?</h3>
              <p className="text-sm text-muted-foreground mb-4">
                Mailing kredi paketleri artık <strong>Modül Pazarı</strong> üzerinden satılıyor.
                Tek vitrinden tüm modül, entegrasyon ve kredi paketlerinize ulaşabilirsiniz.
                Mevcut krediniz ve geçmişiniz aynen korunuyor.
              </p>
              <Button onClick={() => navigate('/app/module-store')} className="bg-indigo-600 hover:bg-indigo-700">
                Modül Pazarı'na Git →
              </Button>
            </div>
          </div>
        </CardContent>
      </Card>
    </div>
  );
}
