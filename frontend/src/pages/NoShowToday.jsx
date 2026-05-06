import React, { useState, useEffect } from 'react';
import { useNavigate } from 'react-router-dom';
import axios from 'axios';

import { Card, CardContent } from '@/components/ui/card';
import { Button } from '@/components/ui/button';
import { Badge } from '@/components/ui/badge';
import {
  Home,
  AlertTriangle,
  UserX,
  Calendar,
} from 'lucide-react';
import { toast } from 'sonner';

import { confirmDialog } from '@/lib/dialogs';
const localISODate = (d) => {
  const y = d.getFullYear();
  const m = String(d.getMonth() + 1).padStart(2, '0');
  const day = String(d.getDate()).padStart(2, '0');
  return `${y}-${m}-${day}`;
};

const fmtTRY = (v) =>
  new Intl.NumberFormat('tr-TR', { style: 'currency', currency: 'TRY' }).format(Number(v || 0));

/**
 * NoShowToday — bugün varış olan ancak henüz check-in yapmamış
 * (status confirmed/guaranteed/pending) rezervasyonları listeler ve tek
 * tıkla "no-show" işaretler. Atomic backend (/api/pms-core/no-show)
 * üzerinden çalışır; oda boşaltma ve audit otomatik.
 */
const NoShowToday = ({ user, tenant, onLogout }) => {
  const navigate = useNavigate();
  const [items, setItems] = useState([]);
  const [loading, setLoading] = useState(false);
  const [busyId, setBusyId] = useState(null);

  const load = async () => {
    setLoading(true);
    try {
      const today = localISODate(new Date());
      const res = await axios.get(
        `/pms/arrivals?start_date=${today}&end_date=${today}&limit=500`
      );
      const list = res.data?.bookings || [];
      // Bekleyen/onaylı/garantili olanlar — checked_in ve cancelled hariç
      const pending = list.filter((b) =>
        ['confirmed', 'guaranteed', 'pending'].includes((b.status || '').toLowerCase())
      );
      setItems(pending);
    } catch (e) {
      toast.error('Liste yüklenemedi');
      setItems([]);
    } finally {
      setLoading(false);
    }
  };

  useEffect(() => {
    load();
  }, []);

  const markNoShow = async (booking) => {
    if (busyId) return;
    if (
      !await confirmDialog({ message: `${booking.guest_name || booking.id.slice(0, 8)} no-show olarak işaretlensin mi?\n(Oda boşaltılacak, audit'e düşecek.)`, variant: 'danger' })
    )
      return;
    setBusyId(booking.id);
    try {
      await axios.post('/api/pms-core/no-show', { booking_id: booking.id });
      toast.success('No-show işaretlendi');
      load();
    } catch (e) {
      const detail = e.response?.data?.detail;
      const msg =
        typeof detail === 'string'
          ? detail
          : detail?.message || detail?.error || 'No-show işaretlenemedi';
      toast.error(msg);
    } finally {
      setBusyId(null);
    }
  };

  const totalLoss = items.reduce((s, b) => s + (b.total_amount || 0), 0);

  return (
    <>
      <div className="p-6">
        <div className="mb-8 flex items-center justify-between">
          <div className="flex items-center gap-3">
            <Button variant="outline" size="icon" onClick={() => navigate('/')}>
              <Home className="w-5 h-5" />
            </Button>
            <div>
              <h1 className="text-3xl font-bold text-gray-900">Bekleyen / No-Show Adayları</h1>
              <p className="text-gray-600">
                Bugün gelmesi gereken ama henüz check-in yapmamış misafirler — manuel no-show
                işaretleyin (gece denetimi otomatik tarar).
              </p>
            </div>
          </div>
          <Button onClick={load} disabled={loading}>
            Yenile
          </Button>
        </div>

        <div className="grid grid-cols-3 gap-4 mb-6">
          <Card>
            <CardContent className="pt-6 text-center">
              <Calendar className="w-8 h-8 text-blue-600 mx-auto mb-2" />
              <p className="text-2xl font-bold">{items.length}</p>
              <p className="text-sm text-gray-500">Bekleyen Varış</p>
            </CardContent>
          </Card>
          <Card>
            <CardContent className="pt-6 text-center">
              <AlertTriangle className="w-8 h-8 text-amber-600 mx-auto mb-2" />
              <p className="text-2xl font-bold">
                {items.filter((b) => (b.status || '').toLowerCase() === 'guaranteed').length}
              </p>
              <p className="text-sm text-gray-500">Garantili Bekleyen</p>
            </CardContent>
          </Card>
          <Card>
            <CardContent className="pt-6 text-center">
              <UserX className="w-8 h-8 text-red-600 mx-auto mb-2" />
              <p className="text-2xl font-bold">{fmtTRY(totalLoss)}</p>
              <p className="text-sm text-gray-500">Potansiyel Kayıp</p>
            </CardContent>
          </Card>
        </div>

        <div className="space-y-3">
          {loading ? (
            <div className="text-center py-12">
              <div className="animate-spin rounded-full h-10 w-10 border-b-2 border-blue-600 mx-auto" />
            </div>
          ) : items.length === 0 ? (
            <Card>
              <CardContent className="pt-12 pb-12 text-center text-gray-500">
                <UserX className="w-12 h-12 mx-auto mb-3 text-gray-400" />
                Bugün bekleyen varış yok — tüm misafirler check-in yapmış görünüyor.
              </CardContent>
            </Card>
          ) : (
            items.map((b) => {
              const status = (b.status || '').toLowerCase();
              const guaranteed = status === 'guaranteed';
              return (
                <Card
                  key={b.id}
                  className={`border-l-4 ${guaranteed ? 'border-amber-500 bg-amber-50' : 'border-gray-300'}`}
                >
                  <CardContent className="pt-4">
                    <div className="flex items-start justify-between">
                      <div className="flex-1">
                        <div className="flex items-center gap-2 mb-2">
                          <h3 className="text-lg font-bold">
                            #{(b.id || '').substring(0, 8).toUpperCase()}
                          </h3>
                          {b.guest_name && (
                            <span className="text-gray-700">{b.guest_name}</span>
                          )}
                          <Badge
                            className={
                              guaranteed
                                ? 'bg-amber-600'
                                : status === 'confirmed'
                                  ? 'bg-blue-600'
                                  : 'bg-gray-500'
                            }
                          >
                            {status}
                          </Badge>
                        </div>
                        <div className="grid grid-cols-4 gap-4 text-sm">
                          <div>
                            <p className="text-gray-500">Oda</p>
                            <p className="font-semibold">{b.room_number || '—'}</p>
                          </div>
                          <div>
                            <p className="text-gray-500">Beklenen</p>
                            <p className="font-semibold">
                              {b.estimated_arrival_time || '14:00'}
                            </p>
                          </div>
                          <div>
                            <p className="text-gray-500">Adet</p>
                            <p className="font-semibold">
                              {b.adults}/{b.children}
                            </p>
                          </div>
                          <div>
                            <p className="text-gray-500">Tutar</p>
                            <p className="font-semibold">{fmtTRY(b.total_amount)}</p>
                          </div>
                        </div>
                      </div>
                      <div className="ml-4">
                        <Button
                          size="sm"
                          variant="destructive"
                          disabled={busyId === b.id}
                          onClick={() => markNoShow(b)}
                        >
                          <UserX className="w-4 h-4 mr-1" />
                          {busyId === b.id ? 'İşleniyor…' : 'No-Show'}
                        </Button>
                      </div>
                    </div>
                  </CardContent>
                </Card>
              );
            })
          )}
        </div>
      </div>
    </>
  );
};

export default NoShowToday;
