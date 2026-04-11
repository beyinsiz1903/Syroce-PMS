import React, { useState, useEffect } from 'react';
import { useNavigate } from 'react-router-dom';
import axios from 'axios';
import { toast } from 'sonner';
import { Card, CardContent, CardHeader, CardTitle } from '@/components/ui/card';
import { Button } from '@/components/ui/button';
import { Input } from '@/components/ui/input';
import { Label } from '@/components/ui/label';
import { Dialog, DialogContent, DialogHeader, DialogTitle, DialogTrigger } from '@/components/ui/dialog';
import { Sparkles, Calendar, Users, Home, Clock, DollarSign, Plus } from 'lucide-react';
import { useTranslation } from 'react-i18next';

const SpaWellness = () => {
  const { t } = useTranslation();
  const navigate = useNavigate();
  const [appointments, setAppointments] = useState([]);
  const [showCreateDialog, setShowCreateDialog] = useState(false);
  const [loading, setLoading] = useState(false);

  const [newAppointment, setNewAppointment] = useState({
    guest_id: '',
    treatment_id: 'massage_60',
    appointment_date: new Date().toISOString().slice(0, 16),
    duration_minutes: 60,
    price: 75,
    charge_to_room: false
  });

  useEffect(() => {
    loadAppointments();
  }, []);

  const loadAppointments = async () => {
    try {
      const response = await axios.get('/spa/appointments');
      setAppointments(response.data.appointments || []);
    } catch (error) {
      toast.error('Randevular yüklenemedi');
    }
  };

  const handleCreateAppointment = async (e) => {
    e.preventDefault();
    setLoading(true);
    try {
      await axios.post('/spa/appointments', newAppointment);
      toast.success('Spa randevusu oluşturuldu!');
      setShowCreateDialog(false);
      loadAppointments();
    } catch (error) {
      toast.error('Randevu oluşturulamadı');
    } finally {
      setLoading(false);
    }
  };

  const treatments = [
    { id: 'massage_60', name: 'Swedish Massage 60 min', duration: 60, price: 75 },
    { id: 'massage_90', name: 'Deep Tissue Massage 90 min', duration: 90, price: 110 },
    { id: 'facial_60', name: 'Hydrating Facial 60 min', duration: 60, price: 85 },
    { id: 'body_scrub', name: 'Body Scrub & Wrap', duration: 75, price: 95 },
    { id: 'couple_massage', name: 'Couples Massage 90 min', duration: 90, price: 180 },
    { id: 'hot_stone', name: 'Hot Stone Therapy', duration: 75, price: 100 }
  ];

  return (
    <div className="p-6">
      <div className="mb-8">
        <div className="flex items-center gap-3 mb-4">
          <Button 
            variant="outline" 
            size="icon"
            onClick={() => navigate('/')}
            className="hover:bg-purple-50"
          >
            <Home className="w-5 h-5" />
          </Button>
          <div>
            <h1 className="text-3xl font-bold text-gray-900">
              🧖 Spa & Wellness Yönetimi
            </h1>
            <p className="text-gray-600">
              Spa randevuları ve treatment yönetimi
            </p>
          </div>
        </div>

        <Dialog open={showCreateDialog} onOpenChange={setShowCreateDialog}>
          <DialogTrigger asChild>
            <Button size="lg" className="bg-purple-600 hover:bg-purple-700">
              <Plus className="w-5 h-5 mr-2" />
              Yeni Randevu
            </Button>
          </DialogTrigger>
          <DialogContent>
            <DialogHeader>
              <DialogTitle>Spa Randevusu Oluştur</DialogTitle>
            </DialogHeader>
            <form onSubmit={handleCreateAppointment} className="space-y-4 mt-4">
              <div>
                <Label>Treatment Seç</Label>
                <select
                  value={newAppointment.treatment_id}
                  onChange={(e) => {
                    const treatment = treatments.find(t => t.id === e.target.value);
                    setNewAppointment({
                      ...newAppointment,
                      treatment_id: e.target.value,
                      duration_minutes: treatment?.duration || 60,
                      price: treatment?.price || 75
                    });
                  }}
                  className="w-full px-3 py-2 border rounded-lg"
                >
                  {treatments.map(t => (
                    <option key={t.id} value={t.id}>
                      {t.name} - €{t.price}
                    </option>
                  ))}
                </select>
              </div>
              <div>
                <Label>Tarih ve Saat</Label>
                <Input
                  type="datetime-local"
                  value={newAppointment.appointment_date}
                  onChange={(e) => setNewAppointment({...newAppointment, appointment_date: e.target.value})}
                  required
                />
              </div>
              <div className="grid grid-cols-2 gap-4">
                <div>
                  <Label>Süre (dk)</Label>
                  <Input
                    type="number"
                    value={newAppointment.duration_minutes}
                    onChange={(e) => setNewAppointment({...newAppointment, duration_minutes: parseInt(e.target.value)})}
                    readOnly
                  />
                </div>
                <div>
                  <Label>Fiyat (€)</Label>
                  <Input
                    type="number"
                    value={newAppointment.price}
                    onChange={(e) => setNewAppointment({...newAppointment, price: parseFloat(e.target.value)})}
                  />
                </div>
              </div>
              <div className="flex items-center gap-2">
                <input
                  type="checkbox"
                  id="charge_to_room"
                  checked={newAppointment.charge_to_room}
                  onChange={(e) => setNewAppointment({...newAppointment, charge_to_room: e.target.checked})}
                  className="w-4 h-4"
                />
                <Label htmlFor="charge_to_room" className="cursor-pointer">
                  Oda hesabına ekle
                </Label>
              </div>
              <Button type="submit" className="w-full" disabled={loading}>
                {loading ? 'Oluşturuluyor...' : 'Randevu Oluştur'}
              </Button>
            </form>
          </DialogContent>
        </Dialog>
      </div>

      {/* Treatment Menu */}
      <div className="grid grid-cols-1 md:grid-cols-3 gap-4 mb-6">
        {treatments.map((treatment) => (
          <Card key={treatment.id} className="hover:shadow-lg transition-shadow">
            <CardContent className="pt-6">
              <Sparkles className="w-10 h-10 text-purple-600 mb-3" />
              <h3 className="text-lg font-bold mb-2">{treatment.name}</h3>
              <div className="flex items-center justify-between">
                <div className="flex items-center gap-2 text-sm text-gray-600">
                  <Clock className="w-4 h-4" />
                  <span>{treatment.duration} dk</span>
                </div>
                <div className="text-xl font-bold text-purple-600">
                  €{treatment.price}
                </div>
              </div>
            </CardContent>
          </Card>
        ))}
      </div>

      {/* Appointments List */}
      <Card>
        <CardHeader>
          <CardTitle>Bugünün Randevuları</CardTitle>
        </CardHeader>
        <CardContent>
          {appointments.length === 0 ? (
            <div className="text-center py-8">
              <Sparkles className="w-16 h-16 text-gray-400 mx-auto mb-4" />
              <p className="text-gray-600">Henüz randevu yok</p>
            </div>
          ) : (
            <div className="space-y-3">
              {appointments.map((apt) => (
                <div key={apt.id} className="flex items-center justify-between p-4 bg-purple-50 rounded-lg">
                  <div className="flex-1">
                    <p className="font-semibold">Treatment: {apt.treatment_id}</p>
                    <p className="text-sm text-gray-600">
                      {new Date(apt.appointment_date).toLocaleString('tr-TR')}
                    </p>
                  </div>
                  <div className="text-right">
                    <p className="text-lg font-bold text-purple-600">€{apt.price}</p>
                    <p className="text-xs text-gray-500">{apt.duration_minutes} dk</p>
                  </div>
                </div>
              ))}
            </div>
          )}
        </CardContent>
      </Card>

      {/* Statistics */}
      <div className="grid grid-cols-4 gap-4 mt-6">
        <Card>
          <CardContent className="pt-6 text-center">
            <Calendar className="w-8 h-8 text-purple-600 mx-auto mb-2" />
            <p className="text-2xl font-bold">{appointments.length}</p>
            <p className="text-sm text-gray-500">Bugün Randevu</p>
          </CardContent>
        </Card>
        <Card>
          <CardContent className="pt-6 text-center">
            <DollarSign className="w-8 h-8 text-green-600 mx-auto mb-2" />
            <p className="text-2xl font-bold">
              €{appointments.reduce((sum, a) => sum + (a.price || 0), 0)}
            </p>
            <p className="text-sm text-gray-500">Toplam Gelir</p>
          </CardContent>
        </Card>
        <Card>
          <CardContent className="pt-6 text-center">
            <Users className="w-8 h-8 text-blue-600 mx-auto mb-2" />
            <p className="text-2xl font-bold">{appointments.filter(a => a.status === 'confirmed').length}</p>
            <p className="text-sm text-gray-500">Onaylı</p>
          </CardContent>
        </Card>
        <Card>
          <CardContent className="pt-6 text-center">
            <Clock className="w-8 h-8 text-orange-600 mx-auto mb-2" />
            <p className="text-2xl font-bold">
              {appointments.reduce((sum, a) => sum + (a.duration_minutes || 0), 0)} dk
            </p>
            <p className="text-sm text-gray-500">Toplam Süre</p>
          </CardContent>
        </Card>
      </div>
    </div>
  );
};

export default SpaWellness;