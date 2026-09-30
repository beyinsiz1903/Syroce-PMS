import React, { useState, useEffect, useCallback } from 'react';
import axios from 'axios';
import { toast } from 'sonner';
import { Card, CardContent, CardHeader, CardTitle } from './ui/card';
import { Button } from './ui/button';
import { Badge } from './ui/badge';
import { Users, RefreshCw, CheckCircle, Clock, ArrowRightLeft, ReceiptText, CalendarDays, Plus, XCircle } from 'lucide-react';
import { confirmDialog } from '@/lib/dialogs';
import { cachedTenantCurrency, formatCurrency } from '@/lib/currency';

const STATUS_LABELS = {
  available: 'Müsait',
  occupied: 'Dolu',
  reserved: 'Rezerve',
  dirty: 'Temizlenecek',
};

const POSTableManagement = ({ outletId = 'main_restaurant' }) => {
  const [tables, setTables] = useState([]);
  const [statusCounts, setStatusCounts] = useState({});
  const [loading, setLoading] = useState(true);
  const [updating, setUpdating] = useState(null);
  const [notProvisioned, setNotProvisioned] = useState(false);
  const [transferTargets, setTransferTargets] = useState({});
  const [reservations, setReservations] = useState([]);
  const [reservationFormOpen, setReservationFormOpen] = useState(false);
  const [savingReservation, setSavingReservation] = useState(false);
  const [reservationForm, setReservationForm] = useState({
    guest_name: '',
    pax: 2,
    res_date: new Date().toLocaleDateString('sv-SE'),
    res_time: '19:00',
    table_id: '',
    notes: '',
  });

  const loadTables = useCallback(async () => {
    try {
      setLoading(true);
      setNotProvisioned(false);
      const response = await axios.get(`/pos/table-layout/${outletId}`);
      setTables(response.data.tables || []);
      setStatusCounts({
        available: response.data.available || 0,
        occupied: response.data.occupied || 0,
        reserved: response.data.reserved || 0,
      });
    } catch (error) {
      // POS masa yönetimi backend'de henüz provizyonlanmamış olabilir
      // (endpoint yok → 404). Bu durumda sessiz boş duruma düş; toast
      // sadece gerçek hatalarda (auth, 5xx, network) çıkar.
      if (error?.response?.status === 404) {
        setTables([]);
        setStatusCounts({});
        setNotProvisioned(true);
      } else {
        console.error('Masalar yüklenemedi:', error);
        toast.error('Masalar yüklenemedi');
      }
    } finally {
      setLoading(false);
    }
  }, [outletId]);

  const loadReservations = useCallback(async () => {
    try {
      const response = await axios.get('/pos/reservations', { params: { outlet_id: outletId } });
      setReservations(Array.isArray(response.data) ? response.data : []);
    } catch (error) {
      if (![403, 404].includes(error?.response?.status)) {
        console.error('Masa rezervasyonları yüklenemedi:', error);
        toast.error('Masa rezervasyonları yüklenemedi');
      }
      setReservations([]);
    }
  }, [outletId]);

  useEffect(() => {
    loadTables();
    loadReservations();
  }, [loadReservations, loadTables]);

  const createReservation = async () => {
    if (!reservationForm.guest_name.trim() || !reservationForm.table_id || !reservationForm.res_date || !reservationForm.res_time) {
      toast.error('Misafir, masa, tarih ve saat bilgilerini tamamlayın');
      return;
    }
    try {
      setSavingReservation(true);
      await axios.post('/pos/reservations', {
        outlet_id: outletId,
        table_id: reservationForm.table_id,
        guest_name: reservationForm.guest_name.trim(),
        pax: Math.max(1, Number(reservationForm.pax) || 1),
        res_date: reservationForm.res_date,
        res_time: reservationForm.res_time,
        notes: reservationForm.notes.trim() || null,
      });
      toast.success('Masa rezervasyonu oluşturuldu');
      setReservationForm(current => ({ ...current, guest_name: '', table_id: '', notes: '' }));
      setReservationFormOpen(false);
      await loadReservations();
    } catch (error) {
      toast.error(error?.response?.data?.detail || 'Masa rezervasyonu oluşturulamadı');
    } finally {
      setSavingReservation(false);
    }
  };

  const updateReservationStatus = async (reservation, status) => {
    try {
      setUpdating(reservation.id);
      await axios.put(`/pos/reservations/${reservation.id}/status`, null, { params: { status } });
      toast.success(status === 'seated' ? 'Misafir masaya alındı' : status === 'completed' ? 'Rezervasyon tamamlandı' : 'Rezervasyon iptal edildi');
      await Promise.all([loadReservations(), loadTables()]);
    } catch (error) {
      toast.error(error?.response?.data?.detail || 'Rezervasyon durumu güncellenemedi');
    } finally {
      setUpdating(null);
    }
  };

  const updateTableStatus = async (table, newStatus) => {
    if (newStatus === 'available' && table.status !== 'available') {
      const confirmed = await confirmDialog({
        message: `Masa ${table.table_number} müsait duruma alınsın mı? Açık adisyon varsa önce adisyonu kapatın.`,
      });
      if (!confirmed) return;
    }
    try {
      setUpdating(table.id);
      await axios.put(`/pos/tables/${table.id}/status`, null, { params: { new_status: newStatus } });
      toast.success(`Masa ${table.table_number} durumu güncellendi`);
      await loadTables();
    } catch (error) {
      const detail = error?.response?.data?.detail;
      if (typeof detail === 'string') {
        toast.error(detail);
      } else if (error?.response?.status === 404) {
        toast.error('POS masa modülü henüz aktif değil');
      } else if (error?.response?.status === 409) {
        toast.error(error.response.data?.detail || 'Açık adisyon bulunan masa müsait yapılamaz');
      } else {
        toast.error('Masa durumu güncellenemedi');
      }
    } finally {
      setUpdating(null);
    }
  };

  const transferTable = async (table) => {
    const target = transferTargets[table.id];
    if (!target) {
      toast.error('Hedef masa seçin');
      return;
    }
    const confirmed = await confirmDialog({
      message: `Masa ${table.table_number} adisyonu Masa ${target} üzerine aktarılsın mı?`,
    });
    if (!confirmed) return;
    try {
      setUpdating(table.id);
      await axios.post('/pos/transfer-table', null, {
        params: {
          from_table: String(table.table_number),
          to_table: String(target),
          outlet_id: outletId,
          transfer_all: true,
        },
      });
      setTransferTargets(current => ({ ...current, [table.id]: '' }));
      toast.success(`Adisyon Masa ${target} üzerine aktarıldı`);
      await loadTables();
    } catch (error) {
      toast.error(error?.response?.data?.detail || 'Masa aktarımı tamamlanamadı');
    } finally {
      setUpdating(null);
    }
  };

  const getStatusColor = (status) => {
    switch (status) {
      case 'available':
        return 'bg-green-100 text-green-700 border-green-300';
      case 'occupied':
        return 'bg-red-100 text-red-700 border-red-300';
      case 'reserved':
        return 'bg-yellow-100 text-yellow-700 border-yellow-300';
      default:
        return 'bg-gray-100 text-gray-700 border-gray-300';
    }
  };

  const getStatusIcon = (status) => {
    switch (status) {
      case 'available':
        return <CheckCircle className="w-4 h-4" />;
      case 'occupied':
        return <Users className="w-4 h-4" />;
      case 'reserved':
        return <Clock className="w-4 h-4" />;
      default:
        return null;
    }
  };

  if (loading) {
    return (
      <Card>
        <CardContent className="p-6 text-center">
          <RefreshCw className="w-8 h-8 animate-spin text-blue-600 mx-auto" />
        </CardContent>
      </Card>
    );
  }

  return (
    <Card>
      <CardHeader>
        <div className="flex items-center justify-between">
          <CardTitle className="flex items-center">
            <Users className="w-5 h-5 mr-2 text-blue-600" />
            Restoran Masaları ({tables.length})
          </CardTitle>
          <Button variant="outline" size="sm" onClick={loadTables} disabled={loading}>
            <RefreshCw className="w-4 h-4 mr-2" />
            Yenile
          </Button>
        </div>
      </CardHeader>
      <CardContent>
        <div className="mb-6 rounded-xl border border-blue-200 bg-blue-50 p-4">
          <div className="flex flex-wrap items-center justify-between gap-3">
            <div>
              <h3 className="flex items-center gap-2 font-semibold text-blue-900">
                <CalendarDays className="h-4 w-4" /> Yaklaşan Masa Rezervasyonları
              </h3>
              <p className="mt-1 text-xs text-blue-700">Onaylı rezervasyonu masaya alın, servis bitince tamamlayın.</p>
            </div>
            <Button size="sm" onClick={() => setReservationFormOpen(current => !current)}>
              {reservationFormOpen ? <XCircle className="mr-1 h-4 w-4" /> : <Plus className="mr-1 h-4 w-4" />}
              {reservationFormOpen ? 'Vazgeç' : 'Rezervasyon Ekle'}
            </Button>
          </div>

          {reservationFormOpen && (
            <div className="mt-4 grid gap-2 rounded-lg border border-blue-200 bg-white p-3 md:grid-cols-6">
              <input aria-label="Misafir adı" className="h-9 rounded-md border px-3 text-sm md:col-span-2" placeholder="Misafir adı" value={reservationForm.guest_name} onChange={event => setReservationForm(current => ({ ...current, guest_name: event.target.value }))} />
              <select aria-label="Rezervasyon masası" className="h-9 rounded-md border bg-white px-2 text-sm" value={reservationForm.table_id} onChange={event => setReservationForm(current => ({ ...current, table_id: event.target.value }))}>
                <option value="">Masa seçin</option>
                {tables.map(table => <option key={table.id} value={table.id}>Masa {table.table_number}</option>)}
              </select>
              <input aria-label="Kişi sayısı" className="h-9 rounded-md border px-3 text-sm" type="number" min="1" value={reservationForm.pax} onChange={event => setReservationForm(current => ({ ...current, pax: event.target.value }))} />
              <input aria-label="Rezervasyon tarihi" className="h-9 rounded-md border px-3 text-sm" type="date" value={reservationForm.res_date} onChange={event => setReservationForm(current => ({ ...current, res_date: event.target.value }))} />
              <input aria-label="Rezervasyon saati" className="h-9 rounded-md border px-3 text-sm" type="time" value={reservationForm.res_time} onChange={event => setReservationForm(current => ({ ...current, res_time: event.target.value }))} />
              <input aria-label="Rezervasyon notu" className="h-9 rounded-md border px-3 text-sm md:col-span-5" placeholder="Not (isteğe bağlı)" value={reservationForm.notes} onChange={event => setReservationForm(current => ({ ...current, notes: event.target.value }))} />
              <Button size="sm" className="h-9" onClick={createReservation} disabled={savingReservation}>{savingReservation ? 'Kaydediliyor…' : 'Kaydet'}</Button>
            </div>
          )}

          <div className="mt-3 grid gap-2 lg:grid-cols-2">
            {reservations.filter(item => ['confirmed', 'seated'].includes(item.status)).slice(0, 8).map(reservation => {
              const table = tables.find(item => item.id === reservation.table_id);
              return (
                <div key={reservation.id} className="flex flex-wrap items-center justify-between gap-2 rounded-lg border border-blue-100 bg-white p-3 text-sm">
                  <div>
                    <p className="font-semibold text-gray-900">{reservation.guest_name} · {reservation.pax} kişi</p>
                    <p className="text-xs text-gray-600">{reservation.res_date} {reservation.res_time} · Masa {table?.table_number || reservation.table_id}</p>
                  </div>
                  <div className="flex gap-1">
                    {reservation.status === 'confirmed' && <Button size="sm" variant="outline" onClick={() => updateReservationStatus(reservation, 'seated')} disabled={updating === reservation.id}>Masaya Al</Button>}
                    {reservation.status === 'seated' && <Button size="sm" variant="outline" onClick={() => updateReservationStatus(reservation, 'completed')} disabled={updating === reservation.id}>Tamamla</Button>}
                    <Button size="sm" variant="ghost" className="text-red-600" onClick={() => updateReservationStatus(reservation, 'cancelled')} disabled={updating === reservation.id}>İptal</Button>
                  </div>
                </div>
              );
            })}
            {reservations.filter(item => ['confirmed', 'seated'].includes(item.status)).length === 0 && (
              <p className="py-2 text-sm text-blue-700">Aktif masa rezervasyonu bulunmuyor.</p>
            )}
          </div>
        </div>

        {/* Status Summary */}
        <div className="grid grid-cols-3 gap-3 mb-6">
          <div className="text-center p-3 bg-green-50 rounded-lg border border-green-200">
            <p className="text-2xl font-bold text-green-700">{statusCounts.available || 0}</p>
            <p className="text-xs text-green-600">Müsait</p>
          </div>
          <div className="text-center p-3 bg-red-50 rounded-lg border border-red-200">
            <p className="text-2xl font-bold text-red-700">{statusCounts.occupied || 0}</p>
            <p className="text-xs text-red-600">Dolu</p>
          </div>
          <div className="text-center p-3 bg-yellow-50 rounded-lg border border-yellow-200">
            <p className="text-2xl font-bold text-yellow-700">{statusCounts.reserved || 0}</p>
            <p className="text-xs text-yellow-600">Rezerve</p>
          </div>
        </div>

        {/* Tables Grid */}
        <div className="grid grid-cols-2 md:grid-cols-4 lg:grid-cols-5 gap-3">
          {tables.map((table) => (
            <Card
              key={table.id}
              className={`hover:shadow-md transition-all ${
                updating === table.id ? 'opacity-50' : ''
              }`}
            >
              <CardContent className="p-4">
                <div className="text-center">
                  <p className="text-2xl font-bold text-gray-900 mb-2">
                    {table.table_number}
                  </p>
                  <Badge className={`${getStatusColor(table.status)} flex items-center justify-center gap-1 mb-2`}>
                    {getStatusIcon(table.status)}
                    {STATUS_LABELS[table.status] || 'Durum bilinmiyor'}
                  </Badge>
                  <p className="text-xs text-gray-600 mb-3">
                    <Users className="w-3 h-3 inline mr-1" />
                    {table.seats ?? table.capacity ?? 0} kişilik
                  </p>
                  {(table.current_bill > 0 || table.current_transaction_id) && (
                    <div className="mb-3 rounded-lg border border-amber-200 bg-amber-50 p-2 text-left text-xs text-amber-900">
                      <div className="flex items-center justify-between gap-2 font-semibold">
                        <span className="flex items-center gap-1"><ReceiptText className="h-3.5 w-3.5" /> Açık adisyon</span>
                        <span>{formatCurrency(table.current_bill || 0, cachedTenantCurrency())}</span>
                      </div>
                      <div className="mt-1 text-amber-700">
                        {table.guest_count || 0} misafir · {table.duration_minutes || 0} dk
                      </div>
                    </div>
                  )}

                  {/* Quick Actions */}
                  <div className="space-y-1">
                    {table.status !== 'available' && (
                      <Button
                        size="sm"
                        variant="outline"
                        className="w-full text-xs"
                        onClick={() => updateTableStatus(table, 'available')}
                        disabled={updating === table.id}
                      >
                        <CheckCircle className="w-3 h-3 mr-1" />
                        Müsait Yap
                      </Button>
                    )}
                    {(table.current_transaction_id || table.current_bill > 0) && (
                      <div className="space-y-1.5 border-t pt-2">
                        <select
                          aria-label={`Masa ${table.table_number} hedef masa`}
                          className="h-8 w-full rounded-md border border-gray-300 bg-white px-2 text-xs"
                          value={transferTargets[table.id] || ''}
                          onChange={event => setTransferTargets(current => ({ ...current, [table.id]: event.target.value }))}
                          disabled={updating === table.id}
                        >
                          <option value="">Hedef masa seçin</option>
                          {tables
                            .filter(candidate => candidate.id !== table.id && candidate.status === 'available' && !candidate.current_transaction_id)
                            .map(candidate => (
                              <option key={candidate.id} value={candidate.table_number}>Masa {candidate.table_number}</option>
                            ))}
                        </select>
                        <Button
                          size="sm"
                          variant="outline"
                          className="w-full text-xs"
                          onClick={() => transferTable(table)}
                          disabled={updating === table.id || !transferTargets[table.id]}
                        >
                          <ArrowRightLeft className="mr-1 h-3 w-3" /> Adisyonu Aktar
                        </Button>
                      </div>
                    )}
                    {table.status === 'available' && (
                      <>
                        <Button
                          size="sm"
                          className="w-full text-xs bg-red-600 hover:bg-red-700"
                          onClick={() => updateTableStatus(table, 'occupied')}
                          disabled={updating === table.id}
                        >
                          <Users className="w-3 h-3 mr-1" />
                          Dolu Yap
                        </Button>
                        <Button
                          size="sm"
                          variant="outline"
                          className="w-full text-xs"
                          onClick={() => updateTableStatus(table, 'reserved')}
                          disabled={updating === table.id}
                        >
                          <Clock className="w-3 h-3 mr-1" />
                          Rezerve Et
                        </Button>
                      </>
                    )}
                  </div>
                </div>
              </CardContent>
            </Card>
          ))}
        </div>

        {tables.length === 0 && (
          <div className="text-center py-8 text-gray-500">
            {notProvisioned
              ? 'Bu satış noktası için masa düzeni henüz oluşturulmamış.'
              : 'Bu satış noktasında henüz masa bulunmuyor.'}
          </div>
        )}
      </CardContent>
    </Card>
  );
};

export default POSTableManagement;
