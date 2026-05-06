import React, { useState, useEffect } from 'react';
import axios from 'axios';

import { Card, CardContent } from '@/components/ui/card';
import { Button } from '@/components/ui/button';
import { Badge } from '@/components/ui/badge';
import { PageHeader } from '@/components/ui/page-header';
import { KpiCard } from '@/components/ui/kpi-card';
import { LogOut, AlertCircle, Wallet, Clock, RefreshCw } from 'lucide-react';
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

const DepartureList = ({ user, tenant, onLogout }) => {
  const [departures, setDepartures] = useState([]);
  const [loading, setLoading] = useState(false);
  const [busyId, setBusyId] = useState(null);

  const load = async () => {
    setLoading(true);
    try {
      const today = localISODate(new Date());
      const res = await axios.get(
        `/pms/bookings?status=checked_in&check_out_from=${today}&check_out_to=${today}&limit=300`
      );
      const list = res.data?.bookings || res.data?.items || res.data || [];
      setDepartures(Array.isArray(list) ? list : []);
    } catch (e) {
      toast.error('Çıkış listesi yüklenemedi');
      setDepartures([]);
    } finally {
      setLoading(false);
    }
  };

  useEffect(() => {
    load();
  }, []);

  const checkout = async (booking, force = false) => {
    if (busyId) return;
    if (!force && (booking.balance || 0) > 0) {
      const ok = await confirmDialog({ message: `Folio bakiyesi ${fmtTRY(booking.balance)} pozitif. Yine de zorla çıkış yapılsın mı?`, variant: 'danger' });
      if (!ok) return;
      force = true;
    } else if (!force) {
      const ok = await confirmDialog({ message: `${booking.guest_name || booking.id.slice(0, 8)} için çıkış yapılsın mı?`, variant: 'danger' });
      if (!ok) return;
    }
    setBusyId(booking.id);
    try {
      await axios.post('/api/pms-core/checkout', {
        booking_id: booking.id,
        force,
      });
      toast.success('Çıkış tamamlandı');
      load();
    } catch (e) {
      const detail = e.response?.data?.detail;
      const msg =
        typeof detail === 'string'
          ? detail
          : detail?.message || detail?.error || 'Çıkış başarısız';
      toast.error(msg);
    } finally {
      setBusyId(null);
    }
  };

  const totalBalance = departures.reduce((s, b) => s + (b.balance || 0), 0);
  const withDebt = departures.filter((b) => (b.balance || 0) > 0).length;

  return (
    <>
      <div className="p-4 md:p-6 space-y-5 max-w-6xl mx-auto">
        <PageHeader
          icon={LogOut}
          title="Bugünün Çıkışları"
          subtitle="Bugün check-out yapacak misafirler — folio bakiyesi ve hızlı çıkış"
          actions={
            <Button variant="outline" size="sm" onClick={load} disabled={loading}>
              <RefreshCw className="w-4 h-4 mr-1.5" /> Yenile
            </Button>
          }
        />

        <div className="grid grid-cols-1 sm:grid-cols-3 gap-3">
          <KpiCard icon={LogOut} label="Toplam Çıkış" value={departures.length} intent="info" />
          <KpiCard icon={AlertCircle} label="Bakiyeli Çıkış" value={withDebt} intent="warning" highlight={withDebt > 0} />
          <KpiCard icon={Wallet} label="Toplam Açık Bakiye" value={fmtTRY(totalBalance)} intent="success" />
        </div>

        <div className="space-y-3">
          {loading ? (
            <div className="text-center py-12">
              <div className="animate-spin rounded-full h-10 w-10 border-b-2 border-blue-600 mx-auto" />
            </div>
          ) : departures.length === 0 ? (
            <Card>
              <CardContent className="pt-12 pb-12 text-center text-gray-500">
                <LogOut className="w-12 h-12 mx-auto mb-3 text-gray-400" />
                Bugün çıkış yok.
              </CardContent>
            </Card>
          ) : (
            departures.map((b) => {
              const debt = (b.balance || 0) > 0;
              return (
                <Card
                  key={b.id}
                  className={`border-l-4 ${debt ? 'border-amber-500 bg-amber-50' : 'border-blue-500'}`}
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
                          {debt && <Badge className="bg-amber-600">Bakiyeli</Badge>}
                          {b.late_checkout && (
                            <Badge className="bg-amber-600">
                              <Clock className="w-3 h-3 mr-1" /> Geç Çıkış
                            </Badge>
                          )}
                        </div>
                        <div className="grid grid-cols-3 gap-4 text-sm">
                          <div>
                            <p className="text-gray-500">Oda</p>
                            <p className="font-semibold">{b.room_number || '—'}</p>
                          </div>
                          <div>
                            <p className="text-gray-500">Çıkış Saati</p>
                            <p className="font-semibold">
                              {b.check_out_time || '12:00'}
                            </p>
                          </div>
                          <div>
                            <p className="text-gray-500">Folio Bakiyesi</p>
                            <p
                              className={`font-semibold ${
                                debt ? 'text-amber-700' : 'text-emerald-700'
                              }`}
                            >
                              {fmtTRY(b.balance || 0)}
                            </p>
                          </div>
                        </div>
                      </div>
                      <div className="ml-4 flex flex-col gap-2 items-end">
                        <Button
                          size="sm"
                          disabled={busyId === b.id}
                          onClick={() => checkout(b, false)}
                        >
                          <LogOut className="w-4 h-4 mr-1" />
                          {busyId === b.id ? 'İşleniyor…' : 'Çıkış Yap'}
                        </Button>
                        {debt && (
                          <Button
                            size="sm"
                            variant="outline"
                            disabled={busyId === b.id}
                            onClick={() => checkout(b, true)}
                          >
                            Zorla Çıkış
                          </Button>
                        )}
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

export default DepartureList;
