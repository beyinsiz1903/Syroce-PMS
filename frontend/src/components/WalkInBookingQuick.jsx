import React, { useState } from 'react';
import axios from 'axios';
import { toast } from 'sonner';
import { Card, CardContent, CardHeader, CardTitle } from '@/components/ui/card';
import { Button } from '@/components/ui/button';
import { Input } from '@/components/ui/input';
import { Label } from '@/components/ui/label';
import { UserPlus, Zap, ScanLine } from 'lucide-react';
import QuickIdScanDialog from '@/components/QuickIdScanDialog';

/**
 * Walk-in Booking Quick Form
 * Tek tık ile yürü-içeri rezervasyon
 */
const WalkInBookingQuick = ({ onSuccess }) => {
  const [formData, setFormData] = useState({
    guest_name: '',
    guest_phone: '',
    guest_email: '',
    guest_id_number: '',
    guest_id_type: '',
    guest_nationality: '',
    room_type: 'standard',
    nights: 1,
    adults: 1
  });
  const [loading, setLoading] = useState(false);
  const [scanOpen, setScanOpen] = useState(false);

  const handleScanned = (doc) => {
    const fullName = [doc.first_name, doc.last_name].filter(Boolean).join(' ').trim();
    setFormData(prev => ({
      ...prev,
      guest_name: fullName || prev.guest_name,
      guest_id_number: doc.id_number || doc.document_number || prev.guest_id_number,
      guest_id_type: doc.document_type || prev.guest_id_type,
      guest_nationality: doc.nationality || prev.guest_nationality,
    }));
  };

  const handleQuickBook = async () => {
    if (!formData.guest_name || !formData.guest_phone) {
      toast.error('Ad ve telefon zorunlu');
      return;
    }

    setLoading(true);
    try {
      const response = await axios.post('/bookings/walk-in-quick', {
        ...formData,
        check_in: new Date().toISOString().split('T')[0],
        check_out: new Date(Date.now() + formData.nights * 86400000).toISOString().split('T')[0],
        source: 'walk-in',
        status: 'confirmed'
      });

      toast.success(`Walk-in rezervasyon oluşturuldu! Oda: ${response.data.room_number}`);

      if (onSuccess) onSuccess(response.data);

      setFormData({
        guest_name: '',
        guest_phone: '',
        guest_email: '',
        guest_id_number: '',
        guest_id_type: '',
        guest_nationality: '',
        room_type: 'standard',
        nights: 1,
        adults: 1
      });
    } catch (error) {
      toast.error('Walk-in rezervasyon başarısız');
    } finally {
      setLoading(false);
    }
  };

  return (
    <Card className="border-2 border-green-300">
      <CardHeader>
        <CardTitle className="flex items-center justify-between">
          <span className="flex items-center gap-2">
            <UserPlus className="w-5 h-5 text-green-600" />
            Walk-in Rezervasyon
          </span>
          <Button
            type="button" size="sm" variant="outline"
            className="border-indigo-300 text-indigo-700 hover:bg-indigo-50"
            onClick={() => setScanOpen(true)}
            data-testid="walkin-scan-id-btn"
          >
            <ScanLine className="w-4 h-4 mr-1" /> Kimlik Tara
          </Button>
        </CardTitle>
      </CardHeader>
      <CardContent className="space-y-3">
        <div className="grid grid-cols-2 gap-3">
          <div>
            <Label className="text-xs">Ad Soyad*</Label>
            <Input
              value={formData.guest_name}
              onChange={(e) => setFormData({...formData, guest_name: e.target.value})}
              placeholder="Ahmet Yılmaz"
              className="h-9"
            />
          </div>
          <div>
            <Label className="text-xs">Telefon*</Label>
            <Input
              value={formData.guest_phone}
              onChange={(e) => setFormData({...formData, guest_phone: e.target.value})}
              placeholder="+90 555 000 00 00"
              className="h-9"
            />
          </div>
        </div>

        <div>
          <Label className="text-xs">E-posta</Label>
          <Input
            value={formData.guest_email}
            onChange={(e) => setFormData({...formData, guest_email: e.target.value})}
            placeholder="ahmet@example.com"
            className="h-9"
          />
        </div>

        <div className="grid grid-cols-3 gap-2">
          <div>
            <Label className="text-xs">Kimlik No</Label>
            <Input
              value={formData.guest_id_number}
              onChange={(e) => setFormData({...formData, guest_id_number: e.target.value})}
              placeholder="11111111111"
              className="h-9"
            />
          </div>
          <div>
            <Label className="text-xs">Belge Tipi</Label>
            <select
              value={formData.guest_id_type}
              onChange={(e) => setFormData({...formData, guest_id_type: e.target.value})}
              className="w-full h-9 border rounded px-2 text-sm"
            >
              <option value="">—</option>
              <option value="tc_kimlik">TC Kimlik</option>
              <option value="passport">Pasaport</option>
              <option value="drivers_license">Sürücü Belgesi</option>
            </select>
          </div>
          <div>
            <Label className="text-xs">Uyruk</Label>
            <Input
              value={formData.guest_nationality}
              onChange={(e) => setFormData({...formData, guest_nationality: e.target.value})}
              placeholder="TR"
              className="h-9"
            />
          </div>
        </div>

        <div className="grid grid-cols-3 gap-2">
          <div>
            <Label className="text-xs">Oda Tipi</Label>
            <select
              value={formData.room_type}
              onChange={(e) => setFormData({...formData, room_type: e.target.value})}
              className="w-full h-9 border rounded px-2 text-sm"
            >
              <option value="standard">Standart</option>
              <option value="deluxe">Deluxe</option>
              <option value="suite">Suit</option>
            </select>
          </div>
          <div>
            <Label className="text-xs">Gece</Label>
            <Input
              type="number"
              value={formData.nights}
              onChange={(e) => setFormData({...formData, nights: parseInt(e.target.value)})}
              min={1}
              className="h-9"
            />
          </div>
          <div>
            <Label className="text-xs">Yetişkin</Label>
            <Input
              type="number"
              value={formData.adults}
              onChange={(e) => setFormData({...formData, adults: parseInt(e.target.value)})}
              min={1}
              className="h-9"
            />
          </div>
        </div>

        <Button
          onClick={handleQuickBook}
          disabled={loading}
          className="w-full bg-green-600 hover:bg-green-700"
        >
          <Zap className="w-4 h-4 mr-2" />
          {loading ? 'Oluşturuluyor…' : 'Walk-in Hızlı Rezervasyon'}
        </Button>
      </CardContent>

      <QuickIdScanDialog
        open={scanOpen}
        onClose={() => setScanOpen(false)}
        onExtracted={handleScanned}
      />
    </Card>
  );
};

export default WalkInBookingQuick;
