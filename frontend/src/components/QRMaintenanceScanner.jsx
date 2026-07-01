import React, { useState } from 'react';
import { Card, CardContent, CardHeader, CardTitle } from '@/components/ui/card';
import { Button } from '@/components/ui/button';
import { Wrench } from 'lucide-react';
import { toast } from 'sonner';
import axios from 'axios';
import { useTranslation } from 'react-i18next';

const ISSUE_TYPES = [
  { value: 'plumbing', label: 'Tesisat' },
  { value: 'hvac', label: 'İklimlendirme (HVAC)' },
  { value: 'electrical', label: 'Elektrik' },
  { value: 'furniture', label: 'Mobilya' },
  { value: 'housekeeping_damage', label: 'Kat Hizmetleri Hasarı' },
  { value: 'other', label: 'Diğer' },
];

const PRIORITIES = [
  { value: 'low', label: 'Düşük' },
  { value: 'normal', label: 'Normal' },
  { value: 'high', label: 'Yüksek' },
  { value: 'urgent', label: 'Acil' },
];

const QRMaintenanceScanner = () => {
  const { t } = useTranslation();
  const [submitting, setSubmitting] = useState(false);
  const [roomNumber, setRoomNumber] = useState('');
  const [assetId, setAssetId] = useState('');
  const [issueType, setIssueType] = useState('other');
  const [priority, setPriority] = useState('normal');
  const [description, setDescription] = useState('');

  const resetForm = () => {
    setRoomNumber('');
    setAssetId('');
    setIssueType('other');
    setPriority('normal');
    setDescription('');
  };

  const handleCreateWorkOrder = async () => {
    if (!roomNumber.trim() && !assetId.trim()) {
      toast.error('Oda numarası veya varlık kodu girin');
      return;
    }
    setSubmitting(true);
    try {
      await axios.post('/maintenance/work-orders', {
        room_number: roomNumber.trim() || null,
        asset_id: assetId.trim() || null,
        issue_type: issueType,
        priority,
        source: 'housekeeping',
        description: description.trim() || null,
      });
      toast.success('Bakım iş emri oluşturuldu');
      resetForm();
    } catch (error) {
      toast.error('İş emri oluşturulamadı');
    } finally {
      setSubmitting(false);
    }
  };

  return (
    <Card>
      <CardHeader>
        <CardTitle className="flex items-center text-lg">
          <Wrench className="w-5 h-5 mr-2" />
          {t('cm.components_QRMaintenanceScanner.qr_ile_bakim_ac')}
        </CardTitle>
      </CardHeader>
      <CardContent>
        <div className="space-y-3">
          <div>
            <label className="block text-sm text-gray-600 mb-1">Oda Numarası</label>
            <input
              type="text"
              className="w-full border rounded-md px-3 py-2 text-sm"
              value={roomNumber}
              onChange={(e) => setRoomNumber(e.target.value)}
              placeholder="Örn. 205"
            />
          </div>
          <div>
            <label className="block text-sm text-gray-600 mb-1">Varlık / Ekipman Kodu (opsiyonel)</label>
            <input
              type="text"
              className="w-full border rounded-md px-3 py-2 text-sm"
              value={assetId}
              onChange={(e) => setAssetId(e.target.value)}
              placeholder="Örn. HVAC-205"
            />
          </div>
          <div>
            <label className="block text-sm text-gray-600 mb-1">Arıza Türü</label>
            <select
              className="w-full border rounded-md px-3 py-2 text-sm"
              value={issueType}
              onChange={(e) => setIssueType(e.target.value)}
            >
              {ISSUE_TYPES.map((it) => (
                <option key={it.value} value={it.value}>{it.label}</option>
              ))}
            </select>
          </div>
          <div>
            <label className="block text-sm text-gray-600 mb-1">Öncelik</label>
            <select
              className="w-full border rounded-md px-3 py-2 text-sm"
              value={priority}
              onChange={(e) => setPriority(e.target.value)}
            >
              {PRIORITIES.map((p) => (
                <option key={p.value} value={p.value}>{p.label}</option>
              ))}
            </select>
          </div>
          <div>
            <label className="block text-sm text-gray-600 mb-1">Açıklama</label>
            <textarea
              className="w-full border rounded-md px-3 py-2 text-sm"
              rows={3}
              value={description}
              onChange={(e) => setDescription(e.target.value)}
              placeholder="Sorunu kısaca açıklayın"
            />
          </div>
          <Button
            className="w-full bg-green-600 hover:bg-green-700"
            onClick={handleCreateWorkOrder}
            disabled={submitting}
          >
            {submitting ? 'Oluşturuluyor…' : t('cm.components_QRMaintenanceScanner.gorev_olustur')}
          </Button>
        </div>
      </CardContent>
    </Card>
  );
};

export default QRMaintenanceScanner;
