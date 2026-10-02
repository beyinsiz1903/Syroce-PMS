import React, { useState, useEffect } from 'react';
import axios from 'axios';
import { toast } from 'sonner';
import { cachedTenantCurrency, formatCurrency } from '@/lib/currency';
import { formatCurrencyBreakdown } from '@/lib/reportCurrency';

const roomStatusLabel = {
  available: 'Müsait',
  occupied: 'Dolu',
  maintenance: 'Bakımda',
  out_of_order: 'Arızalı',
};

const EnhancedReservationCalendar = () => {
  const [selectedDate, setSelectedDate] = useState(new Date().toISOString().split('T')[0]);
  const [rooms, setRooms] = useState([]);
  const [adrData, setAdrData] = useState(null);
  const [aiPricing, setAiPricing] = useState(null);
  const [aiPricingLoading, setAiPricingLoading] = useState(false);
  const [draggedBooking, setDraggedBooking] = useState(null);
  const [showRateOverride, setShowRateOverride] = useState(false);
  const [selectedBooking, setSelectedBooking] = useState(null);
  const displayCurrency = adrData?.currency || cachedTenantCurrency();
  useEffect(() => {
    fetchRooms();
    fetchADR();
    // eslint-disable-next-line react-hooks/exhaustive-deps -- mevcut davranış korunuyor; toplu temizlik turunda eklendi, niyet inceleme bekliyor
  }, [selectedDate]);
  const fetchRooms = async () => {
    try {
      const response = await axios.get(`/rooms`, {
        headers: {}
      });
      setRooms(response.data.rooms || []);
    } catch (error) {
      console.error('Error fetching rooms:', error);
    }
  };
  const fetchADR = async () => {
    try {
      const endDate = new Date(selectedDate);
      endDate.setDate(endDate.getDate() + 30);
      const response = await axios.get(`/reservations/adr-visibility?start_date=${selectedDate}&end_date=${endDate.toISOString().split('T')[0]}`, {
        headers: {}
      });
      setAdrData(response.data);
    } catch (error) {
      console.error('Error fetching ADR:', error);
    }
  };
  const fetchAIPricing = async () => {
    setAiPricingLoading(true);
    try {
      const endDate = new Date(selectedDate);
      endDate.setDate(endDate.getDate() + 30);
      // Bu ekran karar desteğidir: dry_run, fiyatları/veritabanını/kanalları
      // değiştirmeden yalnızca öneri üretir. Yayınlama RMS çalışma alanındaki
      // açıkça adlandırılmış ve onaylı akıştan yapılır.
      const response = await axios.post(`/rms/ai-pricing/auto-publish-rates`, null, {
        headers: {},
        params: {
          start_date: selectedDate,
          end_date: endDate.toISOString().split('T')[0],
          strategy: 'revenue_optimization',
          dry_run: true
        }
      });
      setAiPricing(response.data);
      if (response.data.data_available === false || response.data.success === false) {
        toast.error(response.data.message || 'Fiyat önerisi üretmek için yeterli gerçek veri yok.');
        return;
      }
      toast.success(`${response.data.published_rates?.length || 0} fiyat önerisi hazırlandı. Hiçbir fiyat yayınlanmadı.`);
    } catch (error) {
      console.error('Error fetching AI pricing:', error);
      toast.error(error.response?.data?.detail || error.response?.data?.message || 'Fiyat önerileri alınamadı.');
    } finally {
      setAiPricingLoading(false);
    }
  };
  const handleRateOverride = async (bookingId, newRate, reason) => {
    try {
      // Bug CP fix — backend now expects query params (Query) not JSON body
      await axios.post(`/reservations/rate-override-panel`, null, {
        headers: {},
        params: {
          booking_id: bookingId,
          new_rate: parseFloat(newRate),
          override_reason: reason
        }
      });
      toast.success('Fiyat geçersiz kılma başarılı');
      setShowRateOverride(false);
      fetchRooms();
    } catch (error) {
      console.error('Error overriding rate:', error);
      toast.error('Fiyat geçersiz kılınamadı');
    }
  };
  return <div className="p-6 bg-white overflow-hidden">
      <div className="flex flex-col lg:flex-row justify-between items-start lg:items-center gap-4 mb-6">
        <h1 className="text-3xl font-bold">Fiyat ve Müsaitlik Takvimi</h1>
        <div className="flex flex-wrap gap-4 w-full lg:w-auto">
          <button onClick={fetchAIPricing} disabled={aiPricingLoading} className="px-4 py-2 bg-indigo-600 text-white rounded-lg hover:bg-indigo-700 disabled:opacity-50 flex items-center gap-2 whitespace-nowrap">
            {aiPricingLoading ? 'Öneriler hesaplanıyor…' : 'Yapay zekâ fiyat önerilerini göster'}
          </button>
          <input type="date" value={selectedDate} onChange={e => setSelectedDate(e.target.value)} className="px-4 py-2 border rounded-lg flex-1 min-w-[150px]" />
        </div>
      </div>

      {aiPricing && <section aria-live="polite" className="mb-6 rounded-lg border border-indigo-200 bg-indigo-50 p-4">
          <div className="flex flex-col gap-1 sm:flex-row sm:items-center sm:justify-between">
            <div>
              <h2 className="font-semibold text-indigo-950">Fiyat önerisi önizlemesi</h2>
              <p className="text-sm text-indigo-900">Bu sonuç yalnızca öneridir; hiçbir fiyat kaydedilmedi veya kanallara gönderilmedi.</p>
            </div>
            <span className="text-sm font-medium text-indigo-900">{aiPricing.published_rates?.length || 0} tarih</span>
          </div>
          {aiPricing.published_rates?.length > 0 && <div className="mt-3 max-h-48 overflow-y-auto rounded border border-indigo-100 bg-white">
              {aiPricing.published_rates.map(rate => <div key={rate.date} className="grid grid-cols-3 gap-2 border-b border-indigo-50 px-3 py-2 text-sm last:border-b-0">
                  <span>{rate.date}</span>
                  <span>Doluluk %{rate.forecasted_occupancy}</span>
                  <strong className="text-right">{formatCurrency(rate.recommended_rate, displayCurrency)}</strong>
                </div>)}
            </div>}
        </section>}

      {/* ADR Summary */}
      {adrData && <div className="grid grid-cols-1 sm:grid-cols-2 lg:grid-cols-4 gap-4 mb-6">
          <div className="bg-blue-50 p-4 rounded-lg">
            <div className="text-sm text-gray-600">Ortalama günlük fiyat (ADR)</div>
            <div className="text-2xl font-bold text-blue-600">{formatCurrencyBreakdown(adrData.overall_adr_by_currency, adrData.overall_adr, displayCurrency)}</div>
          </div>
          <div className="bg-green-50 p-4 rounded-lg">
            <div className="text-sm text-gray-600">Toplam oda geliri</div>
            <div className="text-2xl font-bold text-green-600">{formatCurrencyBreakdown(adrData.total_room_revenue_by_currency, adrData.total_room_revenue, displayCurrency)}</div>
          </div>
          <div className="bg-indigo-50 p-4 rounded-lg">
            <div className="text-sm text-gray-600">Oda gecesi</div>
            <div className="text-2xl font-bold text-indigo-600">{adrData.total_room_nights}</div>
          </div>
          <div className="bg-amber-50 p-4 rounded-lg">
            <div className="text-sm text-gray-600">Rezervasyon</div>
            <div className="text-2xl font-bold text-amber-600">{adrData.total_bookings}</div>
          </div>
        </div>}

      {/* Room Grid */}
      <div className="border rounded-lg overflow-hidden">
        <div className="bg-gray-100 p-4 font-semibold border-b">
          Müsaitlik görünümü · {rooms.length} oda
        </div>
        <div className="max-h-[600px] overflow-y-auto overflow-x-hidden">
          {rooms.map(room => <div key={room.id} className="border-b p-4 hover:bg-gray-50">
              <div className="flex flex-col sm:flex-row justify-between items-start sm:items-center gap-4">
                <div className="flex flex-wrap items-center gap-2">
                  <span className="font-semibold">{room.room_number}</span>
                  <span className="text-gray-600">{room.room_type}</span>
                  <span className={`px-2 py-1 rounded text-sm ${room.status === 'available' ? 'bg-green-100 text-green-800' : room.status === 'occupied' ? 'bg-blue-100 text-blue-800' : 'bg-gray-100 text-gray-800'}`}>
                    {roomStatusLabel[room.status] || room.status || 'Bilinmiyor'}
                  </span>
                </div>
                <div className="flex flex-wrap gap-2">
                  <button disabled={!room.current_booking_id} title={room.current_booking_id ? 'Bu odadaki aktif rezervasyonun fiyatını düzeltin' : 'Fiyat düzeltmesi için odada aktif rezervasyon olmalıdır'} onClick={() => {
                setSelectedBooking(room);
                setShowRateOverride(true);
              }} className="px-3 py-1 bg-blue-600 text-white rounded hover:bg-blue-700 text-sm disabled:cursor-not-allowed disabled:opacity-50">
                    Fiyatı düzelt
                  </button>
                </div>
              </div>
            </div>)}
        </div>
      </div>

      {/* Rate Override Modal */}
      {showRateOverride && selectedBooking && <div className="fixed inset-0 bg-black bg-opacity-50 flex items-center justify-center z-50">
          <div className="bg-white rounded-lg p-6 w-[500px]">
            <h3 className="text-xl font-bold mb-4">Fiyat düzeltmesi · Oda {selectedBooking.room_number}</h3>
            <form onSubmit={e => {
          e.preventDefault();
          const formData = new FormData(e.target);
          handleRateOverride(selectedBooking.current_booking_id, formData.get('new_rate'), formData.get('reason'));
        }}>
              <div className="mb-4">
                <label className="block text-sm font-medium mb-2">Yeni fiyat ({selectedBooking.currency || displayCurrency})</label>
                <input type="number" name="new_rate" step="0.01" min="0.01" required className="w-full px-4 py-2 border rounded-lg" placeholder="Yeni fiyatı girin" />
              </div>
              <div className="mb-4">
                <label className="block text-sm font-medium mb-2">Düzeltme gerekçesi</label>
                <textarea name="reason" required rows="3" className="w-full px-4 py-2 border rounded-lg" placeholder="Fiyatın neden değiştirildiğini yazın" />
              </div>
              <div className="flex justify-end gap-2">
                <button type="button" onClick={() => setShowRateOverride(false)} className="px-4 py-2 bg-gray-200 rounded-lg hover:bg-gray-300">
                  Vazgeç
                </button>
                <button type="submit" className="px-4 py-2 bg-blue-600 text-white rounded-lg hover:bg-blue-700">
                  Fiyatı düzelt
                </button>
              </div>
            </form>
          </div>
        </div>}
    </div>;
};
export default EnhancedReservationCalendar;
