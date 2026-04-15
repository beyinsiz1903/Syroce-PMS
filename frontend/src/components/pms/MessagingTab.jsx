import { useState, useEffect, useCallback } from 'react';
import axios from 'axios';
import { toast } from 'sonner';
import { Card, CardContent, CardDescription, CardHeader, CardTitle } from '@/components/ui/card';
import { Button } from '@/components/ui/button';
import { Input } from '@/components/ui/input';
import { Label } from '@/components/ui/label';
import { Badge } from '@/components/ui/badge';
import { Textarea } from '@/components/ui/textarea';
import { Select, SelectContent, SelectItem, SelectTrigger, SelectValue } from '@/components/ui/select';
import { Tabs, TabsContent, TabsList, TabsTrigger } from '@/components/ui/tabs';
import { Dialog, DialogContent, DialogHeader, DialogTitle } from '@/components/ui/dialog';
import {
  Send, Mail, MessageSquare, RefreshCw, FileText, Zap,
  Clock, ChevronRight, Trash2,
  Plus, Play, Power, PowerOff, Search
} from 'lucide-react';

const CHANNEL_INFO = {
  email: { label: 'Email', icon: Mail, color: 'text-blue-600' },
  whatsapp: { label: 'WhatsApp', icon: MessageSquare, color: 'text-emerald-600' },
};

const STATUS_BADGE = {
  sent: { label: 'Gonderildi', variant: 'default' },
  delivered: { label: 'Teslim', variant: 'default' },
  failed: { label: 'Basarisiz', variant: 'destructive' },
  queued: { label: 'Kuyrukta', variant: 'secondary' },
  pending: { label: 'Bekliyor', variant: 'outline' },
};

const TRIGGER_LABELS = {
  booking_confirmed: 'Rezervasyon Onaylandi',
  pre_arrival: 'Check-in Oncesi',
  checked_in: 'Check-in Yapildi',
  checked_out: 'Check-out Yapildi',
  booking_cancelled: 'Rezervasyon İptal',
};

const MessagingTab = ({ guests = [] }) => {
  const [activeTab, setActiveTab] = useState('send');
  const [templates, setTemplates] = useState([]);
  const [deliveryLogs, setDeliveryLogs] = useState([]);
  const [automationRules, setAutomationRules] = useState([]);
  const [metrics, setMetrics] = useState(null);
  const [loading, setLoading] = useState(false);
  const [sending, setSending] = useState(false);
  const [seeding, setSeeding] = useState(false);
  const [guestSearch, setGuestSearch] = useState('');
  const [selectedTemplate, setSelectedTemplate] = useState(null);
  const [showTemplateDialog, setShowTemplateDialog] = useState(false);

  const [message, setMessage] = useState({
    channel: 'email',
    recipient: '',
    subject: '',
    body: '',
    template_id: null,
  });

  const loadTemplates = useCallback(async () => {
    try {
      const res = await axios.get('/messaging-center/templates');
      setTemplates(res.data.templates || []);
    } catch {
      toast.error('Şablonlar yüklenemedi');
    }
  }, []);

  const loadDeliveryLogs = useCallback(async () => {
    try {
      const res = await axios.get('/messaging-center/delivery-logs?limit=50');
      setDeliveryLogs(res.data.logs || []);
    } catch {
      toast.error('Gonderim geçmişi yüklenemedi');
    }
  }, []);

  const loadAutomationRules = useCallback(async () => {
    try {
      const res = await axios.get('/messaging-center/automation/rules');
      setAutomationRules(res.data.rules || []);
    } catch {
      toast.error('Otomasyon kurallari yüklenemedi');
    }
  }, []);

  const loadMetrics = useCallback(async () => {
    try {
      const res = await axios.get('/messaging-center/metrics?days=30');
      setMetrics(res.data);
    } catch { /* silent */ }
  }, []);

  const loadAll = useCallback(async () => {
    setLoading(true);
    await Promise.all([loadTemplates(), loadDeliveryLogs(), loadAutomationRules(), loadMetrics()]);
    setLoading(false);
  }, [loadTemplates, loadDeliveryLogs, loadAutomationRules, loadMetrics]);

  useEffect(() => {
    loadAll();
  }, [loadAll]);

  const seedDemo = async () => {
    setSeeding(true);
    try {
      const res = await axios.post('/messaging-center/seed-demo');
      const d = res.data;
      toast.success(`Demo veri oluşturuldu: ${d.templates} sablon, ${d.automation_rules} kural`);
      loadAll();
    } catch {
      toast.error('Demo veri oluşturulamadı');
    }
    setSeeding(false);
  };

  const sendMsg = async () => {
    if (!message.recipient || !message.body) {
      toast.error('Alici ve mesaj alanlari zorunludur');
      return;
    }
    setSending(true);
    try {
      const res = await axios.post('/messaging-center/send', message);
      if (res.data?.success === false) {
        toast.error(res.data.error || 'Mesaj gonderilemedi');
      } else {
        toast.success(`${CHANNEL_INFO[message.channel]?.label || message.channel} mesaji gonderildi`);
        setMessage({ channel: message.channel, recipient: '', subject: '', body: '', template_id: null });
        setSelectedTemplate(null);
        loadDeliveryLogs();
        loadMetrics();
      }
    } catch (err) {
      if (err.response?.status === 503) {
        toast.error(`${message.channel.toUpperCase()} servisi yapilandirilmamis. Ayarlardan API bilgilerini girin.`);
      } else {
        toast.error(err.response?.data?.detail || err.response?.data?.error || 'Mesaj gonderilemedi');
      }
    }
    setSending(false);
  };

  const useTemplate = (tmpl) => {
    setMessage(prev => ({
      ...prev,
      subject: tmpl.subject || prev.subject,
      body: tmpl.body_template || tmpl.body || '',
      template_id: tmpl.id,
      channel: tmpl.channel || prev.channel,
    }));
    setSelectedTemplate(tmpl);
    setShowTemplateDialog(false);
    toast.success(`"${tmpl.name}" sablonu yuklendi`);
  };

  const toggleRule = async (rule) => {
    try {
      await axios.put(`/messaging-center/automation/rules/${rule.id}`, { enabled: !rule.enabled });
      toast.success(rule.enabled ? 'Kural devre dışı bırakıldı' : 'Kural aktif edildi');
      loadAutomationRules();
    } catch {
      toast.error('Kural güncellenemedi');
    }
  };

  const deleteRule = async (ruleId) => {
    try {
      await axios.delete(`/messaging-center/automation/rules/${ruleId}`);
      toast.success('Kural silindi');
      loadAutomationRules();
    } catch {
      toast.error('Kural silinemedi');
    }
  };

  const testRule = async (ruleId) => {
    try {
      await axios.post(`/messaging-center/automation/test/${ruleId}`);
      toast.success('Test tetiklendi');
    } catch (err) {
      toast.error(err.response?.data?.detail || 'Test başarısız');
    }
  };

  const filteredGuests = guests.filter(g => {
    if (!guestSearch) return false;
    const term = guestSearch.toLowerCase();
    return (g.name || '').toLowerCase().includes(term) ||
           (g.email || '').toLowerCase().includes(term) ||
           (g.phone || '').includes(term);
  });

  const emailTemplates = templates.filter(t => t.channel === 'email');
  const whatsappTemplates = templates.filter(t => t.channel === 'whatsapp');

  const totalSent = deliveryLogs.filter(l => ['sent', 'delivered'].includes(l.status)).length;
  const totalFailed = deliveryLogs.filter(l => l.status === 'failed').length;
  const emailCount = deliveryLogs.filter(l => l.channel === 'email').length;
  const waCount = deliveryLogs.filter(l => l.channel === 'whatsapp').length;

  return (
    <div className="space-y-6">
      <div className="flex justify-between items-center">
        <h2 className="text-2xl font-semibold">Mesaj Merkezi</h2>
        <div className="flex gap-2">
          {templates.length === 0 && (
            <Button variant="outline" size="sm" onClick={seedDemo} disabled={seeding}>
              {seeding ? <RefreshCw className="w-4 h-4 mr-2 animate-spin" /> : <Plus className="w-4 h-4 mr-2" />}
              Demo Veri Olustur
            </Button>
          )}
          <Button variant="outline" size="sm" onClick={loadAll} disabled={loading}>
            <RefreshCw className={`w-4 h-4 mr-2 ${loading ? 'animate-spin' : ''}`} /> Yenile
          </Button>
        </div>
      </div>

      <div className="grid grid-cols-2 md:grid-cols-4 gap-4">
        <Card className="border-l-4 border-l-blue-500">
          <CardContent className="pt-4 pb-3">
            <div className="flex items-center gap-2 text-sm text-gray-500 mb-1">
              <Send className="w-4 h-4" /> Toplam Gonderim
            </div>
            <p className="text-2xl font-bold">{deliveryLogs.length}</p>
            <p className="text-xs text-gray-400">{totalSent} basarili, {totalFailed} başarısız</p>
          </CardContent>
        </Card>
        <Card className="border-l-4 border-l-indigo-500">
          <CardContent className="pt-4 pb-3">
            <div className="flex items-center gap-2 text-sm text-gray-500 mb-1">
              <Mail className="w-4 h-4" /> Email
            </div>
            <p className="text-2xl font-bold">{emailCount}</p>
            <p className="text-xs text-gray-400">{emailTemplates.length} sablon</p>
          </CardContent>
        </Card>
        <Card className="border-l-4 border-l-emerald-500">
          <CardContent className="pt-4 pb-3">
            <div className="flex items-center gap-2 text-sm text-gray-500 mb-1">
              <MessageSquare className="w-4 h-4" /> WhatsApp
            </div>
            <p className="text-2xl font-bold">{waCount}</p>
            <p className="text-xs text-gray-400">{whatsappTemplates.length} sablon</p>
          </CardContent>
        </Card>
        <Card className="border-l-4 border-l-amber-500">
          <CardContent className="pt-4 pb-3">
            <div className="flex items-center gap-2 text-sm text-gray-500 mb-1">
              <Zap className="w-4 h-4" /> Otomasyon
            </div>
            <p className="text-2xl font-bold">{automationRules.length}</p>
            <p className="text-xs text-gray-400">{automationRules.filter(r => r.enabled).length} aktif kural</p>
          </CardContent>
        </Card>
      </div>

      <Tabs value={activeTab} onValueChange={setActiveTab}>
        <TabsList>
          <TabsTrigger value="send">Mesaj Gonder</TabsTrigger>
          <TabsTrigger value="templates">Şablonlar ({templates.length})</TabsTrigger>
          <TabsTrigger value="history">Gonderim Geçmişi ({deliveryLogs.length})</TabsTrigger>
          <TabsTrigger value="automation">Otomasyon ({automationRules.length})</TabsTrigger>
        </TabsList>

        <TabsContent value="send" className="space-y-4 mt-4">
          <div className="grid grid-cols-1 lg:grid-cols-3 gap-6">
            <Card className="lg:col-span-2">
              <CardHeader className="pb-3">
                <CardTitle className="text-base">Yeni Mesaj</CardTitle>
                <CardDescription>Email, SMS veya WhatsApp ile misafirlerinize mesaj gonderin</CardDescription>
              </CardHeader>
              <CardContent className="space-y-4">
                <div className="grid grid-cols-1 md:grid-cols-2 gap-4">
                  <div>
                    <Label>Kanal</Label>
                    <Select value={message.channel} onValueChange={v => setMessage(p => ({ ...p, channel: v }))}>
                      <SelectTrigger>
                        <SelectValue />
                      </SelectTrigger>
                      <SelectContent>
                        <SelectItem value="email"><span className="flex items-center gap-2"><Mail className="w-3 h-3" /> Email</span></SelectItem>
                        <SelectItem value="whatsapp"><span className="flex items-center gap-2"><MessageSquare className="w-3 h-3" /> WhatsApp</span></SelectItem>
                      </SelectContent>
                    </Select>
                  </div>
                  <div>
                    <Label>Alici *</Label>
                    <Input
                      placeholder={message.channel === 'email' ? 'misafir@email.com' : '+905321234567'}
                      value={message.recipient}
                      onChange={e => setMessage(p => ({ ...p, recipient: e.target.value }))}
                    />
                  </div>
                </div>

                {message.channel === 'email' && (
                  <div>
                    <Label>Konu</Label>
                    <Input
                      placeholder="Mesaj konusu"
                      value={message.subject}
                      onChange={e => setMessage(p => ({ ...p, subject: e.target.value }))}
                    />
                  </div>
                )}

                <div>
                  <div className="flex justify-between items-center mb-1">
                    <Label>Mesaj *</Label>
                    {selectedTemplate && (
                      <Badge variant="secondary" className="text-xs">
                        Şablon: {selectedTemplate.name}
                      </Badge>
                    )}
                  </div>
                  <Textarea
                    placeholder="Mesajinizi yazin..."
                    value={message.body}
                    onChange={e => setMessage(p => ({ ...p, body: e.target.value }))}
                    rows={5}
                  />
                </div>

                <div className="flex gap-2">
                  <Button onClick={sendMsg} disabled={sending || !message.recipient || !message.body} className="flex-1">
                    {sending ? <RefreshCw className="w-4 h-4 mr-2 animate-spin" /> : <Send className="w-4 h-4 mr-2" />}
                    {CHANNEL_INFO[message.channel]?.label || message.channel} Gonder
                  </Button>
                  <Button variant="outline" onClick={() => setShowTemplateDialog(true)}>
                    <FileText className="w-4 h-4 mr-2" /> Şablon Sec
                  </Button>
                </div>
              </CardContent>
            </Card>

            <Card>
              <CardHeader className="pb-3">
                <CardTitle className="text-base flex items-center gap-2">
                  <Search className="w-4 h-4" /> Misafir Ara
                </CardTitle>
                <CardDescription>Alici bilgisini misafirden seçin</CardDescription>
              </CardHeader>
              <CardContent className="space-y-3">
                <Input
                  placeholder="Ad, email veya telefon..."
                  value={guestSearch}
                  onChange={e => setGuestSearch(e.target.value)}
                  className="text-sm"
                />
                <div className="max-h-[300px] overflow-y-auto space-y-2">
                  {guestSearch && filteredGuests.length === 0 ? (
                    <p className="text-sm text-gray-400 text-center py-4">Misafir bulunamadı</p>
                  ) : (
                    filteredGuests.slice(0, 15).map(g => (
                      <div
                        key={g.id}
                        className="border rounded-lg p-2 cursor-pointer hover:border-blue-400 hover:bg-blue-50/50 transition-all"
                        onClick={() => {
                          const recipient = message.channel === 'email' ? (g.email || '') : (g.phone || '');
                          if (!recipient) {
                            toast.error(`Misafirin ${message.channel === 'email' ? 'email' : 'telefon'} bilgisi yok`);
                            return;
                          }
                          setMessage(p => ({ ...p, recipient }));
                          setGuestSearch('');
                          toast.success(`${g.name} secildi`);
                        }}
                      >
                        <p className="text-sm font-medium">{g.name}</p>
                        <div className="flex gap-3 text-xs text-gray-400">
                          {g.email && <span>{g.email}</span>}
                          {g.phone && <span>{g.phone}</span>}
                        </div>
                      </div>
                    ))
                  )}
                  {!guestSearch && (
                    <p className="text-sm text-gray-400 text-center py-4">Misafir aramak için yazin</p>
                  )}
                </div>
              </CardContent>
            </Card>
          </div>
        </TabsContent>

        <TabsContent value="templates" className="mt-4">
          <div className="grid grid-cols-1 lg:grid-cols-2 gap-6">
            <Card>
              <CardHeader className="pb-3">
                <CardTitle className="text-base flex items-center gap-2">
                  <Mail className="w-4 h-4" /> Email Şablonlari
                </CardTitle>
              </CardHeader>
              <CardContent>
                {emailTemplates.length === 0 ? (
                  <p className="text-sm text-gray-400 text-center py-6">Email sablonu yok</p>
                ) : (
                  <div className="space-y-2">
                    {emailTemplates.map(t => (
                      <div key={t.id} className="border rounded-lg p-3 hover:bg-gray-50 transition-all">
                        <div className="flex justify-between items-start">
                          <div className="min-w-0 flex-1">
                            <p className="font-medium text-sm">{t.name}</p>
                            {t.subject && <p className="text-xs text-gray-500 truncate">Konu: {t.subject}</p>}
                            <p className="text-xs text-gray-400 mt-1">Degiskenler: {(t.variables || []).join(', ') || 'Yok'}</p>
                          </div>
                          <Button size="sm" variant="outline" className="h-7 text-xs shrink-0 ml-2" onClick={() => useTemplate(t)}>
                            Kullan
                          </Button>
                        </div>
                      </div>
                    ))}
                  </div>
                )}
              </CardContent>
            </Card>

            <Card>
              <CardHeader className="pb-3">
                <CardTitle className="text-base flex items-center gap-2">
                  <MessageSquare className="w-4 h-4" /> WhatsApp Şablonlari
                </CardTitle>
              </CardHeader>
              <CardContent>
                {whatsappTemplates.length === 0 ? (
                  <p className="text-sm text-gray-400 text-center py-6">WhatsApp sablonu yok</p>
                ) : (
                  <div className="space-y-2">
                    {whatsappTemplates.map(t => (
                      <div key={t.id} className="border rounded-lg p-3 hover:bg-gray-50 transition-all">
                        <div className="flex justify-between items-start">
                          <div className="min-w-0 flex-1">
                            <p className="font-medium text-sm">{t.name}</p>
                            <p className="text-xs text-gray-500 mt-1 line-clamp-2">{t.body_template?.slice(0, 100)}...</p>
                            <p className="text-xs text-gray-400 mt-1">Degiskenler: {(t.variables || []).join(', ') || 'Yok'}</p>
                          </div>
                          <Button size="sm" variant="outline" className="h-7 text-xs shrink-0 ml-2" onClick={() => useTemplate(t)}>
                            Kullan
                          </Button>
                        </div>
                      </div>
                    ))}
                  </div>
                )}
              </CardContent>
            </Card>
          </div>
        </TabsContent>

        <TabsContent value="history" className="mt-4">
          <Card>
            <CardHeader className="pb-3">
              <CardTitle className="text-base">Gonderim Geçmişi</CardTitle>
              <CardDescription>Son 50 mesaj gonderimi</CardDescription>
            </CardHeader>
            <CardContent>
              {deliveryLogs.length === 0 ? (
                <p className="text-sm text-gray-400 text-center py-8">Henüz gonderim yok</p>
              ) : (
                <div className="max-h-[500px] overflow-y-auto space-y-2">
                  {deliveryLogs.map(log => {
                    const ch = CHANNEL_INFO[log.channel] || { label: log.channel, icon: Send, color: 'text-gray-600' };
                    const ChannelIcon = ch.icon;
                    const st = STATUS_BADGE[log.status] || { label: log.status, variant: 'outline' };
                    return (
                      <div key={log.id} className="flex items-center justify-between border rounded-lg px-4 py-3">
                        <div className="flex items-center gap-3 min-w-0">
                          <ChannelIcon className={`w-4 h-4 shrink-0 ${ch.color}`} />
                          <div className="min-w-0">
                            <p className="text-sm font-medium truncate">{log.recipient}</p>
                            <p className="text-xs text-gray-400">{log.use_case || log.subject || '-'}</p>
                          </div>
                        </div>
                        <div className="flex items-center gap-3 shrink-0">
                          <span className="text-xs text-gray-400">
                            {log.created_at ? new Date(log.created_at).toLocaleDateString('tr-TR', { day: '2-digit', month: '2-digit', hour: '2-digit', minute: '2-digit' }) : '-'}
                          </span>
                          <Badge variant={st.variant} className="text-xs">{st.label}</Badge>
                        </div>
                      </div>
                    );
                  })}
                </div>
              )}
            </CardContent>
          </Card>
        </TabsContent>

        <TabsContent value="automation" className="mt-4">
          <Card>
            <CardHeader className="pb-3">
              <div className="flex justify-between items-center">
                <div>
                  <CardTitle className="text-base flex items-center gap-2">
                    <Zap className="w-4 h-4 text-amber-500" /> Otomasyon Kurallari
                  </CardTitle>
                  <CardDescription>Olay bazli otomatik mesaj gonderim kurallari</CardDescription>
                </div>
              </div>
            </CardHeader>
            <CardContent>
              {automationRules.length === 0 ? (
                <div className="text-center py-8 text-gray-400">
                  <Zap className="w-10 h-10 mx-auto mb-3 opacity-30" />
                  <p className="font-medium">Otomasyon kurali yok</p>
                  <p className="text-sm">Demo veri olusturarak ornek kurallar ekleyebilirsiniz</p>
                </div>
              ) : (
                <div className="space-y-3">
                  {automationRules.map(rule => {
                    const triggerLabel = TRIGGER_LABELS[rule.trigger_event] || rule.trigger_event;
                    const ch = CHANNEL_INFO[rule.channel] || { label: rule.channel, icon: Send };
                    const ChannelIcon = ch.icon;
                    return (
                      <div key={rule.id} className={`border rounded-lg p-4 transition-all ${rule.enabled ? '' : 'opacity-50 bg-gray-50'}`}>
                        <div className="flex justify-between items-start">
                          <div className="flex-1 min-w-0">
                            <div className="flex items-center gap-2 mb-1">
                              <span className="font-medium text-sm">{rule.name}</span>
                              <Badge variant={rule.enabled ? 'default' : 'secondary'} className="text-xs">
                                {rule.enabled ? 'Aktif' : 'Pasif'}
                              </Badge>
                            </div>
                            <div className="flex items-center gap-2 text-xs text-gray-500">
                              <Badge variant="outline" className="text-xs">{triggerLabel}</Badge>
                              <ChevronRight className="w-3 h-3" />
                              <ChannelIcon className={`w-3 h-3 ${ch.color}`} />
                              <span>{ch.label}</span>
                              {rule.delay_minutes > 0 && (
                                <span className="flex items-center gap-1">
                                  <Clock className="w-3 h-3" /> {rule.delay_minutes} dk gecikme
                                </span>
                              )}
                            </div>
                          </div>
                          <div className="flex gap-1 shrink-0">
                            <Button size="sm" variant="ghost" className="h-7 w-7 p-0" onClick={() => testRule(rule.id)} title="Test Et">
                              <Play className="w-3 h-3" />
                            </Button>
                            <Button size="sm" variant="ghost" className="h-7 w-7 p-0" onClick={() => toggleRule(rule)} title={rule.enabled ? 'Devre Disi Birak' : 'Aktif Et'}>
                              {rule.enabled ? <PowerOff className="w-3 h-3" /> : <Power className="w-3 h-3" />}
                            </Button>
                            <Button size="sm" variant="ghost" className="h-7 w-7 p-0 text-red-500 hover:text-red-700" onClick={() => deleteRule(rule.id)} title="Sil">
                              <Trash2 className="w-3 h-3" />
                            </Button>
                          </div>
                        </div>
                      </div>
                    );
                  })}
                </div>
              )}
            </CardContent>
          </Card>
        </TabsContent>
      </Tabs>

      <Dialog open={showTemplateDialog} onOpenChange={setShowTemplateDialog}>
        <DialogContent className="max-w-lg max-h-[80vh] overflow-y-auto">
          <DialogHeader>
            <DialogTitle>Şablon Sec</DialogTitle>
          </DialogHeader>
          <div className="space-y-2">
            {templates.length === 0 ? (
              <p className="text-sm text-gray-400 text-center py-6">Şablon bulunamadı. Demo veri oluşturun.</p>
            ) : (
              templates.map(t => {
                const ch = CHANNEL_INFO[t.channel] || { label: t.channel, icon: Send };
                const ChannelIcon = ch.icon;
                return (
                  <div
                    key={t.id}
                    className="border rounded-lg p-3 cursor-pointer hover:border-blue-400 hover:bg-blue-50/50 transition-all"
                    onClick={() => useTemplate(t)}
                  >
                    <div className="flex items-center gap-2 mb-1">
                      <ChannelIcon className={`w-3 h-3 ${ch.color}`} />
                      <span className="font-medium text-sm">{t.name}</span>
                      <Badge variant="outline" className="text-xs">{ch.label}</Badge>
                    </div>
                    <p className="text-xs text-gray-500 line-clamp-2">{t.body_template?.slice(0, 120)}...</p>
                  </div>
                );
              })
            )}
          </div>
        </DialogContent>
      </Dialog>
    </div>
  );
};

export default MessagingTab;
