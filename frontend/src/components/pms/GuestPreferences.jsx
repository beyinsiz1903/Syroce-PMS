import { useState } from 'react';
import axios from 'axios';
import { toast } from 'sonner';
import { Card, CardContent, CardHeader, CardTitle } from '@/components/ui/card';
import { Button } from '@/components/ui/button';
import { Input } from '@/components/ui/input';
import { Label } from '@/components/ui/label';
import { Select, SelectContent, SelectItem, SelectTrigger, SelectValue } from '@/components/ui/select';
import { Textarea } from '@/components/ui/textarea';
import {
  Heart, Bed, Thermometer, AlertTriangle, Coffee, Save, Gift, Cake, Star, Bell
} from 'lucide-react';

const PREFERENCE_CATEGORIES = {
  room: {
    label: 'Oda Tercihleri',
    icon: Bed,
    items: [
      { key: 'pillow_type', label: 'Yastik Tipi', options: ['Yumusak', 'Sert', 'Ortopedik', 'Tuy', 'Anti-Alerjik'] },
      { key: 'bed_type', label: 'Yatak Tercihi', options: ['King', 'Twin', 'Queen', 'Ekstra Yatak'] },
      { key: 'floor_pref', label: 'Kat Tercihi', options: ['Yuksek Kat', 'Alcak Kat', 'Orta Kat', 'Fark Etmez'] },
      { key: 'room_view', label: 'Manzara', options: ['Deniz', 'Havuz', 'Bahce', 'Sehir', 'Fark Etmez'] },
      { key: 'room_location', label: 'Konum', options: ['Asansore Yakin', 'Asansordan Uzak', 'Kose Oda', 'Sessiz Bolge'] },
    ]
  },
  comfort: {
    label: 'Konfor Tercihleri',
    icon: Thermometer,
    items: [
      { key: 'room_temp', label: 'Oda Sicakligi', options: ['18°C', '20°C', '22°C', '24°C', '26°C'] },
      { key: 'extra_blanket', label: 'Ekstra Battaniye', options: ['Evet', 'Hayir'] },
      { key: 'bath_amenities', label: 'Banyo Urunleri', options: ['Standart', 'Premium', 'Hipoalerjenik'] },
      { key: 'towel_pref', label: 'Havlu', options: ['Gunluk Degisim', 'Talep Uzerine', 'Cevreci (2 Gunde Bir)'] },
    ]
  },
  dining: {
    label: 'Yeme-Icme',
    icon: Coffee,
    items: [
      { key: 'diet', label: 'Diyet', options: ['Normal', 'Vejetaryen', 'Vegan', 'Glutensiz', 'Helal', 'Koser'] },
      { key: 'breakfast_time', label: 'Kahvalti Saati', options: ['Erken (06:30)', 'Normal (08:00)', 'Gec (10:00)'] },
      { key: 'minibar_pref', label: 'Minibar', options: ['Dolu', 'Bos', 'Sadece Su', 'Alkolsuz'] },
      { key: 'welcome_drink', label: 'Hosgeldin Icecegi', options: ['Cay', 'Kahve', 'Meyve Suyu', 'Sampanya', 'Yok'] },
    ]
  },
  special: {
    label: 'Ozel Durumlar',
    icon: AlertTriangle,
    items: [
      { key: 'allergies', label: 'Alerjiler', type: 'text', placeholder: 'Fistik, toz, kedi...' },
      { key: 'medical', label: 'Saglik Notu', type: 'text', placeholder: 'Ozel saglik durumu...' },
      { key: 'mobility', label: 'Hareket Kisitlamasi', options: ['Yok', 'Tekerlekli Sandalye', 'Yurume Guclugu', 'Gorme Engeli'] },
      { key: 'smoking', label: 'Sigara', options: ['Icmez', 'Icer (Balkon)', 'Icer (Dis Alan)'] },
      { key: 'pet', label: 'Evcil Hayvan', options: ['Yok', 'Kopek', 'Kedi', 'Diger'] },
    ]
  }
};

const GuestPreferences = ({ guest, onSave }) => {
  const [prefs, setPrefs] = useState(guest?.preferences || {});
  const [notes, setNotes] = useState(guest?.preference_notes || '');
  const [birthday, setBirthday] = useState(guest?.birthday || '');
  const [anniversary, setAnniversary] = useState(guest?.anniversary || '');
  const [vipLevel, setVipLevel] = useState(guest?.vip_level || '');
  const [saving, setSaving] = useState(false);

  const updatePref = (key, value) => setPrefs(prev => ({ ...prev, [key]: value }));

  const savePreferences = async () => {
    setSaving(true);
    try {
      await axios.patch(`/pms/guests/${guest?.id}/preferences`, {
        preferences: prefs,
        preference_notes: notes,
        birthday, anniversary, vip_level: vipLevel
      });
      toast.success('Misafir tercihleri kaydedildi');
      onSave?.({ ...prefs, preference_notes: notes, birthday, anniversary, vip_level: vipLevel });
    } catch {
      toast.error('Tercihler kaydedilemedi');
    } finally {
      setSaving(false);
    }
  };

  return (
    <div className="space-y-4">
      <div className="flex items-center justify-between">
        <h3 className="text-lg font-semibold flex items-center gap-2">
          <Heart className="h-5 w-5 text-red-500" /> Misafir Tercihleri - {guest?.name}
        </h3>
        <Button onClick={savePreferences} disabled={saving}><Save className="h-4 w-4 mr-1" /> Kaydet</Button>
      </div>

      <div className="grid grid-cols-1 md:grid-cols-3 gap-4">
        <Card>
          <CardHeader className="pb-2">
            <CardTitle className="text-sm flex items-center gap-2"><Star className="h-4 w-4" /> VIP & Ozel Gunler</CardTitle>
          </CardHeader>
          <CardContent className="space-y-3">
            <div>
              <Label>VIP Seviyesi</Label>
              <Select value={vipLevel} onValueChange={setVipLevel}>
                <SelectTrigger><SelectValue placeholder="VIP Seviyesi..." /></SelectTrigger>
                <SelectContent>
                  <SelectItem value="none">Normal</SelectItem>
                  <SelectItem value="silver">Silver VIP</SelectItem>
                  <SelectItem value="gold">Gold VIP</SelectItem>
                  <SelectItem value="platinum">Platinum VIP</SelectItem>
                  <SelectItem value="diamond">Diamond VIP</SelectItem>
                  <SelectItem value="owner">Otel Sahibi Misafiri</SelectItem>
                </SelectContent>
              </Select>
            </div>
            <div>
              <Label className="flex items-center gap-1"><Cake className="h-3 w-3" /> Dogum Tarihi</Label>
              <Input type="date" value={birthday} onChange={e => setBirthday(e.target.value)} />
            </div>
            <div>
              <Label className="flex items-center gap-1"><Gift className="h-3 w-3" /> Evlilik Yildonumu</Label>
              <Input type="date" value={anniversary} onChange={e => setAnniversary(e.target.value)} />
            </div>
          </CardContent>
        </Card>

        <Card className="md:col-span-2">
          <CardHeader className="pb-2">
            <CardTitle className="text-sm flex items-center gap-2"><Bell className="h-4 w-4" /> Ozel Notlar</CardTitle>
          </CardHeader>
          <CardContent>
            <Textarea
              value={notes}
              onChange={e => setNotes(e.target.value)}
              placeholder="Misafir hakkinda ozel notlar, istekler, dikkat edilecek hususlar..."
              rows={4}
            />
          </CardContent>
        </Card>
      </div>

      {Object.entries(PREFERENCE_CATEGORIES).map(([catKey, cat]) => (
        <Card key={catKey}>
          <CardHeader className="pb-2">
            <CardTitle className="text-sm flex items-center gap-2">
              <cat.icon className="h-4 w-4" /> {cat.label}
            </CardTitle>
          </CardHeader>
          <CardContent>
            <div className="grid grid-cols-1 sm:grid-cols-2 lg:grid-cols-3 gap-3">
              {cat.items.map(item => (
                <div key={item.key}>
                  <Label className="text-xs">{item.label}</Label>
                  {item.type === 'text' ? (
                    <Input
                      value={prefs[item.key] || ''}
                      onChange={e => updatePref(item.key, e.target.value)}
                      placeholder={item.placeholder}
                      className="h-8 text-sm"
                    />
                  ) : (
                    <Select value={prefs[item.key] || ''} onValueChange={v => updatePref(item.key, v)}>
                      <SelectTrigger className="h-8 text-sm"><SelectValue placeholder="Secin..." /></SelectTrigger>
                      <SelectContent>
                        {item.options.map(opt => <SelectItem key={opt} value={opt}>{opt}</SelectItem>)}
                      </SelectContent>
                    </Select>
                  )}
                </div>
              ))}
            </div>
          </CardContent>
        </Card>
      ))}
    </div>
  );
};

export default GuestPreferences;
