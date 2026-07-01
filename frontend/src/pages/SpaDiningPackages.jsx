import React, { useState, useEffect } from 'react';
import { useTranslation } from 'react-i18next';
import axios from 'axios';
import { toast } from 'sonner';
import { Sparkles, Utensils, CalendarPlus, Loader2, Clock, CheckCircle } from 'lucide-react';
import { Card, CardHeader, CardTitle, CardContent, CardDescription, CardFooter } from '@/components/ui/card';
import { Button } from '@/components/ui/button';
import { Input } from '@/components/ui/input';
import { Label } from '@/components/ui/label';
import { Switch } from '@/components/ui/switch';
import MaybeLayout from '@/components/MaybeLayout';

const SpaDiningPackages = ({ user, tenant, onLogout, embedded = false }) => {
  const { t } = useTranslation();
  const [loading, setLoading] = useState(false);
  const [packages, setPackages] = useState([]);
  const [bookings, setBookings] = useState([]);
  const [submitting, setSubmitting] = useState(false);

  // Form state
  const [formData, setFormData] = useState({
    package_id: '',
    spa_therapist_id: 'auto',
    spa_room_id: 'auto',
    dining_outlet_id: 'main_restaurant',
    dining_table_number: '1',
    starts_at: new Date().toISOString().slice(0, 16),
    guest_name: '',
    guest_phone: '',
    reservation_id: '',
    charge_to_room: false
  });

  useEffect(() => {
    fetchData();
  }, []);

  const fetchData = async () => {
    try {
      setLoading(true);
      const [pkgRes, bkRes] = await Promise.all([
        axios.get('/spa-dining/packages'),
        axios.get('/spa-dining/bookings')
      ]);
      setPackages(pkgRes.data.packages || []);
      setBookings(pkgRes.data.bookings || bkRes.data.bookings || []);
      if (pkgRes.data.packages?.length > 0) {
        setFormData(prev => ({ ...prev, package_id: pkgRes.data.packages[0].id }));
      }
    } catch (err) {
      console.error(err);
      toast.error('Paket verileri yüklenemedi.');
    } finally {
      setLoading(false);
    }
  };

  const handleInputChange = (e) => {
    const { name, value, type, checked } = e.target;
    setFormData(prev => ({
      ...prev,
      [name]: type === 'checkbox' ? checked : value
    }));
  };

  const handleSubmit = async (e) => {
    e.preventDefault();
    if (!formData.guest_name) {
      toast.error('Misafir adı zorunludur.');
      return;
    }

    try {
      setSubmitting(true);
      const payload = {
        ...formData,
        starts_at: new Date(formData.starts_at).toISOString()
      };
      await axios.post('/spa-dining/bookings', payload);
      toast.success('Paket rezervasyonu başarıyla oluşturuldu!');
      
      // Reset form but keep package and date
      setFormData(prev => ({
        ...prev,
        guest_name: '',
        guest_phone: '',
        reservation_id: '',
        charge_to_room: false
      }));
      fetchData();
    } catch (err) {
      console.error(err);
      toast.error(err.response?.data?.detail || 'Rezervasyon oluşturulamadı. Müsaitlik durumunu kontrol edin.');
    } finally {
      setSubmitting(false);
    }
  };

  return (
    <MaybeLayout embedded={embedded} user={user} tenant={tenant} onLogout={onLogout} currentModule="spa_dining_packages">
      <div className="max-w-7xl mx-auto px-4 py-6 space-y-6">
        <div className="flex flex-col md:flex-row md:items-center justify-between gap-4">
          <div>
            <h1 className="text-2xl font-bold text-gray-900 flex items-center gap-2">
              <Sparkles className="w-6 h-6 text-pink-600" />
              SPA & Restoran Paketleri
            </h1>
            <p className="text-sm text-gray-500 mt-1">Lüks dinlenme ve gurme yemek deneyimlerini tek kalemde yönetin.</p>
          </div>
          <Button variant="outline" onClick={fetchData} disabled={loading}>
            Yenile
          </Button>
        </div>

        <div className="grid grid-cols-1 lg:grid-cols-3 gap-6">
          {/* New Booking Form */}
          <div className="lg:col-span-1">
            <Card>
              <CardHeader>
                <CardTitle className="text-lg flex items-center gap-2">
                  <CalendarPlus className="w-5 h-5 text-indigo-600" /> Yeni Paket Rezervasyonu
                </CardTitle>
              </CardHeader>
              <form onSubmit={handleSubmit}>
                <CardContent className="space-y-4">
                  <div className="space-y-2">
                    <Label>Paket Seçimi</Label>
                    <select 
                      name="package_id" 
                      value={formData.package_id} 
                      onChange={handleInputChange}
                      className="flex h-10 w-full items-center justify-between rounded-md border border-input bg-background px-3 py-2 text-sm ring-offset-background placeholder:text-muted-foreground focus:outline-none focus:ring-2 focus:ring-ring focus:ring-offset-2 disabled:cursor-not-allowed disabled:opacity-50"
                    >
                      {packages.map(pkg => (
                        <option key={pkg.id} value={pkg.id}>{pkg.name} ({pkg.price} ₺)</option>
                      ))}
                    </select>
                  </div>
                  
                  <div className="space-y-2">
                    <Label>Misafir Adı</Label>
                    <Input name="guest_name" value={formData.guest_name} onChange={handleInputChange} required placeholder="Örn: Jane Doe" />
                  </div>

                  <div className="space-y-2">
                    <Label>Oda / Rezervasyon No (İsteğe Bağlı)</Label>
                    <Input name="reservation_id" value={formData.reservation_id} onChange={handleInputChange} placeholder="Örn: R-1024" />
                  </div>

                  <div className="space-y-2">
                    <Label>Başlangıç Zamanı (SPA)</Label>
                    <Input type="datetime-local" name="starts_at" value={formData.starts_at} onChange={handleInputChange} required />
                  </div>

                  <div className="flex items-center justify-between pt-2 border-t mt-4">
                    <Label className="text-sm font-medium cursor-pointer" htmlFor="charge_to_room">Ücreti Odaya Yansıt (Folyo)</Label>
                    <Switch id="charge_to_room" name="charge_to_room" checked={formData.charge_to_room} onCheckedChange={(checked) => handleInputChange({ target: { name: 'charge_to_room', type: 'checkbox', checked }})} />
                  </div>
                </CardContent>
                <CardFooter>
                  <Button type="submit" className="w-full bg-indigo-600 hover:bg-indigo-700 text-white" disabled={submitting || packages.length === 0}>
                    {submitting ? <Loader2 className="w-4 h-4 animate-spin mr-2" /> : null}
                    Rezervasyonu Tamamla
                  </Button>
                </CardFooter>
              </form>
            </Card>
          </div>

          {/* Bookings & Packages Info */}
          <div className="lg:col-span-2 space-y-6">
            <Card>
              <CardHeader>
                <CardTitle className="text-lg flex items-center gap-2">
                  <Utensils className="w-5 h-5 text-gray-500" /> Yaklaşan Paket Rezervasyonları
                </CardTitle>
              </CardHeader>
              <CardContent>
                {loading ? (
                  <div className="flex justify-center p-6"><Loader2 className="w-6 h-6 animate-spin text-gray-400" /></div>
                ) : bookings.length === 0 ? (
                  <div className="text-center py-8 bg-gray-50 rounded-lg border border-dashed border-gray-200">
                    <CheckCircle className="w-10 h-10 text-gray-300 mx-auto mb-3" />
                    <h3 className="text-sm font-medium text-gray-900">Kayıt bulunamadı</h3>
                  </div>
                ) : (
                  <div className="space-y-3">
                    {bookings.map((booking, idx) => (
                      <div key={idx} className="p-4 border rounded-xl bg-white hover:shadow-md transition-shadow">
                        <div className="flex justify-between items-start">
                          <div>
                            <h4 className="font-semibold text-gray-900">{booking.guest_name}</h4>
                            <p className="text-sm text-indigo-600 font-medium">{booking.package_name}</p>
                          </div>
                          <span className={`px-2 py-1 text-xs font-semibold rounded-full ${booking.status === 'confirmed' ? 'bg-green-100 text-green-700' : 'bg-gray-100 text-gray-700'}`}>
                            {booking.status === 'confirmed' ? 'Onaylandı' : booking.status}
                          </span>
                        </div>
                        <div className="mt-4 grid grid-cols-2 gap-4 text-sm text-gray-600">
                          <div className="flex items-center gap-2">
                            <Clock className="w-4 h-4 text-indigo-500" /> SPA: {new Date(booking.spa_start).toLocaleTimeString([], {hour: '2-digit', minute:'2-digit'})}
                          </div>
                          <div className="flex items-center gap-2">
                            <Utensils className="w-4 h-4 text-amber-500" /> Restoran: {new Date(booking.dining_start).toLocaleTimeString([], {hour: '2-digit', minute:'2-digit'})}
                          </div>
                        </div>
                      </div>
                    ))}
                  </div>
                )}
              </CardContent>
            </Card>

            <div className="grid grid-cols-1 md:grid-cols-2 gap-4">
              {packages.map(pkg => (
                <div key={pkg.id} className="border rounded-xl p-4 bg-gradient-to-br from-indigo-50 to-pink-50 relative overflow-hidden">
                  <h4 className="font-bold text-gray-900 mb-1">{pkg.name}</h4>
                  <p className="text-xs text-gray-600 mb-3 line-clamp-2">{pkg.description}</p>
                  <div className="text-lg font-extrabold text-indigo-700">{pkg.price} ₺</div>
                  <Sparkles className="w-16 h-16 text-white absolute -bottom-4 -right-4 opacity-50" />
                </div>
              ))}
            </div>
          </div>
        </div>
      </div>
    </MaybeLayout>
  );
};

export default SpaDiningPackages;
