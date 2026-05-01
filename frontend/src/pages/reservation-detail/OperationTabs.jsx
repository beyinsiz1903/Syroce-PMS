import { useState, useEffect } from 'react';
import axios from 'axios';
import { toast } from 'sonner';
import { Button } from '@/components/ui/button';
import { Input } from '@/components/ui/input';
import { Label } from '@/components/ui/label';
import { Loader2, Home, Repeat2, AlertTriangle } from 'lucide-react';
import { API, fmtTL, fmtTs } from './helpers';

export function RoomChangeTab({ booking, room, roomMoves, onRefresh }) {
  const [roomTypes, setRoomTypes] = useState([]);
  const [selectedType, setSelectedType] = useState('');
  const [selectedRoomId, setSelectedRoomId] = useState('');
  const [reason, setReason] = useState('');
  const [pricingOption, setPricingOption] = useState('current');
  const [customPrice, setCustomPrice] = useState('');
  const [loading, setLoading] = useState(false);
  const [loadingRooms, setLoadingRooms] = useState(false);

  useEffect(() => {
    const loadRooms = async () => {
      setLoadingRooms(true);
      try {
        const ci = booking?.check_in?.toString().slice(0, 10) || '';
        const co = booking?.check_out?.toString().slice(0, 10) || '';
        const res = await axios.get(`/pms/available-rooms-by-type?check_in=${ci}&check_out=${co}`);
        setRoomTypes(res.data.room_types || []);
      } catch (e) { console.log('Room load error:', e); }
      setLoadingRooms(false);
    };
    loadRooms();
  }, [booking]);

  const currentRoomType = room?.room_type || '';
  const selectedTypeData = roomTypes.find(rt => rt.type === selectedType);
  const isUpgrade = selectedTypeData && currentRoomType && selectedTypeData.base_price > (room?.base_price || 0);
  const priceDiff = selectedTypeData ? (selectedTypeData.base_price - (room?.base_price || 0)) : 0;

  const handleChange = async () => {
    if (!selectedRoomId || !reason) { toast.error('Oda ve sebep seçimi zorunlu'); return; }
    setLoading(true);
    try {
      const extraCharge = pricingOption === 'upgrade' ? Math.max(0, priceDiff) : pricingOption === 'custom' ? parseFloat(customPrice) || 0 : 0;
      await axios.post(`/pms/reservations/${booking.id}/room-change`, {
        new_room_id: selectedRoomId, reason, transfer_folio: true, extra_charge: extraCharge
      });
      toast.success('Oda değiştirildi');
      setSelectedRoomId(''); setSelectedType(''); setReason(''); onRefresh?.();
    } catch (e) { toast.error('Hata: ' + (e.response?.data?.detail || e.message)); }
    setLoading(false);
  };

  return (
    <div data-testid="room-change-tab" className="space-y-4">
      <div className="border rounded-lg p-4 bg-blue-50/50">
        <div className="text-xs font-semibold text-blue-600 uppercase mb-2">Mevcut Oda</div>
        <div className="flex items-center gap-3">
          <div className="w-10 h-10 bg-blue-600 text-white rounded-lg flex items-center justify-center font-bold">{booking?.room_number || '-'}</div>
          <div>
            <div className="text-sm font-semibold">{room?.room_type || 'Oda'} - {booking?.room_number || '-'}</div>
            <div className="text-xs text-gray-500">Kat: {room?.floor || '-'} | Fiyat: {fmtTL(room?.base_price)} TL/gece</div>
          </div>
        </div>
      </div>

      <div className="border rounded-lg p-4 space-y-3">
        <div className="text-sm font-semibold text-gray-700">Yeni Oda Sec</div>
        {loadingRooms ? (
          <div className="flex items-center gap-2 text-sm text-gray-400"><Loader2 className="w-4 h-4 animate-spin" /> Müsait odalar yükleniyor...</div>
        ) : (
          <>
            <div className="grid grid-cols-2 gap-3">
              <div>
                <Label className="text-xs">Oda Tipi</Label>
                <select value={selectedType} onChange={e => { setSelectedType(e.target.value); setSelectedRoomId(''); }} className="w-full h-8 text-sm border rounded-md px-2 bg-white" data-testid="room-change-type-select">
                  <option value="">Oda tipi seçiniz...</option>
                  {roomTypes.map(rt => (
                    <option key={rt.type} value={rt.type}>
                      {rt.type} ({rt.rooms.filter(r => r.is_available && r.id !== booking?.room_id).length} müsait) - {fmtTL(rt.base_price)} TL
                    </option>
                  ))}
                </select>
              </div>
              <div>
                <Label className="text-xs">Oda</Label>
                <select value={selectedRoomId} onChange={e => setSelectedRoomId(e.target.value)} className="w-full h-8 text-sm border rounded-md px-2 bg-white" data-testid="room-change-room-select">
                  <option value="">Oda Seciniz...</option>
                  {selectedType && roomTypes.find(rt => rt.type === selectedType)?.rooms
                    .filter(r => r.is_available && r.id !== booking?.room_id)
                    .map(r => (
                      <option key={r.id} value={r.id}>{r.room_number} (Kat: {r.floor || '-'})</option>
                    ))
                  }
                </select>
              </div>
            </div>

            {isUpgrade && selectedType && (
              <div className="bg-amber-50 border border-amber-200 rounded-lg p-3 space-y-2">
                <div className="text-xs font-semibold text-amber-800">Ust Kategori Oda - Fiyat Farki: {fmtTL(priceDiff)} TL/gece</div>
                <div className="flex gap-3">
                  <label className="flex items-center gap-1.5 text-xs cursor-pointer">
                    <input type="radio" name="pricing" value="current" checked={pricingOption === 'current'} onChange={e => setPricingOption(e.target.value)} />
                    Mevcut fiyat (ek ücret yok)
                  </label>
                  <label className="flex items-center gap-1.5 text-xs cursor-pointer">
                    <input type="radio" name="pricing" value="upgrade" checked={pricingOption === 'upgrade'} onChange={e => setPricingOption(e.target.value)} />
                    Güncel fiyat farki ({fmtTL(priceDiff)} TL)
                  </label>
                  <label className="flex items-center gap-1.5 text-xs cursor-pointer">
                    <input type="radio" name="pricing" value="custom" checked={pricingOption === 'custom'} onChange={e => setPricingOption(e.target.value)} />
                    Özel fiyat
                  </label>
                </div>
                {pricingOption === 'custom' && (
                  <Input type="number" value={customPrice} onChange={e => setCustomPrice(e.target.value)} placeholder="Ek ücret (TL)" className="h-8 text-sm w-40" />
                )}
              </div>
            )}

            <div>
              <Label className="text-xs">Degisiklik Sebebi</Label>
              <select value={reason} onChange={e => setReason(e.target.value)} className="w-full h-8 text-sm border rounded-md px-2 bg-white">
                <option value="">Sebep Seciniz...</option>
                <option value="Misafir istegi">Misafir istegi</option>
                <option value="Teknik ariza">Teknik ariza</option>
                <option value="Upgrade">Upgrade</option>
                <option value="Downgrade">Downgrade</option>
                <option value="Temizlik sorunu">Temizlik sorunu</option>
                <option value="Diger">Diger</option>
              </select>
            </div>
          </>
        )}
        <Button size="sm" onClick={handleChange} disabled={loading || !selectedRoomId || !reason} className="bg-indigo-600 hover:bg-indigo-700 text-white h-8 text-xs" data-testid="room-change-submit-btn">
          {loading ? <Loader2 className="w-3 h-3 animate-spin mr-1" /> : <Repeat2 className="w-3 h-3 mr-1" />} Oda Degistir
        </Button>
      </div>

      <div className="space-y-2">
        <div className="text-xs font-semibold text-gray-500 uppercase">Oda Degisiklik Geçmişi</div>
        {(!roomMoves || roomMoves.length === 0) ? <div className="text-center py-4 text-gray-400 text-sm">Geçmiş oda değişikliği yok</div> : (
          roomMoves.map((rm, i) => (
            <div key={rm.id || i} className="border rounded-lg p-3 flex items-center gap-3">
              <div className="w-8 h-8 bg-indigo-100 rounded-full flex items-center justify-center"><Home className="w-4 h-4 text-indigo-600" /></div>
              <div className="flex-1">
                <div className="text-sm font-medium">{rm.from_room_number || '?'} → {rm.to_room_number || '?'}</div>
                <div className="text-xs text-gray-400">{rm.reason} | {rm.moved_by} | {fmtTs(rm.moved_at)}</div>
              </div>
            </div>
          ))
        )}
      </div>
    </div>
  );
}

export function CancelTab({ booking, bookingId, onRefresh, onClose }) {
  const [reason, setReason] = useState('');
  const [cancelType, setCancelType] = useState('guest_request');
  const [applyNoshow, setApplyNoshow] = useState(false);
  const [noshowChargeType, setNoshowChargeType] = useState('per_night');
  const [noshowAmount, setNoshowAmount] = useState('');
  const [loading, setLoading] = useState(false);

  const cancelTypes = {
    guest_request: 'Misafir Talebi', no_suitable_room: 'Uygun Oda Yok',
    force_majeure: 'Mucbir Sebep', overbooking: 'Overbooking',
    payment_issue: 'Ödeme Sorunu', other: 'Diger'
  };

  const nights = booking ? Math.max(1, Math.ceil((new Date(booking.check_out) - new Date(booking.check_in)) / (1000 * 60 * 60 * 24))) : 1;
  const nightlyRate = booking ? (booking.total_amount || 0) / nights : 0;

  useEffect(() => {
    if (noshowChargeType === 'per_night') setNoshowAmount(String(Math.round(nightlyRate)));
    else if (noshowChargeType === 'full_stay') setNoshowAmount(String(booking?.total_amount || 0));
  }, [noshowChargeType, nightlyRate, booking]);

  const handleCancel = async () => {
    if (!reason) { toast.error('İptal nedeni giriniz'); return; }
    if (!window.confirm(applyNoshow ? 'No-show olarak iptal edilsin mi?' : 'Rezervasyon iptal edilsin mi?')) return;
    setLoading(true);
    try {
      await axios.post(`/pms/reservations/${bookingId}/cancel`, {
        reason, cancel_type: cancelType, apply_noshow: applyNoshow,
        noshow_charge_type: applyNoshow ? noshowChargeType : null,
        noshow_charge_amount: applyNoshow ? parseFloat(noshowAmount) || 0 : null,
      });
      toast.success(applyNoshow ? 'No-show olarak isaretlendi' : 'Rezervasyon iptal edildi');
      onRefresh?.();
    } catch (e) { toast.error('Hata: ' + (e.response?.data?.detail || e.message)); }
    setLoading(false);
  };

  return (
    <div data-testid="cancel-tab" className="space-y-4 max-w-lg">
      <div className="bg-red-50 border border-red-200 rounded-lg p-4">
        <div className="text-sm font-semibold text-red-800 mb-3">Rezervasyon Iptali</div>
        <div className="space-y-3">
          <div>
            <Label className="text-xs">İptal Nedeni *</Label>
            <select value={cancelType} onChange={e => setCancelType(e.target.value)} className="w-full h-8 text-sm border rounded-md px-2 bg-white" data-testid="cancel-type-select">
              {Object.entries(cancelTypes).map(([k, v]) => <option key={k} value={k}>{v}</option>)}
            </select>
          </div>
          <div>
            <Label className="text-xs">Açıklama *</Label>
            <textarea value={reason} onChange={e => setReason(e.target.value)} className="w-full h-16 text-sm border rounded-md p-2 resize-none bg-white" placeholder="İptal aciklamasi..." data-testid="cancel-reason-input" />
          </div>

          <div className="border-t pt-3">
            <label className="flex items-center gap-2 cursor-pointer">
              <input type="checkbox" checked={applyNoshow} onChange={e => setApplyNoshow(e.target.checked)} className="rounded" data-testid="noshow-checkbox" />
              <span className="text-sm font-medium text-red-700">No-Show Uygula</span>
            </label>
          </div>

          {applyNoshow && (
            <div className="bg-white border rounded-lg p-3 space-y-2">
              <div className="text-xs font-semibold text-gray-700">No-Show Ucreti</div>
              <div className="flex gap-2">
                <label className="flex items-center gap-1.5 text-xs cursor-pointer">
                  <input type="radio" name="noshowType" value="per_night" checked={noshowChargeType === 'per_night'} onChange={e => setNoshowChargeType(e.target.value)} />
                  1 Gecelik ({fmtTL(Math.round(nightlyRate))} TL)
                </label>
                <label className="flex items-center gap-1.5 text-xs cursor-pointer">
                  <input type="radio" name="noshowType" value="full_stay" checked={noshowChargeType === 'full_stay'} onChange={e => setNoshowChargeType(e.target.value)} />
                  Tüm Konaklama ({fmtTL(booking?.total_amount)} TL)
                </label>
                <label className="flex items-center gap-1.5 text-xs cursor-pointer">
                  <input type="radio" name="noshowType" value="custom" checked={noshowChargeType === 'custom'} onChange={e => setNoshowChargeType(e.target.value)} />
                  Özel Tutar
                </label>
              </div>
              <Input type="number" value={noshowAmount} onChange={e => { setNoshowAmount(e.target.value); setNoshowChargeType('custom'); }} placeholder="Tutar (TL)" className="h-8 text-sm w-40" data-testid="noshow-amount-input" />
            </div>
          )}

          <Button onClick={handleCancel} disabled={loading || !reason} className="bg-red-600 hover:bg-red-700 text-white h-9 text-sm w-full" data-testid="cancel-submit-btn">
            {loading ? <Loader2 className="w-4 h-4 animate-spin mr-1" /> : <AlertTriangle className="w-4 h-4 mr-1" />}
            {applyNoshow ? 'No-Show Olarak İptal Et' : 'Rezervasyonu İptal Et'}
          </Button>
        </div>
      </div>
    </div>
  );
}
