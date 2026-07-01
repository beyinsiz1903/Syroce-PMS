import { useState } from 'react';
import axios from 'axios';
import { toast } from 'sonner';
import { Card, CardContent, CardHeader, CardTitle } from '@/components/ui/card';
import { Badge } from '@/components/ui/badge';
import { Button } from '@/components/ui/button';
import { Input } from '@/components/ui/input';
import { Label } from '@/components/ui/label';
import { Select, SelectContent, SelectItem, SelectTrigger, SelectValue } from '@/components/ui/select';
import { Dialog, DialogContent, DialogHeader, DialogTitle } from '@/components/ui/dialog';
import {
  BellOff, Link2, Wine, Plus, Trash2, Clock, CheckCircle, AlertTriangle, DoorOpen
} from 'lucide-react';
import { useTranslation } from 'react-i18next';

const MINIBAR_ITEMS = [
  { code: 'water', name: 'Su (500ml)', price: 5 },
  { code: 'cola', name: 'Kola', price: 8 },
  { code: 'juice', name: 'Meyve Suyu', price: 10 },
  { code: 'beer', name: 'Bira', price: 25 },
  { code: 'wine_mini', name: 'Sarap (Minibar)', price: 40 },
  { code: 'chips', name: 'Cips', price: 12 },
  { code: 'chocolate', name: 'Cikolata', price: 15 },
  { code: 'nuts', name: 'Kuruyemis', price: 18 },
  { code: 'whisky_mini', name: 'Viski (50ml)', price: 35 },
  { code: 'vodka_mini', name: 'Votka (50ml)', price: 30 },
];

const CHECKOUT_RULES = [
  { key: 'early_checkout', label: 'Erken Çıkış (12:00 oncesi)', charge: 0, description: 'Ücret yok' },
  { key: 'standard_checkout', label: 'Standart Çıkış (12:00)', charge: 0, description: 'Normal çıkış saati' },
  { key: 'late_14', label: 'Gec Çıkış (14:00)', charge: 30, description: 'Oda ucretinin %30' },
  { key: 'late_17', label: 'Gec Çıkış (17:00)', charge: 50, description: 'Oda ucretinin %50' },
  { key: 'late_after_17', label: 'Gec Çıkış (17:00 sonrasi)', charge: 100, description: 'Tam gun ucreti' },
];

const RoomFeaturesPanel = ({ room, onUpdate }) => {
  const { t } = useTranslation();
  const [dndEnabled, setDndEnabled] = useState(room?.dnd || false);
  const [connectedRoom, setConnectedRoom] = useState(room?.connected_room || '');
  const [minibarItems, setMinibarItems] = useState([]);
  const [showMinibar, setShowMinibar] = useState(false);
  const [showCheckoutRules, setShowCheckoutRules] = useState(false);
  const [selectedMinibarItem, setSelectedMinibarItem] = useState('');
  const [minibarQty, setMinibarQty] = useState(1);

  const toggleDND = async () => {
    const newVal = !dndEnabled;
    try {
      await axios.patch(`/pms/rooms/${room._id || room.id}/features`, { dnd: newVal });
      setDndEnabled(newVal);
      toast.success(newVal ? 'DND Aktif' : 'DND Kapatildi');
      onUpdate?.();
    } catch {
      toast.error('DND durumu güncellenemedi');
    }
  };

  const setConnecting = async () => {
    try {
      await axios.patch(`/pms/rooms/${room._id || room.id}/features`, { connected_room: connectedRoom });
      toast.success(`Oda ${room.room_number} → ${connectedRoom} baglandi`);
      onUpdate?.();
    } catch {
      toast.error('Oda baglama işlemi başarısız');
    }
  };

  const addMinibarCharge = () => {
    if (!selectedMinibarItem) return;
    const item = MINIBAR_ITEMS.find(i => i.code === selectedMinibarItem);
    if (!item) return;
    setMinibarItems(prev => [...prev, { ...item, quantity: minibarQty, total: item.price * minibarQty }]);
    setSelectedMinibarItem('');
    setMinibarQty(1);
  };

  const removeMinibarItem = (idx) => {
    setMinibarItems(prev => prev.filter((_, i) => i !== idx));
  };

  const postMinibarCharges = async () => {
    if (minibarItems.length === 0) return;
    const total = minibarItems.reduce((sum, i) => sum + i.total, 0);
    try {
      await axios.post(`/frontdesk/folio/${room.booking_id}/charge`, {
        description: 'Minibar - ' + minibarItems.map(i => `${i.quantity}x ${i.name}`).join(', '),
        amount: total,
        charge_category: 'minibar',
        quantity: 1
      });
      toast.success(`Minibar ucreti eklendi: ${total} TL`);
      setMinibarItems([]);
      setShowMinibar(false);
    } catch {
      toast.error('Minibar ucreti eklenemedi');
    }
  };

  const minibarTotal = minibarItems.reduce((sum, i) => sum + i.total, 0);

  return (
    <div className="space-y-4">
      <div className="grid grid-cols-1 md:grid-cols-3 gap-4">
        <Card>
          <CardHeader className="pb-2">
            <CardTitle className="text-sm flex items-center gap-2">
              <BellOff className="h-4 w-4" />
              Rahatsiz Etmeyin (DND)
            </CardTitle>
          </CardHeader>
          <CardContent>
            <div className="flex items-center justify-between">
              <Badge variant={dndEnabled ? 'destructive' : 'outline'}>
                {dndEnabled ? 'AKTIF' : 'KAPALI'}
              </Badge>
              <Button size="sm" variant={dndEnabled ? 'destructive' : 'default'} onClick={toggleDND}>
                {dndEnabled ? 'Kapat' : 'Aktif Et'}
              </Button>
            </div>
          </CardContent>
        </Card>

        <Card>
          <CardHeader className="pb-2">
            <CardTitle className="text-sm flex items-center gap-2">
              <Link2 className="h-4 w-4" />
              {t('cm.components_pms_RoomFeaturesPanel.baglanti_oda')}
            </CardTitle>
          </CardHeader>
          <CardContent>
            <div className="flex gap-2">
              <Input
                placeholder={t('cm.components_pms_RoomFeaturesPanel.oda_no')}
                value={connectedRoom}
                onChange={(e) => setConnectedRoom(e.target.value)}
                className="flex-1"
              />
              <Button size="sm" onClick={setConnecting} disabled={!connectedRoom}>
                <Link2 className="h-4 w-4" />
              </Button>
            </div>
            {room?.connected_room && (
              <p className="text-xs text-muted-foreground mt-1">Mevcut: {room.connected_room}</p>
            )}
          </CardContent>
        </Card>

        <Card>
          <CardHeader className="pb-2">
            <CardTitle className="text-sm flex items-center gap-2">
              <Wine className="h-4 w-4" />
              Minibar
            </CardTitle>
          </CardHeader>
          <CardContent>
            <Button size="sm" className="w-full" onClick={() => setShowMinibar(true)}>
              <Plus className="h-4 w-4 mr-1" /> Minibar Girisi
            </Button>
          </CardContent>
        </Card>
      </div>

      <Card>
        <CardHeader className="pb-2">
          <CardTitle className="text-sm flex items-center gap-2">
            <Clock className="h-4 w-4" />
            {t('cm.components_pms_RoomFeaturesPanel.erken_gec_cikis_kurallari')}
          </CardTitle>
        </CardHeader>
        <CardContent>
          <div className="grid grid-cols-1 sm:grid-cols-2 lg:grid-cols-5 gap-2">
            {CHECKOUT_RULES.map((rule) => (
              <div key={rule.key} className="border rounded-lg p-3 text-center">
                <p className="text-xs font-medium">{rule.label}</p>
                <p className={`text-lg font-bold ${rule.charge > 0 ? 'text-amber-600' : 'text-green-600'}`}>
                  {rule.charge > 0 ? `%${rule.charge}` : 'Ucretsiz'}
                </p>
                <p className="text-xs text-muted-foreground">{rule.description}</p>
              </div>
            ))}
          </div>
        </CardContent>
      </Card>

      <Dialog open={showMinibar} onOpenChange={setShowMinibar}>
        <DialogContent className="max-w-lg">
          <DialogHeader>
            <DialogTitle className="flex items-center gap-2">
              <Wine className="h-5 w-5" /> {t('cm.components_pms_RoomFeaturesPanel.minibar_tuketim_girisi_oda')} {room?.room_number}
            </DialogTitle>
          </DialogHeader>
          <div className="space-y-4">
            <div className="flex gap-2">
              <Select value={selectedMinibarItem} onValueChange={setSelectedMinibarItem}>
                <SelectTrigger className="flex-1">
                  <SelectValue placeholder={t('cm.components_pms_RoomFeaturesPanel.urun_secin')} />
                </SelectTrigger>
                <SelectContent>
                  {MINIBAR_ITEMS.map(item => (
                    <SelectItem key={item.code} value={item.code}>
                      {item.name} - {item.price} TL
                    </SelectItem>
                  ))}
                </SelectContent>
              </Select>
              <Input
                type="number"
                min={1}
                max={10}
                value={minibarQty}
                onChange={(e) => setMinibarQty(parseInt(e.target.value) || 1)}
                className="w-20"
              />
              <Button onClick={addMinibarCharge} disabled={!selectedMinibarItem}>
                <Plus className="h-4 w-4" />
              </Button>
            </div>

            {minibarItems.length > 0 && (
              <div className="border rounded-lg">
                <div className="divide-y">
                  {minibarItems.map((item, idx) => (
                    <div key={idx} className="flex items-center justify-between p-2 text-sm">
                      <span>{item.quantity}x {item.name}</span>
                      <div className="flex items-center gap-2">
                        <span className="font-medium">{item.total} TL</span>
                        <Button size="sm" variant="ghost" onClick={() => removeMinibarItem(idx)}>
                          <Trash2 className="h-3 w-3 text-red-500" />
                        </Button>
                      </div>
                    </div>
                  ))}
                </div>
                <div className="border-t p-2 flex justify-between font-bold">
                  <span>{t('cm.components_pms_RoomFeaturesPanel.toplam')}</span>
                  <span>{minibarTotal} TL</span>
                </div>
              </div>
            )}

            <Button className="w-full" onClick={postMinibarCharges} disabled={minibarItems.length === 0}>
              <CheckCircle className="h-4 w-4 mr-1" /> {t('cm.components_pms_RoomFeaturesPanel.folyoya_ekle')}{minibarTotal} TL)
            </Button>
          </div>
        </DialogContent>
      </Dialog>
    </div>
  );
};

export default RoomFeaturesPanel;
