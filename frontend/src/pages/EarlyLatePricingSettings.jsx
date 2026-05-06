import { useEffect, useState } from 'react';
import api from '@/api/axios';
import { Card } from '@/components/ui/card';
import { Button } from '@/components/ui/button';
import { Input } from '@/components/ui/input';
import { Label } from '@/components/ui/label';
import { Select, SelectContent, SelectItem, SelectTrigger, SelectValue } from '@/components/ui/select';
import { Loader2, Plus, Trash2, Save, Clock } from 'lucide-react';
import { toast } from 'sonner';

const CHARGE_TYPES = [
  { v: 'flat', l: 'Sabit Tutar' },
  { v: 'percent_of_nightly', l: 'Gecelik %' },
  { v: 'percent_of_total', l: 'Toplam %' },
  { v: 'free', l: 'Ücretsiz' },
];

const blank = (label = '') => ({ id: '', label, from_hour: 8, to_hour: 12, charge_type: 'percent_of_nightly', charge_value: 50 });

function RuleEditor({ title, rules, setRules }) {
  return (
    <Card className="p-4">
      <div className="flex items-center justify-between mb-3">
        <h2 className="font-semibold flex items-center gap-2"><Clock className="w-4 h-4" /> {title}</h2>
        <Button size="sm" variant="outline" onClick={() => setRules([...rules, blank()])}>
          <Plus className="w-3.5 h-3.5 mr-1" /> Kural Ekle
        </Button>
      </div>
      {rules.length === 0 && <div className="text-sm text-gray-400 py-4 text-center">Kural yok</div>}
      <div className="space-y-2">
        {rules.map((r, i) => (
          <div key={i} className="grid grid-cols-12 gap-2 items-end border rounded p-2">
            <div className="col-span-3">
              <Label className="text-[10px]">Etiket</Label>
              <Input value={r.label} onChange={e => { const c = [...rules]; c[i] = { ...r, label: e.target.value }; setRules(c); }} className="h-8" />
            </div>
            <div className="col-span-2">
              <Label className="text-[10px]">Başlangıç (saat)</Label>
              <Input type="number" min={0} max={23} value={r.from_hour} onChange={e => { const c = [...rules]; c[i] = { ...r, from_hour: parseInt(e.target.value) || 0 }; setRules(c); }} className="h-8" />
            </div>
            <div className="col-span-2">
              <Label className="text-[10px]">Bitiş (saat)</Label>
              <Input type="number" min={0} max={23} value={r.to_hour} onChange={e => { const c = [...rules]; c[i] = { ...r, to_hour: parseInt(e.target.value) || 0 }; setRules(c); }} className="h-8" />
            </div>
            <div className="col-span-2">
              <Label className="text-[10px]">Ücret Tipi</Label>
              <Select value={r.charge_type} onValueChange={v => { const c = [...rules]; c[i] = { ...r, charge_type: v }; setRules(c); }}>
                <SelectTrigger className="h-8"><SelectValue /></SelectTrigger>
                <SelectContent>{CHARGE_TYPES.map(t => <SelectItem key={t.v} value={t.v}>{t.l}</SelectItem>)}</SelectContent>
              </Select>
            </div>
            <div className="col-span-2">
              <Label className="text-[10px]">Değer</Label>
              <Input type="number" value={r.charge_value} onChange={e => { const c = [...rules]; c[i] = { ...r, charge_value: parseFloat(e.target.value) || 0 }; setRules(c); }} className="h-8" disabled={r.charge_type === 'free'} />
            </div>
            <div className="col-span-1 flex justify-end">
              <Button size="icon" variant="ghost" onClick={() => setRules(rules.filter((_, j) => j !== i))} className="h-8 w-8 text-red-600">
                <Trash2 className="w-3.5 h-3.5" />
              </Button>
            </div>
          </div>
        ))}
      </div>
    </Card>
  );
}

export default function EarlyLatePricingSettings() {
  const [cfg, setCfg] = useState(null);
  const [loading, setLoading] = useState(true);
  const [saving, setSaving] = useState(false);

  useEffect(() => {
    api.get('/pms/settings/early-late-pricing')
      .then(r => setCfg(r.data))
      .catch(e => toast.error('Yükleme hatası: ' + (e.response?.data?.detail || e.message)))
      .finally(() => setLoading(false));
  }, []);

  const save = async () => {
    setSaving(true);
    try {
      const { data } = await api.put('/pms/settings/early-late-pricing', cfg);
      setCfg(data);
      toast.success('Kurallar kaydedildi');
    } catch (e) {
      toast.error('Hata: ' + (e.response?.data?.detail || e.message));
    } finally { setSaving(false); }
  };

  if (loading || !cfg) return <div className="p-12 text-center"><Loader2 className="inline w-6 h-6 animate-spin" /></div>;

  return (
    <div className="p-6 max-w-6xl mx-auto space-y-4" data-testid="early-late-pricing-settings">
      <div className="flex items-center justify-between">
        <div>
          <h1 className="text-2xl font-bold flex items-center gap-2"><Clock className="w-6 h-6 text-amber-600" /> Erken Giriş / Geç Çıkış Ücretleri</h1>
          <p className="text-sm text-gray-500 mt-1">Saat-bazlı otomatik ek ücret kuralları. Standart saatler dışında uygulanır.</p>
        </div>
        <Button onClick={save} disabled={saving} className="bg-amber-600 hover:bg-amber-700">
          {saving ? <Loader2 className="w-4 h-4 mr-2 animate-spin" /> : <Save className="w-4 h-4 mr-2" />} Kaydet
        </Button>
      </div>

      <Card className="p-4 grid grid-cols-2 gap-4">
        <div>
          <Label className="text-xs">Standart Giriş Saati</Label>
          <Input type="number" min={0} max={23} value={cfg.standard_checkin_hour} onChange={e => setCfg({ ...cfg, standard_checkin_hour: parseInt(e.target.value) || 14 })} className="h-9" />
        </div>
        <div>
          <Label className="text-xs">Standart Çıkış Saati</Label>
          <Input type="number" min={0} max={23} value={cfg.standard_checkout_hour} onChange={e => setCfg({ ...cfg, standard_checkout_hour: parseInt(e.target.value) || 12 })} className="h-9" />
        </div>
      </Card>

      <RuleEditor title="Erken Giriş Kuralları" rules={cfg.early_checkin} setRules={r => setCfg({ ...cfg, early_checkin: r })} />
      <RuleEditor title="Geç Çıkış Kuralları" rules={cfg.late_checkout} setRules={r => setCfg({ ...cfg, late_checkout: r })} />
    </div>
  );
}
