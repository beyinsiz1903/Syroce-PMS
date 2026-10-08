import React, { useCallback, useEffect, useMemo, useState } from 'react';
import axios from 'axios';
import { AlertTriangle, BarChart3, CheckCircle2, ClipboardCheck, Plus, RefreshCw, ShieldCheck } from 'lucide-react';
import { toast } from 'sonner';
import { Button } from '@/components/ui/button';
import { Card, CardContent, CardHeader, CardTitle } from '@/components/ui/card';
import { Dialog, DialogContent, DialogFooter, DialogHeader, DialogTitle } from '@/components/ui/dialog';
import { Input } from '@/components/ui/input';
import { Label } from '@/components/ui/label';
import { Tabs, TabsContent, TabsList, TabsTrigger } from '@/components/ui/tabs';
import EmptyState from '@/components/EmptyState';

const kindLabels = { standard: 'Standart', audit: 'Denetim', finding: 'Uygunsuzluk', capa: 'CAPA' };
const statusLabels = { draft: 'Taslak', open: 'Açık', in_progress: 'İşlemde', pending_verification: 'Doğrulama bekliyor', closed: 'Kapalı', cancelled: 'İptal' };
const nextStatus = { draft: 'open', open: 'in_progress', in_progress: 'pending_verification', pending_verification: 'closed', closed: 'open', cancelled: 'open' };
const emptyForm = { id: '', kind: 'audit', title: '', description: '', department: 'Ön Büro', severity: 'medium', owner_id: '', due_at: '', root_cause: '', corrective_action: '', preventive_action: '', verification_note: '', checklistText: '', checklist: [] };

export default function QualityManagement() {
  const [dashboard, setDashboard] = useState(null);
  const [records, setRecords] = useState([]);
  const [feedback, setFeedback] = useState({ entries: [], summary: {} });
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState('');
  const [filter, setFilter] = useState('all');
  const [dialogOpen, setDialogOpen] = useState(false);
  const [form, setForm] = useState(emptyForm);
  const [saving, setSaving] = useState(false);

  const load = useCallback(async () => {
    setLoading(true);
    setError('');
    const [dashboardResult, recordResult, feedbackResult] = await Promise.allSettled([
      axios.get('/quality/dashboard'),
      axios.get('/quality/records', { params: { limit: 500 } }),
      axios.get('/quality/feedback', { params: { limit: 100 } }),
    ]);
    if (dashboardResult.status === 'fulfilled') setDashboard(dashboardResult.value.data);
    else setError(dashboardResult.reason?.response?.data?.detail || 'Kalite özeti yüklenemedi.');
    setRecords(recordResult.status === 'fulfilled' ? recordResult.value.data?.records || [] : []);
    setFeedback(feedbackResult.status === 'fulfilled' ? feedbackResult.value.data || { entries: [], summary: {} } : { entries: [], summary: {} });
    setLoading(false);
  }, []);

  useEffect(() => { load(); }, [load]);

  const visibleRecords = useMemo(() => filter === 'all' ? records : records.filter((row) => row._kind === `quality_${filter}`), [filter, records]);

  const save = async () => {
    if (!form.title.trim() || !form.department.trim()) {
      toast.error('Başlık ve departman zorunludur.');
      return;
    }
    setSaving(true);
    try {
      const payload = {
        kind: form.kind,
        title: form.title.trim(),
        description: form.description || null,
        department: form.department.trim(),
        severity: form.severity,
        owner_id: form.owner_id || null,
        due_at: form.due_at ? new Date(form.due_at).toISOString() : null,
        root_cause: form.root_cause || null,
        corrective_action: form.corrective_action || null,
        preventive_action: form.preventive_action || null,
        verification_note: form.verification_note || null,
        checklist: form.id ? form.checklist : form.checklistText.split('\n').map((label) => label.trim()).filter(Boolean).map((label) => ({ label, required: true, result: 'pending' })),
        evidence_urls: [],
      };
      if (form.id) await axios.put(`/quality/records/${encodeURIComponent(form.id)}`, payload);
      else await axios.post('/quality/records', payload);
      toast.success(form.id ? 'Kalite kaydı güncellendi.' : 'Kalite kaydı oluşturuldu.');
      setDialogOpen(false);
      setForm(emptyForm);
      await load();
    } catch (err) {
      toast.error(err?.response?.data?.detail || 'Kalite kaydı oluşturulamadı.');
    } finally {
      setSaving(false);
    }
  };

  const edit = (record) => {
    setForm({
      ...emptyForm,
      ...record,
      kind: record._kind?.replace('quality_', '') || 'audit',
      due_at: record.due_at ? new Date(record.due_at).toISOString().slice(0, 16) : '',
      checklist: record.checklist || [],
    });
    setDialogOpen(true);
  };

  const transition = async (record) => {
    const target = nextStatus[record.status || 'open'];
    try {
      await axios.post(`/quality/records/${encodeURIComponent(record.id)}/transition`, { status: target, note: 'Kalite yönetimi ekranından güncellendi.' });
      toast.success(`Durum: ${statusLabels[target]}`);
      await load();
    } catch (err) {
      toast.error(err?.response?.data?.detail || 'Durum güncellenemedi.');
    }
  };

  const summary = dashboard?.summary || {};
  return <main className="min-h-screen bg-slate-50/70 p-4 lg:p-6" data-testid="quality-management">
    <div className="mx-auto max-w-[1500px] space-y-5">
      <header className="flex flex-wrap items-start justify-between gap-3">
        <div><p className="text-xs font-semibold uppercase tracking-[0.18em] text-emerald-700">Sürekli iyileştirme</p><h1 className="mt-1 text-3xl font-black tracking-tight text-slate-950">Kalite Yönetimi</h1><p className="mt-1 max-w-3xl text-sm text-slate-600">Standart, denetim, uygunsuzluk ve düzeltici/önleyici faaliyetleri tek denetim iziyle yönetin.</p></div>
        <div className="flex gap-2"><Button variant="outline" onClick={load} disabled={loading}><RefreshCw className={`mr-2 h-4 w-4 ${loading ? 'animate-spin' : ''}`} />Yenile</Button><Button onClick={() => { setForm(emptyForm); setDialogOpen(true); }}><Plus className="mr-2 h-4 w-4" />Yeni kayıt</Button></div>
      </header>
      {error && <div role="alert" className="rounded-xl border border-red-200 bg-red-50 p-3 text-sm text-red-800">{error}</div>}
      <section className="grid gap-3 sm:grid-cols-2 xl:grid-cols-5" aria-label="Kalite özeti">
        <Metric label="Açık kayıt" value={summary.open || 0} icon={ClipboardCheck} />
        <Metric label="Geciken" value={summary.overdue || 0} icon={AlertTriangle} tone="amber" />
        <Metric label="Kritik" value={summary.critical || 0} icon={ShieldCheck} tone="red" />
        <Metric label="Kapatılan" value={summary.closed || 0} icon={CheckCircle2} tone="emerald" />
        <Metric label="Kapanış oranı" value={`%${summary.closure_rate || 0}`} icon={BarChart3} tone="blue" />
      </section>
      <Tabs defaultValue="register">
        <TabsList className="h-auto w-full justify-start overflow-x-auto p-1"><TabsTrigger value="register">Kalite kayıtları</TabsTrigger><TabsTrigger value="feedback">Misafir geri bildirimi</TabsTrigger><TabsTrigger value="performance">Performans</TabsTrigger></TabsList>
        <TabsContent value="register" className="space-y-3 pt-3">
          <div className="flex flex-wrap gap-2">{['all', ...Object.keys(kindLabels)].map((kind) => <Button key={kind} size="sm" variant={filter === kind ? 'default' : 'outline'} onClick={() => setFilter(kind)}>{kind === 'all' ? 'Tümü' : kindLabels[kind]}</Button>)}</div>
          <RecordTable records={visibleRecords} loading={loading} onTransition={transition} onEdit={edit} />
        </TabsContent>
        <TabsContent value="feedback" className="pt-3"><FeedbackPanel feedback={feedback} /></TabsContent>
        <TabsContent value="performance" className="pt-3"><PerformancePanel summary={summary} /></TabsContent>
      </Tabs>
    </div>
    <Dialog open={dialogOpen} onOpenChange={setDialogOpen}><DialogContent className="max-h-[90vh] max-w-2xl overflow-y-auto"><DialogHeader><DialogTitle>Yeni kalite kaydı</DialogTitle></DialogHeader><div className="grid gap-4 sm:grid-cols-2">
      <Field label="Kayıt türü"><select disabled={Boolean(form.id)} className="h-10 w-full rounded-md border bg-white px-3 text-sm disabled:opacity-60" value={form.kind} onChange={(e) => setForm({ ...form, kind: e.target.value })}>{Object.entries(kindLabels).map(([value, label]) => <option key={value} value={value}>{label}</option>)}</select></Field>
      <Field label="Önem"><select className="h-10 w-full rounded-md border bg-white px-3 text-sm" value={form.severity} onChange={(e) => setForm({ ...form, severity: e.target.value })}><option value="low">Düşük</option><option value="medium">Orta</option><option value="high">Yüksek</option><option value="critical">Kritik</option></select></Field>
      <Field label="Başlık" wide><Input value={form.title} onChange={(e) => setForm({ ...form, title: e.target.value })} /></Field>
      <Field label="Departman"><Input value={form.department} onChange={(e) => setForm({ ...form, department: e.target.value })} /></Field>
      <Field label="Sorumlu kullanıcı kimliği"><Input value={form.owner_id} onChange={(e) => setForm({ ...form, owner_id: e.target.value })} /></Field>
      <Field label="Hedef tarih"><Input type="datetime-local" value={form.due_at} onChange={(e) => setForm({ ...form, due_at: e.target.value })} /></Field>
      <Field label="Açıklama" wide><textarea className="min-h-20 w-full rounded-md border p-3 text-sm" value={form.description} onChange={(e) => setForm({ ...form, description: e.target.value })} /></Field>
      {(form.kind === 'capa' || form.kind === 'finding') && <><Field label="Kök neden" wide><textarea className="min-h-20 w-full rounded-md border p-3 text-sm" value={form.root_cause} onChange={(e) => setForm({ ...form, root_cause: e.target.value })} /></Field><Field label="Düzeltici faaliyet"><textarea className="min-h-20 w-full rounded-md border p-3 text-sm" value={form.corrective_action} onChange={(e) => setForm({ ...form, corrective_action: e.target.value })} /></Field><Field label="Önleyici faaliyet"><textarea className="min-h-20 w-full rounded-md border p-3 text-sm" value={form.preventive_action} onChange={(e) => setForm({ ...form, preventive_action: e.target.value })} /></Field></>}
      {form.id ? <Field label="Kontrol sonuçları" wide><div className="space-y-2">{form.checklist.length ? form.checklist.map((item, index) => <div key={`${item.label}-${index}`} className="grid items-center gap-2 rounded-lg border p-2 sm:grid-cols-[1fr_170px]"><span className="text-sm">{item.label}{item.required ? ' *' : ''}</span><select aria-label={`${item.label} sonucu`} className="h-9 rounded-md border bg-white px-2 text-sm" value={item.result} onChange={(e) => setForm({ ...form, checklist: form.checklist.map((row, rowIndex) => rowIndex === index ? { ...row, result: e.target.value } : row) })}><option value="pending">Bekliyor</option><option value="pass">Uygun</option><option value="fail">Uygunsuz</option><option value="not_applicable">Uygulanamaz</option></select></div>) : <p className="text-sm text-slate-500">Kontrol maddesi yok.</p>}</div></Field> : <Field label="Kontrol listesi (her satır bir madde)" wide><textarea className="min-h-28 w-full rounded-md border p-3 text-sm" value={form.checklistText} onChange={(e) => setForm({ ...form, checklistText: e.target.value })} placeholder="Oda temizliği doğrulandı&#10;Ekipman çalışır durumda" /></Field>}
      {form.kind === 'capa' && <Field label="Doğrulama notu" wide><textarea className="min-h-20 w-full rounded-md border p-3 text-sm" value={form.verification_note || ''} onChange={(e) => setForm({ ...form, verification_note: e.target.value })} /></Field>}
    </div><DialogFooter><Button variant="outline" onClick={() => setDialogOpen(false)} disabled={saving}>Vazgeç</Button><Button onClick={save} disabled={saving}>{saving ? 'Kaydediliyor…' : form.id ? 'Değişiklikleri kaydet' : 'Kaydet'}</Button></DialogFooter></DialogContent></Dialog>
  </main>;
}

const Field = ({ label, wide, children }) => <div className={wide ? 'sm:col-span-2' : ''}><Label className="mb-1.5 block">{label}</Label>{children}</div>;
const metricTone = {
  slate: 'bg-slate-100 text-slate-700',
  amber: 'bg-amber-50 text-amber-700',
  red: 'bg-red-50 text-red-700',
  emerald: 'bg-emerald-50 text-emerald-700',
  blue: 'bg-blue-50 text-blue-700',
};
const Metric = ({ label, value, icon: Icon, tone = 'slate' }) => <Card><CardContent className="flex items-center gap-3 p-4"><span className={`rounded-xl p-2 ${metricTone[tone] || metricTone.slate}`}><Icon className="h-5 w-5" /></span><div><p className="text-2xl font-bold text-slate-950">{value}</p><p className="text-xs text-slate-500">{label}</p></div></CardContent></Card>;

function RecordTable({ records, loading, onTransition, onEdit }) {
  if (!loading && !records.length) return <EmptyState title="Kalite kaydı bulunamadı" description="İlk standart, denetim veya CAPA kaydınızı oluşturun." />;
  return <Card><CardContent className="overflow-x-auto p-0"><table className="w-full min-w-[850px] text-left text-sm"><thead className="border-b bg-slate-50 text-xs uppercase text-slate-500"><tr><th className="p-3">Kayıt</th><th>Departman</th><th>Önem</th><th>Durum</th><th>Hedef</th><th className="pr-3 text-right">İşlem</th></tr></thead><tbody>{records.map((row) => <tr key={row.id} className="border-b last:border-0"><td className="p-3"><p className="font-medium text-slate-900">{row.title}</p><p className="text-xs text-slate-500">{kindLabels[row._kind?.replace('quality_', '')] || row._kind}</p></td><td>{row.department}</td><td><Severity value={row.severity} /></td><td>{statusLabels[row.status] || row.status}</td><td>{row.due_at ? new Date(row.due_at).toLocaleString('tr-TR') : '—'}</td><td className="pr-3 text-right"><div className="flex justify-end gap-2"><Button size="sm" variant="ghost" onClick={() => onEdit(row)}>Düzenle</Button><Button size="sm" variant="outline" onClick={() => onTransition(row)}>{row.status === 'pending_verification' ? 'Doğrula ve kapat' : row.status === 'closed' ? 'Yeniden aç' : 'İlerlet'}</Button></div></td></tr>)}</tbody></table></CardContent></Card>;
}
const Severity = ({ value }) => <span className={`rounded-full px-2 py-1 text-xs font-medium ${value === 'critical' ? 'bg-red-50 text-red-700' : value === 'high' ? 'bg-rose-50 text-rose-700' : value === 'low' ? 'bg-slate-100 text-slate-600' : 'bg-amber-50 text-amber-700'}`}>{({ low: 'Düşük', medium: 'Orta', high: 'Yüksek', critical: 'Kritik' })[value] || value}</span>;

function FeedbackPanel({ feedback }) {
  const summary = feedback.summary || {};
  return <div className="space-y-3"><div className="grid gap-3 sm:grid-cols-3"><Metric label="Toplam geri bildirim" value={summary.total || 0} icon={ClipboardCheck} /><Metric label="Ortalama puan" value={summary.average_rating ?? '—'} icon={BarChart3} tone="blue" /><Metric label="Çözüm bekleyen" value={summary.unresolved || 0} icon={AlertTriangle} tone="amber" /></div><Card><CardHeader><CardTitle>Son geri bildirimler</CardTitle></CardHeader><CardContent className="space-y-2">{feedback.entries?.length ? feedback.entries.map((entry, index) => <div key={entry.id || entry.dedup_key || index} className="rounded-lg border p-3 text-sm"><div className="flex justify-between gap-3"><span className="font-medium">{entry.category || entry.source || 'Misafir geri bildirimi'}</span><span>{entry.rating ?? entry.nps_score ?? '—'}</span></div><p className="mt-1 text-slate-600">{entry.comment || entry.feedback || 'Yorum bırakılmadı.'}</p></div>) : <p className="text-sm text-slate-500">Geri bildirim bulunamadı.</p>}</CardContent></Card></div>;
}

function PerformancePanel({ summary }) {
  const departments = Object.entries(summary.by_department || {}).sort((a, b) => b[1] - a[1]);
  return <div className="grid gap-4 lg:grid-cols-2"><Card><CardHeader><CardTitle>Departmanlara göre kayıtlar</CardTitle></CardHeader><CardContent className="space-y-3">{departments.length ? departments.map(([department, count]) => <div key={department}><div className="mb-1 flex justify-between text-sm"><span>{department}</span><strong>{count}</strong></div><div className="h-2 rounded bg-slate-100"><div className="h-2 rounded bg-blue-600" style={{ width: `${Math.min(100, count / Math.max(1, summary.total) * 100)}%` }} /></div></div>) : <p className="text-sm text-slate-500">Henüz veri yok.</p>}</CardContent></Card><Card><CardHeader><CardTitle>Kayıt türleri</CardTitle></CardHeader><CardContent className="space-y-2">{Object.entries(summary.by_kind || {}).map(([kind, count]) => <div key={kind} className="flex justify-between rounded-lg border p-3 text-sm"><span>{kindLabels[kind]}</span><strong>{count}</strong></div>)}</CardContent></Card></div>;
}
