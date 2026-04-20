import { useEffect, useState, useCallback } from 'react';
import axios from 'axios';
import { Card, CardContent, CardHeader, CardTitle } from '@/components/ui/card';
import { Button } from '@/components/ui/button';
import { Input } from '@/components/ui/input';
import { Label } from '@/components/ui/label';
import { Badge } from '@/components/ui/badge';
import { Dialog, DialogContent, DialogHeader, DialogTitle, DialogFooter } from '@/components/ui/dialog';
import { Select, SelectContent, SelectItem, SelectTrigger, SelectValue } from '@/components/ui/select';
import { Textarea } from '@/components/ui/textarea';

const STAGES = [
  { key: 'lead',       label: 'Lead',      cls: 'bg-slate-100 text-slate-700' },
  { key: 'qualified',  label: 'Qualified', cls: 'bg-blue-100 text-blue-700' },
  { key: 'proposal',   label: 'Teklif',    cls: 'bg-amber-100 text-amber-700' },
  { key: 'contract',   label: 'Sözleşme',  cls: 'bg-violet-100 text-violet-700' },
  { key: 'won',        label: 'Kazanıldı', cls: 'bg-emerald-100 text-emerald-700' },
  { key: 'lost',       label: 'Kaybedildi',cls: 'bg-rose-100 text-rose-700' },
];
const STAGE_BY_KEY = Object.fromEntries(STAGES.map(s => [s.key, s]));

const blank = {
  title: '', account_id: '', event_type: 'wedding',
  expected_start: '', expected_end: '', pax: 0,
  estimated_value: 0, currency: 'TRY', probability: 50,
  source: '', notes: '',
};

export default function SalesPipelineTab({ accounts = [] }) {
  const [pipeline, setPipeline] = useState(null);
  const [opps, setOpps] = useState([]);
  const [loading, setLoading] = useState(true);
  const [stageFilter, setStageFilter] = useState('all');
  const [showForm, setShowForm] = useState(false);
  const [form, setForm] = useState(blank);
  const [transitionFor, setTransitionFor] = useState(null);
  const [toStage, setToStage] = useState('qualified');
  const [reason, setReason] = useState('');
  const [activityFor, setActivityFor] = useState(null);
  const [activity, setActivity] = useState({ type: 'call', subject: '', body: '', outcome: 'positive' });

  const load = useCallback(async () => {
    setLoading(true);
    try {
      const [p, o] = await Promise.all([
        axios.get('/mice/sales/pipeline'),
        axios.get('/mice/sales/opportunities', {
          params: stageFilter !== 'all' ? { stage: stageFilter } : {},
        }),
      ]);
      setPipeline(p.data);
      setOpps(o.data?.opportunities || []);
    } catch (e) { console.error(e); }
    setLoading(false);
  }, [stageFilter]);

  useEffect(() => { load(); }, [load]);

  const submit = async () => {
    try {
      await axios.post('/mice/sales/opportunities', {
        ...form,
        pax: Number(form.pax) || 0,
        estimated_value: Number(form.estimated_value) || 0,
        probability: Number(form.probability) || 0,
      });
      setShowForm(false); setForm(blank);
      await load();
    } catch (e) { alert('Kayıt başarısız: ' + (e.response?.data?.detail || e.message)); }
  };

  const doTransition = async () => {
    try {
      await axios.post(`/mice/sales/opportunities/${transitionFor.id}/transition`, {
        to_stage: toStage, reason,
      });
      setTransitionFor(null); setReason('');
      await load();
    } catch (e) { alert('Hata: ' + (e.response?.data?.detail || e.message)); }
  };

  const submitActivity = async () => {
    try {
      await axios.post(`/mice/sales/opportunities/${activityFor.id}/activities`, activity);
      setActivityFor(null); setActivity({ type: 'call', subject: '', body: '', outcome: 'positive' });
    } catch (e) { alert('Hata: ' + (e.response?.data?.detail || e.message)); }
  };

  const remove = async (id) => {
    if (!confirm('Fırsatı silmek istiyor musunuz?')) return;
    try { await axios.delete(`/mice/sales/opportunities/${id}`); await load(); }
    catch (e) { alert(e.response?.data?.detail || e.message); }
  };

  const fmtCurrency = (v) => `₺${Number(v || 0).toLocaleString('tr-TR')}`;

  return (
    <div className="space-y-4">
      {/* Pipeline summary cards */}
      {pipeline && (
        <div className="grid grid-cols-2 md:grid-cols-6 gap-3">
          {pipeline.stages.map((s) => {
            const meta = STAGE_BY_KEY[s.stage] || { label: s.stage, cls: 'bg-gray-100' };
            return (
              <Card key={s.stage} className="cursor-pointer"
                    onClick={() => setStageFilter(stageFilter === s.stage ? 'all' : s.stage)}>
                <CardContent className="p-3">
                  <Badge className={meta.cls}>{meta.label}</Badge>
                  <div className="text-2xl font-bold mt-1">{s.count}</div>
                  <div className="text-xs text-gray-500">{fmtCurrency(s.total_value)}</div>
                </CardContent>
              </Card>
            );
          })}
        </div>
      )}

      {pipeline && (
        <div className="grid grid-cols-2 md:grid-cols-4 gap-3">
          <Card><CardContent className="p-3">
            <div className="text-xs text-gray-500">Açık Pipeline</div>
            <div className="text-xl font-bold text-emerald-600">{fmtCurrency(pipeline.open_value)}</div>
          </CardContent></Card>
          <Card><CardContent className="p-3">
            <div className="text-xs text-gray-500">Olasılık-Ağırlıklı</div>
            <div className="text-xl font-bold text-blue-600">{fmtCurrency(pipeline.weighted_open_value)}</div>
          </CardContent></Card>
          <Card><CardContent className="p-3">
            <div className="text-xs text-gray-500">Kazanılan</div>
            <div className="text-xl font-bold text-violet-600">{fmtCurrency(pipeline.won_value)}</div>
          </CardContent></Card>
          <Card><CardContent className="p-3">
            <div className="text-xs text-gray-500">Kazanma Oranı</div>
            <div className="text-xl font-bold">{pipeline.win_rate_pct}%</div>
          </CardContent></Card>
        </div>
      )}

      {/* Opportunities table */}
      <Card>
        <CardHeader className="flex flex-row items-center justify-between">
          <CardTitle className="text-base">
            Fırsatlar {stageFilter !== 'all' && <Badge className="ml-2">{STAGE_BY_KEY[stageFilter]?.label}</Badge>}
          </CardTitle>
          <div className="flex gap-2">
            {stageFilter !== 'all' && (
              <Button variant="outline" size="sm" onClick={() => setStageFilter('all')}>Filtreyi Temizle</Button>
            )}
            <Button size="sm" onClick={() => { setForm(blank); setShowForm(true); }}>+ Yeni Fırsat</Button>
          </div>
        </CardHeader>
        <CardContent className="p-0 overflow-x-auto">
          <table className="w-full text-sm">
            <thead className="bg-slate-50 border-b text-left">
              <tr>
                <th className="p-2">Başlık</th>
                <th className="p-2">Tür</th>
                <th className="p-2">Tarih</th>
                <th className="p-2 text-right">Pax</th>
                <th className="p-2 text-right">Tutar</th>
                <th className="p-2 text-center">%</th>
                <th className="p-2">Aşama</th>
                <th className="p-2 text-right">İşlem</th>
              </tr>
            </thead>
            <tbody>
              {loading && <tr><td colSpan={8} className="p-6 text-center text-gray-500">Yükleniyor...</td></tr>}
              {!loading && opps.length === 0 && (
                <tr><td colSpan={8} className="p-6 text-center text-gray-500">Fırsat yok.</td></tr>
              )}
              {opps.map((o) => {
                const meta = STAGE_BY_KEY[o.stage] || { label: o.stage, cls: 'bg-gray-100' };
                return (
                  <tr key={o.id} className="border-b hover:bg-slate-50">
                    <td className="p-2 font-medium">{o.title}</td>
                    <td className="p-2">{o.event_type || '-'}</td>
                    <td className="p-2 font-mono text-xs">{o.expected_start || '-'}{o.expected_end && ` → ${o.expected_end}`}</td>
                    <td className="p-2 text-right">{o.pax || 0}</td>
                    <td className="p-2 text-right">{fmtCurrency(o.estimated_value)}</td>
                    <td className="p-2 text-center">{o.probability}%</td>
                    <td className="p-2"><Badge className={meta.cls}>{meta.label}</Badge></td>
                    <td className="p-2 text-right whitespace-nowrap">
                      <Button size="sm" variant="outline"
                              onClick={() => { setTransitionFor(o); setToStage(o.stage); }}>
                        Aşama
                      </Button>{' '}
                      <Button size="sm" variant="outline"
                              onClick={() => setActivityFor(o)}>
                        Aktivite
                      </Button>{' '}
                      <Button size="sm" variant="ghost" className="text-rose-600"
                              onClick={() => remove(o.id)}>Sil</Button>
                    </td>
                  </tr>
                );
              })}
            </tbody>
          </table>
        </CardContent>
      </Card>

      {/* Create form */}
      <Dialog open={showForm} onOpenChange={setShowForm}>
        <DialogContent className="max-w-2xl">
          <DialogHeader><DialogTitle>Yeni Satış Fırsatı</DialogTitle></DialogHeader>
          <div className="grid grid-cols-2 gap-3">
            <div className="col-span-2">
              <Label>Başlık</Label>
              <Input value={form.title} onChange={(e) => setForm({ ...form, title: e.target.value })} />
            </div>
            <div>
              <Label>Müşteri Hesabı</Label>
              <Select value={form.account_id || 'none'}
                      onValueChange={(v) => setForm({ ...form, account_id: v === 'none' ? '' : v })}>
                <SelectTrigger><SelectValue placeholder="Seçin..." /></SelectTrigger>
                <SelectContent>
                  <SelectItem value="none">— Yok —</SelectItem>
                  {accounts.map((a) => <SelectItem key={a.id} value={a.id}>{a.name}</SelectItem>)}
                </SelectContent>
              </Select>
            </div>
            <div>
              <Label>Etkinlik Türü</Label>
              <Select value={form.event_type} onValueChange={(v) => setForm({ ...form, event_type: v })}>
                <SelectTrigger><SelectValue /></SelectTrigger>
                <SelectContent>
                  <SelectItem value="wedding">Düğün</SelectItem>
                  <SelectItem value="conference">Konferans</SelectItem>
                  <SelectItem value="corporate">Kurumsal</SelectItem>
                  <SelectItem value="social">Sosyal</SelectItem>
                  <SelectItem value="incentive">Incentive</SelectItem>
                </SelectContent>
              </Select>
            </div>
            <div>
              <Label>Başlangıç</Label>
              <Input type="date" value={form.expected_start}
                     onChange={(e) => setForm({ ...form, expected_start: e.target.value })} />
            </div>
            <div>
              <Label>Bitiş</Label>
              <Input type="date" value={form.expected_end}
                     onChange={(e) => setForm({ ...form, expected_end: e.target.value })} />
            </div>
            <div>
              <Label>Pax</Label>
              <Input type="number" value={form.pax}
                     onChange={(e) => setForm({ ...form, pax: e.target.value })} />
            </div>
            <div>
              <Label>Tahmini Tutar (₺)</Label>
              <Input type="number" value={form.estimated_value}
                     onChange={(e) => setForm({ ...form, estimated_value: e.target.value })} />
            </div>
            <div>
              <Label>Olasılık (%)</Label>
              <Input type="number" min={0} max={100} value={form.probability}
                     onChange={(e) => setForm({ ...form, probability: e.target.value })} />
            </div>
            <div>
              <Label>Kaynak</Label>
              <Input value={form.source} placeholder="referral, website, repeat..."
                     onChange={(e) => setForm({ ...form, source: e.target.value })} />
            </div>
            <div className="col-span-2">
              <Label>Notlar</Label>
              <Textarea value={form.notes}
                        onChange={(e) => setForm({ ...form, notes: e.target.value })} />
            </div>
          </div>
          <DialogFooter>
            <Button variant="outline" onClick={() => setShowForm(false)}>İptal</Button>
            <Button onClick={submit} disabled={!form.title}>Kaydet</Button>
          </DialogFooter>
        </DialogContent>
      </Dialog>

      {/* Stage transition */}
      <Dialog open={!!transitionFor} onOpenChange={(o) => !o && setTransitionFor(null)}>
        <DialogContent>
          <DialogHeader><DialogTitle>Aşama Değiştir: {transitionFor?.title}</DialogTitle></DialogHeader>
          <div className="space-y-3">
            <div>
              <Label>Yeni Aşama</Label>
              <Select value={toStage} onValueChange={setToStage}>
                <SelectTrigger><SelectValue /></SelectTrigger>
                <SelectContent>
                  {STAGES.map((s) => <SelectItem key={s.key} value={s.key}>{s.label}</SelectItem>)}
                </SelectContent>
              </Select>
            </div>
            <div>
              <Label>Sebep / Not</Label>
              <Textarea value={reason} onChange={(e) => setReason(e.target.value)} />
            </div>
          </div>
          <DialogFooter>
            <Button variant="outline" onClick={() => setTransitionFor(null)}>İptal</Button>
            <Button onClick={doTransition}>Uygula</Button>
          </DialogFooter>
        </DialogContent>
      </Dialog>

      {/* Activity */}
      <Dialog open={!!activityFor} onOpenChange={(o) => !o && setActivityFor(null)}>
        <DialogContent>
          <DialogHeader><DialogTitle>Aktivite Ekle: {activityFor?.title}</DialogTitle></DialogHeader>
          <div className="grid grid-cols-2 gap-3">
            <div>
              <Label>Tür</Label>
              <Select value={activity.type} onValueChange={(v) => setActivity({ ...activity, type: v })}>
                <SelectTrigger><SelectValue /></SelectTrigger>
                <SelectContent>
                  <SelectItem value="call">Telefon</SelectItem>
                  <SelectItem value="email">E-posta</SelectItem>
                  <SelectItem value="meeting">Toplantı</SelectItem>
                  <SelectItem value="site_visit">Saha Ziyareti</SelectItem>
                  <SelectItem value="note">Not</SelectItem>
                  <SelectItem value="task">Görev</SelectItem>
                </SelectContent>
              </Select>
            </div>
            <div>
              <Label>Sonuç</Label>
              <Select value={activity.outcome} onValueChange={(v) => setActivity({ ...activity, outcome: v })}>
                <SelectTrigger><SelectValue /></SelectTrigger>
                <SelectContent>
                  <SelectItem value="positive">Olumlu</SelectItem>
                  <SelectItem value="neutral">Nötr</SelectItem>
                  <SelectItem value="negative">Olumsuz</SelectItem>
                </SelectContent>
              </Select>
            </div>
            <div className="col-span-2">
              <Label>Konu</Label>
              <Input value={activity.subject}
                     onChange={(e) => setActivity({ ...activity, subject: e.target.value })} />
            </div>
            <div className="col-span-2">
              <Label>Detay</Label>
              <Textarea value={activity.body}
                        onChange={(e) => setActivity({ ...activity, body: e.target.value })} />
            </div>
          </div>
          <DialogFooter>
            <Button variant="outline" onClick={() => setActivityFor(null)}>İptal</Button>
            <Button onClick={submitActivity}>Kaydet</Button>
          </DialogFooter>
        </DialogContent>
      </Dialog>
    </div>
  );
}
