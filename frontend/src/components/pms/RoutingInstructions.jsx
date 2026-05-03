import { useEffect, useState } from 'react';
import axios from 'axios';
import { toast } from 'sonner';
import { Card, CardContent, CardHeader, CardTitle } from '@/components/ui/card';
import { Badge } from '@/components/ui/badge';
import { Button } from '@/components/ui/button';
import { Input } from '@/components/ui/input';
import { Label } from '@/components/ui/label';
import { Select, SelectContent, SelectItem, SelectTrigger, SelectValue } from '@/components/ui/select';
import { Dialog, DialogContent, DialogHeader, DialogTitle } from '@/components/ui/dialog';
import { ArrowRightLeft, Plus, Trash2, Building2, User, CreditCard, FileText } from 'lucide-react';

const CHARGE_CATEGORIES = [
  { value: 'room', label: 'Oda Ucreti' },
  { value: 'fb', label: 'Yiyecek & Icecek' },
  { value: 'minibar', label: 'Minibar' },
  { value: 'laundry', label: 'Camasirhane' },
  { value: 'telephone', label: 'Telefon' },
  { value: 'spa', label: 'Spa & Wellness' },
  { value: 'parking', label: 'Otopark' },
  { value: 'business_center', label: 'Is Merkezi' },
  { value: 'other', label: 'Diger' },
];

const ROUTING_TARGETS = [
  { value: 'guest', label: 'Misafir Folyosu', icon: User },
  { value: 'company', label: 'Şirket Folyosu', icon: Building2 },
  { value: 'travel_agent', label: 'Acente Folyosu', icon: FileText },
  { value: 'group_master', label: 'Grup Master Folyo', icon: CreditCard },
];

// Backend'den dönen kayıtlı kurallarda label alanları yok — UI'da
// göstermek için kategori/target değerinden yeniden hesaplıyoruz.
const enrichRule = (rule) => {
  const cat = CHARGE_CATEGORIES.find(c => c.value === rule.category);
  const tgt = ROUTING_TARGETS.find(t => t.value === rule.target);
  return {
    ...rule,
    category_label: rule.category_label || cat?.label || rule.category,
    target_label: rule.target_label || tgt?.label || rule.target,
  };
};

const RoutingInstructions = ({ booking, onSave }) => {
  const [rules, setRules] = useState(() =>
    (booking?.routing_rules || []).map(enrichRule),
  );
  const [showAdd, setShowAdd] = useState(false);
  const [newRule, setNewRule] = useState({ category: '', target: '', limit: '', notes: '' });
  const [saving, setSaving] = useState(false);

  // Booking değiştiğinde sunucudan kayıtlı kuralları çek — booking objesi
  // listeleme endpoint'inden geldiyse routing_rules dahil olmayabilir.
  useEffect(() => {
    const id = booking?.id;
    if (!id) return;
    let cancelled = false;
    axios.get(`/api/frontdesk/booking/${id}/routing-rules`)
      .then(res => {
        if (cancelled) return;
        const fetched = res?.data?.rules || [];
        setRules(fetched.map(enrichRule));
      })
      .catch(() => { /* sessiz fail — UI booking.routing_rules ile devam eder */ });
    return () => { cancelled = true; };
  }, [booking?.id]);

  const addRule = () => {
    if (!newRule.category || !newRule.target) return;
    const cat = CHARGE_CATEGORIES.find(c => c.value === newRule.category);
    const tgt = ROUTING_TARGETS.find(t => t.value === newRule.target);
    setRules(prev => [...prev, {
      id: `tmp-${Date.now()}`,
      category: newRule.category,
      category_label: cat?.label,
      target: newRule.target,
      target_label: tgt?.label,
      limit: newRule.limit ? parseFloat(newRule.limit) : null,
      notes: newRule.notes,
      active: true,
    }]);
    setNewRule({ category: '', target: '', limit: '', notes: '' });
    setShowAdd(false);
  };

  const removeRule = (id) => setRules(prev => prev.filter(r => r.id !== id));

  const saveRules = async () => {
    if (!booking?.id) {
      toast.error('Geçersiz rezervasyon');
      return;
    }
    setSaving(true);
    try {
      // Backend persist için label alanlarını çıkarıyoruz (her açılışta
      // enrichRule yeniden hesaplıyor; veride tekrar tutmak gereksiz).
      const payload = rules.map(({ category_label, target_label, ...rest }) => rest);
      await axios.post(`/api/frontdesk/booking/${booking.id}/routing-rules`, { rules: payload });
      toast.success('Yonlendirme kuralları kaydedildi');
      onSave?.(payload);
    } catch (err) {
      const detail = err?.response?.data?.detail || 'Kurallar kaydedilemedi';
      toast.error(detail);
    } finally {
      setSaving(false);
    }
  };

  return (
    <Card>
      <CardHeader className="pb-2">
        <div className="flex items-center justify-between">
          <CardTitle className="text-sm flex items-center gap-2">
            <ArrowRightLeft className="h-4 w-4" /> Masraf Yonlendirme Kurallari
          </CardTitle>
          <div className="flex gap-2">
            <Button size="sm" variant="outline" onClick={() => setShowAdd(true)}>
              <Plus className="h-3 w-3 mr-1" /> Kural Ekle
            </Button>
            <Button size="sm" onClick={saveRules} disabled={rules.length === 0 || saving}>Kaydet</Button>
          </div>
        </div>
      </CardHeader>
      <CardContent>
        {rules.length === 0 ? (
          <p className="text-sm text-muted-foreground text-center py-4">
            Henüz yonlendirme kuralı tanimlanmadi. Tüm masraflar misafir folyosuna yansiyacak.
          </p>
        ) : (
          <div className="space-y-2">
            {rules.map(rule => (
              <div key={rule.id} className="flex items-center justify-between border rounded-lg p-3">
                <div className="flex items-center gap-3">
                  <Badge variant="outline">{rule.category_label}</Badge>
                  <ArrowRightLeft className="h-3 w-3 text-muted-foreground" />
                  <Badge>{rule.target_label}</Badge>
                  {rule.limit && <span className="text-xs text-muted-foreground">Limit: {rule.limit} TL</span>}
                </div>
                <Button size="sm" variant="ghost" onClick={() => removeRule(rule.id)}>
                  <Trash2 className="h-3 w-3 text-red-500" />
                </Button>
              </div>
            ))}
          </div>
        )}

        <Dialog open={showAdd} onOpenChange={setShowAdd}>
          <DialogContent>
            <DialogHeader>
              <DialogTitle>Yeni Yonlendirme Kurali</DialogTitle>
            </DialogHeader>
            <div className="space-y-4">
              <div>
                <Label>Masraf Kategorisi</Label>
                <Select value={newRule.category} onValueChange={v => setNewRule(p => ({ ...p, category: v }))}>
                  <SelectTrigger><SelectValue placeholder="Kategori seçin..." /></SelectTrigger>
                  <SelectContent>
                    {CHARGE_CATEGORIES.map(c => <SelectItem key={c.value} value={c.value}>{c.label}</SelectItem>)}
                  </SelectContent>
                </Select>
              </div>
              <div>
                <Label>Hedef Folyo</Label>
                <Select value={newRule.target} onValueChange={v => setNewRule(p => ({ ...p, target: v }))}>
                  <SelectTrigger><SelectValue placeholder="Hedef seçin..." /></SelectTrigger>
                  <SelectContent>
                    {ROUTING_TARGETS.map(t => <SelectItem key={t.value} value={t.value}>{t.label}</SelectItem>)}
                  </SelectContent>
                </Select>
              </div>
              <div>
                <Label>Limit (TL, opsiyonel)</Label>
                <Input type="number" value={newRule.limit} onChange={e => setNewRule(p => ({ ...p, limit: e.target.value }))} placeholder="Limitsiz" />
              </div>
              <div>
                <Label>Not</Label>
                <Input value={newRule.notes} onChange={e => setNewRule(p => ({ ...p, notes: e.target.value }))} placeholder="Opsiyonel açıklama" />
              </div>
              <Button className="w-full" onClick={addRule}>Kural Ekle</Button>
            </div>
          </DialogContent>
        </Dialog>
      </CardContent>
    </Card>
  );
};

export default RoutingInstructions;
