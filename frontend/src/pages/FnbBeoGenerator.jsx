import React, { useState } from 'react';
import axios from 'axios';

import { Card, CardContent, CardHeader, CardTitle } from '@/components/ui/card';
import { Button } from '@/components/ui/button';
import { Input } from '@/components/ui/input';
import { Textarea } from '@/components/ui/textarea';
import { Calendar, Users, FileText, Clock, CheckCircle, Download } from 'lucide-react';
import { toast } from 'sonner';
import { useTranslation } from 'react-i18next';

const FnbBeoGenerator = ({ user, tenant, onLogout }) => {
  const { t } = useTranslation();
  const [form, setForm] = useState({
    event_name: '',
    client_name: '',
    date: '',
    start_time: '',
    end_time: '',
    venue: '',
    pax: 0,
    menu: '',
    setup: '',
    special_notes: '',
  });
  const [saving, setSaving] = useState(false);
  const [createdBeo, setCreatedBeo] = useState(null);

  const handleChange = (e) => {
    const { name, value } = e.target;
    setForm((prev) => ({ ...prev, [name]: value }));
  };

  const handleSubmit = async (e) => {
    e.preventDefault();
    setSaving(true);
    try {
      const payload = {
        ...form,
        pax: Number(form.pax) || 0,
      };
      const res = await axios.post('/fnb/beo', payload);
      setCreatedBeo({ ...payload, id: res.data.beo_id });
      toast.success(t('messages.success.created'));
    } catch (error) {
      console.error('Failed to create BEO', error);
      toast.error(t('messages.error.saveFailed'));
    } finally {
      setSaving(false);
    }
  };

  return (
    <>
      <div className="p-6 space-y-6">
        <div className="flex items-center justify-between">
          <div>
            <h1 className="text-2xl font-bold flex items-center gap-2">
              <FileText className="w-6 h-6 text-amber-600" />
              BEO Generator
            </h1>
            <p className="text-gray-600 mt-1 text-sm">
              Banquet Event Order detaylarını girin, kaydedilmiş bir BEO kaydı oluşturun.
            </p>
          </div>
        </div>

        <div className="grid grid-cols-1 lg:grid-cols-2 gap-6">
          {/* Form */}
          <Card>
            <CardHeader>
              <CardTitle>Yeni BEO</CardTitle>
            </CardHeader>
            <CardContent>
              <form className="space-y-3" onSubmit={handleSubmit}>
                <Input
                  name="event_name"
                  placeholder="Etkinlik adı"
                  value={form.event_name}
                  onChange={handleChange}
                  required
                />
                <Input
                  name="client_name"
                  placeholder="Müşteri / Grup adı"
                  value={form.client_name}
                  onChange={handleChange}
                  required
                />
                <div className="grid grid-cols-2 gap-2">
                  <Input
                    type="date"
                    name="date"
                    value={form.date}
                    onChange={handleChange}
                    required
                  />
                  <div className="grid grid-cols-2 gap-2">
                    <Input
                      type="time"
                      name="start_time"
                      value={form.start_time}
                      onChange={handleChange}
                      required
                    />
                    <Input
                      type="time"
                      name="end_time"
                      value={form.end_time}
                      onChange={handleChange}
                    />
                  </div>
                </div>
                <Input
                  name="venue"
                  placeholder="Salon / Mekan"
                  value={form.venue}
                  onChange={handleChange}
                  required
                />
                <Input
                  type="number"
                  name="pax"
                  placeholder="Kişi sayısı"
                  value={form.pax}
                  onChange={handleChange}
                  min={0}
                />
                <Textarea
                  name="menu"
                  placeholder="Menü detayları (örn. 3 course set menu)"
                  value={form.menu}
                  onChange={handleChange}
                  rows={3}
                />
                <Textarea
                  name="setup"
                  placeholder="Setup (örn. classroom, theatre)"
                  value={form.setup}
                  onChange={handleChange}
                  rows={2}
                />
                <Textarea
                  name="special_notes"
                  placeholder="Özel notlar (AV ihtiyaçları, dekorasyon, vb.)"
                  value={form.special_notes}
                  onChange={handleChange}
                  rows={3}
                />

                <Button type="submit" className="w-full bg-amber-600" disabled={saving}>
                  {saving ? 'Kaydediliyor...' : 'BEO Oluştur'}
                </Button>
              </form>
            </CardContent>
          </Card>

          {/* Preview */}
          <Card className="bg-gray-50">
            <CardHeader>
              <CardTitle>Önizleme</CardTitle>
            </CardHeader>
            <CardContent>
              {createdBeo ? (
                <div className="space-y-2 text-sm">
                  <div className="flex items-center justify-between">
                    <span className="font-semibold">BEO ID:</span>
                    <span>{createdBeo.id}</span>
                  </div>
                  <div className="flex items-center gap-2">
                    <FileText className="w-4 h-4 text-amber-600" />
                    <span className="font-semibold">{createdBeo.event_name}</span>
                  </div>
                  <div className="flex items-center gap-2 text-gray-700">
                    <Users className="w-4 h-4" />
                    <span>{createdBeo.client_name}</span>
                  </div>
                  <div className="flex items-center gap-2 text-gray-700">
                    <Calendar className="w-4 h-4" />
                    <span>
                      {createdBeo.date} {createdBeo.start_time && `• ${createdBeo.start_time}`}
                      {createdBeo.end_time && ` - ${createdBeo.end_time}`}
                    </span>
                  </div>
                  <div className="flex items-center gap-2 text-gray-700">
                    <Clock className="w-4 h-4" />
                    <span>
                      {createdBeo.venue} • {createdBeo.pax} pax
                    </span>
                  </div>
                  {createdBeo.menu && (
                    <div>
                      <div className="font-semibold mt-2">Menü</div>
                      <p className="whitespace-pre-line text-gray-700">{createdBeo.menu}</p>
                    </div>
                  )}
                  {createdBeo.setup && (
                    <div>
                      <div className="font-semibold mt-2">Setup</div>
                      <p className="whitespace-pre-line text-gray-700">{createdBeo.setup}</p>
                    </div>
                  )}
                  {createdBeo.special_notes && (
                    <div>
                      <div className="font-semibold mt-2">Notlar</div>
                      <p className="whitespace-pre-line text-gray-700">{createdBeo.special_notes}</p>
                    </div>
                  )}

                  <div className="mt-4 flex items-center text-green-600 gap-2 text-sm">
                    <CheckCircle className="w-4 h-4" />
                    <span>BEO kaydedildi.</span>
                  </div>

                  <div className="pt-2">
                    <Button
                      type="button"
                      variant="outline"
                      className="w-full"
                      onClick={() => window.print()}
                    >
                      <Download className="w-4 h-4 mr-2" />
                      PDF İndir (Yazdır → PDF olarak kaydet)
                    </Button>
                  </div>
                </div>
              ) : (
                <p className="text-gray-500 text-sm">
                  Formu doldurup kaydettikten sonra BEO detaylarını burada göreceksiniz.
                </p>
              )}
            </CardContent>
          </Card>
        </div>
      </div>
    </>
  );
};

export default FnbBeoGenerator;
