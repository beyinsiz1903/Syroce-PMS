import React, { useState, useEffect } from 'react';
import { useNavigate } from 'react-router-dom';
import axios from 'axios';
import { toast } from 'sonner';
import { Card, CardContent, CardHeader, CardTitle } from '@/components/ui/card';
import { Button } from '@/components/ui/button';
import { Input } from '@/components/ui/input';
import { Label } from '@/components/ui/label';
import { Textarea } from '@/components/ui/textarea';
import { Dialog, DialogContent, DialogHeader, DialogTitle, DialogTrigger } from '@/components/ui/dialog';
import { Calendar, Users, Home, Clock, MapPin, Plus, Utensils, DollarSign } from 'lucide-react';
import { useTranslation } from 'react-i18next';

const MeetingEvents = () => {
  const { t } = useTranslation();
  const navigate = useNavigate();
  const [events, setEvents] = useState([]);
  const [showCreateDialog, setShowCreateDialog] = useState(false);
  const [loading, setLoading] = useState(false);

  const [newEvent, setNewEvent] = useState({
    event_name: '',
    organization: '',
    contact_name: '',
    contact_email: '',
    meeting_room_id: 'room_1',
    event_date: new Date().toISOString().split('T')[0],
    start_time: '09:00',
    end_time: '17:00',
    setup_type: 'theater',
    expected_attendees: 50,
    catering_required: false,
    total_cost: 500
  });

  useEffect(() => {
    loadEvents();
  }, []);

  const loadEvents = async () => {
    try {
      const response = await axios.get('/events/bookings');
      setEvents(response.data.events || []);
    } catch (error) {
      toast.error('Etkinlikler yüklenemedi');
    }
  };

  const handleCreateEvent = async (e) => {
    e.preventDefault();
    setLoading(true);
    try {
      await axios.post('/events/bookings', newEvent);
      toast.success('Etkinlik rezervasyonu oluşturuldu!');
      setShowCreateDialog(false);
      loadEvents();
    } catch (error) {
      toast.error('Etkinlik oluşturulamadı');
    } finally {
      setLoading(false);
    }
  };

  return (
    <div className="p-6">
      <div className="mb-8">
        <div className="flex items-center justify-between">
          <div className="flex items-center gap-3">
            <Button 
              variant="outline" 
              size="icon"
              onClick={() => navigate('/')}
              className="hover:bg-orange-50"
            >
              <Home className="w-5 h-5" />
            </Button>
            <div>
              <h1 className="text-3xl font-bold text-gray-900">
                🏛️ {t('dashboard.meetingEvents')}
              </h1>
              <p className="text-gray-600">
                Toplantı odaları ve etkinlik yönetimi
              </p>
            </div>
          </div>

          <Dialog open={showCreateDialog} onOpenChange={setShowCreateDialog}>
            <DialogTrigger asChild>
              <Button size="lg" className="bg-orange-600 hover:bg-orange-700">
                <Plus className="w-5 h-5 mr-2" />
                Yeni Etkinlik
              </Button>
            </DialogTrigger>
            <DialogContent className="max-w-2xl">
              <DialogHeader>
                <DialogTitle>Etkinlik Rezervasyonu Oluştur</DialogTitle>
              </DialogHeader>
              <form onSubmit={handleCreateEvent} className="space-y-4 mt-4">
                <div className="grid grid-cols-2 gap-4">
                  <div>
                    <Label>Etkinlik Adı *</Label>
                    <Input
                      value={newEvent.event_name}
                      onChange={(e) => setNewEvent({...newEvent, event_name: e.target.value})}
                      required
                      placeholder="Yıllık Konferans 2025"
                    />
                  </div>
                  <div>
                    <Label>Organizasyon *</Label>
                    <Input
                      value={newEvent.organization}
                      onChange={(e) => setNewEvent({...newEvent, organization: e.target.value})}
                      required
                      placeholder="ABC Şirketi"
                    />
                  </div>
                  <div>
                    <Label>İlgili Kişi *</Label>
                    <Input
                      value={newEvent.contact_name}
                      onChange={(e) => setNewEvent({...newEvent, contact_name: e.target.value})}
                      required
                    />
                  </div>
                  <div>
                    <Label>E-posta *</Label>
                    <Input
                      type="email"
                      value={newEvent.contact_email}
                      onChange={(e) => setNewEvent({...newEvent, contact_email: e.target.value})}
                      required
                    />
                  </div>
                  <div>
                    <Label>Tarih *</Label>
                    <Input
                      type="date"
                      value={newEvent.event_date}
                      onChange={(e) => setNewEvent({...newEvent, event_date: e.target.value})}
                      required
                    />
                  </div>
                  <div>
                    <Label>Katılımcı Sayısı *</Label>
                    <Input
                      type="number"
                      value={newEvent.expected_attendees}
                      onChange={(e) => setNewEvent({...newEvent, expected_attendees: parseInt(e.target.value)})}
                      required
                    />
                  </div>
                  <div>
                    <Label>Başlangıç</Label>
                    <Input
                      type="time"
                      value={newEvent.start_time}
                      onChange={(e) => setNewEvent({...newEvent, start_time: e.target.value})}
                    />
                  </div>
                  <div>
                    <Label>Bitiş</Label>
                    <Input
                      type="time"
                      value={newEvent.end_time}
                      onChange={(e) => setNewEvent({...newEvent, end_time: e.target.value})}
                    />
                  </div>
                </div>
                <div className="flex items-center gap-2">
                  <input
                    type="checkbox"
                    id="catering"
                    checked={newEvent.catering_required}
                    onChange={(e) => setNewEvent({...newEvent, catering_required: e.target.checked})}
                    className="w-4 h-4"
                  />
                  <Label htmlFor="catering" className="cursor-pointer">
                    Catering gerekli
                  </Label>
                </div>
                <Button type="submit" className="w-full" disabled={loading}>
                  {loading ? 'Oluşturuluyor...' : 'Etkinlik Oluştur'}
                </Button>
              </form>
            </DialogContent>
          </Dialog>
        </div>
      </div>

      {/* Events List */}
      <div className="grid grid-cols-1 gap-4">
        {events.length === 0 ? (
          <Card>
            <CardContent className="pt-12 pb-12 text-center">
              <Calendar className="w-16 h-16 text-gray-400 mx-auto mb-4" />
              <p className="text-gray-600">Henüz etkinlik yok</p>
            </CardContent>
          </Card>
        ) : (
          events.map((event) => (
            <Card key={event.id}>
              <CardContent className="pt-6">
                <div className="flex items-start justify-between">
                  <div className="flex-1">
                    <h3 className="text-xl font-bold mb-2">{event.event_name}</h3>
                    <p className="text-gray-600 mb-3">{event.organization}</p>
                    <div className="grid grid-cols-3 gap-4">
                      <div className="flex items-center gap-2 text-sm text-gray-600">
                        <Calendar className="w-4 h-4" />
                        <span>{event.event_date}</span>
                      </div>
                      <div className="flex items-center gap-2 text-sm text-gray-600">
                        <Clock className="w-4 h-4" />
                        <span>{event.start_time} - {event.end_time}</span>
                      </div>
                      <div className="flex items-center gap-2 text-sm text-gray-600">
                        <Users className="w-4 h-4" />
                        <span>{event.expected_attendees} kişi</span>
                      </div>
                    </div>
                  </div>
                  <div className="text-right ml-4">
                    <p className="text-2xl font-bold text-orange-600">€{event.total_cost}</p>
                    {event.catering_required && (
                      <div className="flex items-center gap-1 text-sm text-green-600 mt-2">
                        <Utensils className="w-4 h-4" />
                        <span>Catering</span>
                      </div>
                    )}
                  </div>
                </div>
              </CardContent>
            </Card>
          ))
        )}
      </div>

      {/* Statistics */}
      <div className="grid grid-cols-4 gap-4 mt-6">
        <Card>
          <CardContent className="pt-6 text-center">
            <Calendar className="w-8 h-8 text-orange-600 mx-auto mb-2" />
            <p className="text-2xl font-bold">{events.length}</p>
            <p className="text-sm text-gray-500">Toplam Etkinlik</p>
          </CardContent>
        </Card>
        <Card>
          <CardContent className="pt-6 text-center">
            <Users className="w-8 h-8 text-blue-600 mx-auto mb-2" />
            <p className="text-2xl font-bold">
              {events.reduce((sum, e) => sum + (e.expected_attendees || 0), 0)}
            </p>
            <p className="text-sm text-gray-500">Toplam Katılımcı</p>
          </CardContent>
        </Card>
        <Card>
          <CardContent className="pt-6 text-center">
            <DollarSign className="w-8 h-8 text-green-600 mx-auto mb-2" />
            <p className="text-2xl font-bold">
              €{events.reduce((sum, e) => sum + (e.total_cost || 0), 0)}
            </p>
            <p className="text-sm text-gray-500">Toplam Gelir</p>
          </CardContent>
        </Card>
        <Card>
          <CardContent className="pt-6 text-center">
            <Utensils className="w-8 h-8 text-purple-600 mx-auto mb-2" />
            <p className="text-2xl font-bold">
              {events.filter(e => e.catering_required).length}
            </p>
            <p className="text-sm text-gray-500">Catering</p>
          </CardContent>
        </Card>
      </div>
    </div>
  );
};

export default MeetingEvents;