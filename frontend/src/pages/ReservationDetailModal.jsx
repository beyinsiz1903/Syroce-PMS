import { useState, useEffect, useCallback } from 'react';
import axios from 'axios';
import { toast } from 'sonner';
import { Tabs, TabsContent, TabsList, TabsTrigger } from '@/components/ui/tabs';
import { Button } from '@/components/ui/button';
import { Badge } from '@/components/ui/badge';
import {
  X, Calendar, DollarSign, FileText, Users, Receipt,
  History, MessageSquare, Star, AlertTriangle,
  LogIn, LogOut, Repeat2, Shield, Mail, Loader2, CreditCard
} from 'lucide-react';

import { API, fmtTL, statusLabel } from './reservation-detail/helpers';
import { GeneralInfoTab, GuestsTab } from './reservation-detail/InfoTabs';
import { FoliosTab } from './reservation-detail/FoliosTab';
import { DailyRatesTab, ExtraChargesTab } from './reservation-detail/PricingTabs';
import { RoomChangeTab, CancelTab } from './reservation-detail/OperationTabs';
import { CommunicationTab, NotesTab, HistoryTab } from './reservation-detail/GuestServiceTabs';
import { DepositsTab, VoucherTab, InvoiceTab } from './reservation-detail/DocumentTabs';
import { OnlinePaymentTab } from './reservation-detail/OnlinePaymentTab';
import { VCCTab } from './reservation-detail/VCCTab';

export default function ReservationDetailModal({ bookingId, onClose, allBookings }) {
  const [data, setData] = useState(null);
  const [loading, setLoading] = useState(true);
  const [activeTab, setActiveTab] = useState('general');

  const loadData = useCallback(async () => {
    if (!bookingId) return;
    try {
      const res = await axios.get(`/pms/reservations/${bookingId}/full-detail`);
      setData(res.data);
    } catch (e) {
      toast.error('Rezervasyon detayı yüklenemedi');
      console.error(e);
    }
    setLoading(false);
  }, [bookingId]);

  useEffect(() => { setLoading(true); loadData(); }, [loadData]);

  const action = async (url, body = {}, msg = 'İşlem tamamlandi') => {
    try { await axios.post(`${API}${url}`, body); toast.success(msg); loadData(); }
    catch (e) { toast.error('Hata: ' + (e.response?.data?.detail || e.message)); }
  };

  if (loading) return (
    <div className="fixed inset-0 z-[60] flex items-center justify-center bg-black/50">
      <div className="bg-white rounded-2xl p-8 flex flex-col items-center gap-3"><Loader2 className="w-8 h-8 animate-spin text-blue-600" /><span className="text-sm text-gray-500">Yükleniyor...</span></div>
    </div>
  );

  if (!data) return null;

  const { booking, guest, room, company, folios, charges, payments, extra_charges, notes, history, room_moves, daily_rates, guests, summary, communication_logs, deposits } = data;

  const tabs = [
    { id: 'general', label: 'Genel Bilgiler', icon: FileText },
    { id: 'guests', label: `Misafirler (${guests?.length || 0})`, icon: Users },
    { id: 'online_payment', label: 'Online Ödeme', icon: CreditCard },
    { id: 'vcc', label: 'Sanal Kart', icon: Shield },
    { id: 'folios', label: 'Folyolar', icon: DollarSign },
    { id: 'daily_rates', label: 'Günlük Fiyatlar', icon: Calendar },
    { id: 'extras', label: 'Ek Ücretler', icon: Receipt },
    { id: 'room_change', label: 'Oda Degistir', icon: Repeat2 },
    { id: 'cancel', label: 'İptal', icon: AlertTriangle },
    { id: 'voucher', label: 'Voucher', icon: FileText },
    { id: 'invoice', label: 'Fatura', icon: Receipt },
    { id: 'deposits', label: `Depozito ${deposits?.length ? `(${deposits.length})` : ''}`, icon: Shield },
    { id: 'communication', label: `İletişim ${communication_logs?.length ? `(${communication_logs.length})` : ''}`, icon: Mail },
    { id: 'notes', label: `Notlar ${notes?.length ? `(${notes.length})` : ''}`, icon: MessageSquare },
    { id: 'history', label: 'Geçmiş', icon: History },
  ];

  return (
    <div className="fixed inset-0 z-[60]" data-testid="reservation-detail-modal">
      <div className="absolute inset-0 bg-black/50 backdrop-blur-sm" onClick={onClose} />
      <div className="absolute inset-2 md:inset-4 lg:inset-6 bg-white rounded-2xl shadow-2xl flex flex-col overflow-hidden">
        {/* Header */}
        <div className="flex items-center justify-between px-6 py-3 border-b bg-gradient-to-r from-slate-800 to-slate-700">
          <div className="flex items-center gap-4">
            <h2 className="text-white font-semibold text-base">Rezervasyon - {booking?.ota_confirmation || booking?.id?.slice(0, 12) || ''}</h2>
            <Badge className="bg-white/20 text-white border-white/30 text-xs">{statusLabel(booking?.status)}</Badge>
            {booking?.group_booking_id && <Badge className="bg-amber-400/30 text-amber-100 border-amber-400/40 text-xs">Grup</Badge>}
          </div>
          <button onClick={onClose} className="text-white/70 hover:text-white hover:bg-white/10 rounded-full p-2 transition-colors" data-testid="close-reservation-detail"><X className="w-5 h-5" /></button>
        </div>

        <div className="flex flex-1 overflow-hidden">
          {/* Left Sidebar */}
          <div className="w-64 border-r bg-gray-50 overflow-y-auto flex-shrink-0">
            <div className="p-4 space-y-4">
              <div className="text-center">
                <div className="w-14 h-14 bg-teal-600 text-white rounded-full flex items-center justify-center text-xl font-bold mx-auto mb-2">{(guest?.name || booking?.guest_name || 'M')[0]?.toUpperCase()}</div>
                <div className="font-bold text-gray-800 text-sm">{guest?.name || booking?.guest_name}</div>
                {guest?.vip_status && <Badge className="bg-amber-100 text-amber-700 border-amber-200 mt-1 text-xs"><Star className="w-3 h-3 mr-0.5" /> VIP</Badge>}
              </div>
              <div className="space-y-2 text-xs">
                <div className="flex justify-between"><span className="text-gray-500">Durum</span><Badge className="bg-emerald-100 text-emerald-700 text-xs h-5">{statusLabel(booking?.status)}</Badge></div>
                <div className="flex justify-between"><span className="text-gray-500">Kanal</span><span className="font-medium text-gray-700">{booking?.source_channel || 'Direkt'}</span></div>
                <div className="flex justify-between"><span className="text-gray-500">Oda</span><span className="font-medium text-blue-600">{booking?.room_number || room?.room_number || '-'}</span></div>
                <div className="flex justify-between"><span className="text-gray-500">Giriş</span><span className="font-medium">{booking?.check_in?.toString().slice(0, 10)}</span></div>
                <div className="flex justify-between"><span className="text-gray-500">Çıkış</span><span className="font-medium">{booking?.check_out?.toString().slice(0, 10)}</span></div>
                {booking?.created_at && (
                  <div className="flex justify-between"><span className="text-gray-500">Olusturulma</span><span className="font-medium text-[10px]">{new Date(booking.created_at).toLocaleString('tr-TR', { day: '2-digit', month: 'short', hour: '2-digit', minute: '2-digit' })}</span></div>
                )}
              </div>

              {/* Operational Status Panel */}
              <div className="space-y-1.5 pt-2 border-t" data-testid="reservation-ops-panel">
                <p className="text-[10px] font-semibold text-gray-400 uppercase tracking-wider mb-1.5">Operasyonel Durum</p>
                {/* Payment status */}
                {(summary?.balance || 0) > 0 && (
                  <div className="flex items-center gap-1.5 bg-red-50 border border-red-200 rounded-md px-2 py-1.5" data-testid="ops-payment-alert">
                    <AlertTriangle className="w-3 h-3 text-red-500 flex-shrink-0" />
                    <span className="text-[11px] text-red-700 font-medium">Ödeme bekleniyor: {fmtTL(summary?.balance)} TL</span>
                  </div>
                )}
                {(summary?.balance || 0) <= 0 && (
                  <div className="flex items-center gap-1.5 bg-emerald-50 border border-emerald-200 rounded-md px-2 py-1.5" data-testid="ops-payment-ok">
                    <Shield className="w-3 h-3 text-emerald-500 flex-shrink-0" />
                    <span className="text-[11px] text-emerald-700">Ödeme tamam</span>
                  </div>
                )}
                {/* Room status */}
                {room && (room.status === 'dirty' || room.status === 'cleaning') && (
                  <div className="flex items-center gap-1.5 bg-amber-50 border border-amber-200 rounded-md px-2 py-1.5" data-testid="ops-room-dirty">
                    <AlertTriangle className="w-3 h-3 text-amber-500 flex-shrink-0" />
                    <span className="text-[11px] text-amber-700 font-medium">Oda {room.status === 'cleaning' ? 'temizleniyor' : 'kirli'}</span>
                  </div>
                )}
                {room && room.status === 'available' && (
                  <div className="flex items-center gap-1.5 bg-emerald-50 border border-emerald-200 rounded-md px-2 py-1.5" data-testid="ops-room-ready">
                    <Shield className="w-3 h-3 text-emerald-500 flex-shrink-0" />
                    <span className="text-[11px] text-emerald-700">Oda hazir</span>
                  </div>
                )}
                {/* VIP status */}
                {guest?.vip_status && (
                  <div className="flex items-center gap-1.5 bg-purple-50 border border-purple-200 rounded-md px-2 py-1.5" data-testid="ops-vip">
                    <Star className="w-3 h-3 text-purple-500 flex-shrink-0" />
                    <span className="text-[11px] text-purple-700 font-medium">VIP Misafir</span>
                  </div>
                )}
                {/* Repeat guest */}
                {guest?.total_stays > 1 && (
                  <div className="flex items-center gap-1.5 bg-blue-50 border border-blue-200 rounded-md px-2 py-1.5" data-testid="ops-repeat">
                    <Users className="w-3 h-3 text-blue-500 flex-shrink-0" />
                    <span className="text-[11px] text-blue-700">{guest.total_stays}. konaklama</span>
                  </div>
                )}
                {/* Guest preferences */}
                {guest?.preferences && Object.keys(guest.preferences).length > 0 && (
                  <div className="bg-slate-50 border border-slate-200 rounded-md px-2 py-1.5" data-testid="ops-preferences">
                    <p className="text-[10px] text-slate-500 mb-0.5">Tercihler</p>
                    <div className="flex flex-wrap gap-1">
                      {Object.entries(guest.preferences).slice(0, 3).map(([k, v]) => (
                        <span key={k} className="text-[10px] bg-white border rounded px-1.5 py-0.5 text-slate-600">
                          {k}: {typeof v === 'boolean' ? (v ? 'Evet' : 'Hayir') : String(v)}
                        </span>
                      ))}
                    </div>
                  </div>
                )}
              </div>
              <div className="border rounded-lg p-3 bg-white space-y-2">
                <div className="flex justify-between text-xs"><span className="text-gray-500">TOPLAM</span><span className="font-bold">{fmtTL(summary?.total_amount)} TL</span></div>
                <div className="flex justify-between text-xs"><span className="text-gray-500">ODENEN</span><span className="font-bold text-emerald-600">{fmtTL(summary?.total_payments)} TL</span></div>
                {(summary?.total_deposits || 0) > 0 && <div className="flex justify-between text-xs"><span className="text-gray-500">DEPOZITO</span><span className="font-bold text-blue-600">{fmtTL(summary?.total_deposits)} TL</span></div>}
                <div className="border-t pt-2 flex justify-between text-xs"><span className="text-gray-500">BAKIYE</span><span className={`font-bold ${(summary?.balance || 0) > 0 ? 'text-red-600' : 'text-green-600'}`}>{fmtTL(summary?.balance)} TL</span></div>
              </div>
              <div className="space-y-1.5">
                {(booking?.status === 'confirmed' || booking?.status === 'guaranteed') && (
                  <Button size="sm" variant="outline" onClick={async () => {
                    try {
                      await axios.post(`/frontdesk/checkin/${bookingId}?create_folio=true&force_clean=true`);
                      toast.success('Giriş yapıldı'); loadData();
                    } catch (e) { toast.error('Hata: ' + (e.response?.data?.detail || e.message)); }
                  }} className="w-full h-8 text-xs justify-start bg-emerald-50 text-emerald-700 border-emerald-300 hover:bg-emerald-100"><LogIn className="w-3 h-3 mr-2" /> Giriş Yap</Button>
                )}
                {booking?.status === 'checked_in' && (
                  <Button size="sm" variant="outline" onClick={async () => {
                    if (!window.confirm('Çıkış yapılsın mı?')) return;
                    try {
                      const res = await axios.post(`/frontdesk/checkout/${bookingId}?auto_close_folios=true`);
                      if (res.data.total_balance > 0.01) {
                        toast.warning(`Açık bakiye ile çıkış yapıldı: ${res.data.total_balance.toFixed(2)}`);
                      } else {
                        toast.success('Çıkış yapıldı');
                      }
                      loadData();
                    } catch (e) {
                      const detail = e.response?.data?.detail || e.message;
                      if (e.response?.status === 402) {
                        toast.error(`Açık bakiye var: ${detail}. Lütfen önce ödeme alınız.`);
                      } else {
                        toast.error('Hata: ' + detail);
                      }
                    }
                  }} className="w-full h-8 text-xs justify-start bg-blue-50 text-blue-700 border-blue-300 hover:bg-blue-100"><LogOut className="w-3 h-3 mr-2" /> Çıkış Yap</Button>
                )}
                <Button size="sm" variant="outline" onClick={() => action(`/api/pms/reservations/${bookingId}/early-checkin`, { extra_charge: 0 }, 'Erken giriş yapıldı')} className="w-full h-8 text-xs justify-start"><LogIn className="w-3 h-3 mr-2" /> Erken Giriş</Button>
                <Button size="sm" variant="outline" onClick={() => action(`/api/pms/reservations/${bookingId}/late-checkout`, { extra_charge: 0 }, 'Geç çıkış kaydedildi')} className="w-full h-8 text-xs justify-start"><LogOut className="w-3 h-3 mr-2" /> Geç Çıkış</Button>
                <Button size="sm" variant="outline" onClick={async () => {
                  const vip = data?.guest?.vip_status || false;
                  try { await axios.put(`/pms/reservations/${bookingId}/vip-status?vip=${!vip}`); toast.success(vip ? 'VIP kaldırıldı' : 'VIP yapıldı'); loadData(); }
                  catch (e) { toast.error('Hata'); }
                }} className="w-full h-8 text-xs justify-start"><Star className="w-3 h-3 mr-2" /> {data?.guest?.vip_status ? 'VIP Kaldır' : 'VIP Yap'}</Button>
                <Button size="sm" variant="outline" onClick={() => { if (window.confirm('No-show olarak işaretlensin mi?')) action(`/api/pms/reservations/${bookingId}/mark-noshow`, {}, 'No-show işaretlendi'); }} className="w-full h-8 text-xs justify-start text-red-600 border-red-200 hover:bg-red-50"><AlertTriangle className="w-3 h-3 mr-2" /> No-Show</Button>
                <Button size="sm" variant="outline" onClick={() => setActiveTab('cancel')} className="w-full h-8 text-xs justify-start text-red-600 border-red-200 hover:bg-red-50" data-testid="btn-cancel-reservation"><X className="w-3 h-3 mr-2" /> İptal Et</Button>
                <Button size="sm" variant="outline" onClick={() => setActiveTab('voucher')} className="w-full h-8 text-xs justify-start text-teal-600 border-teal-200 hover:bg-teal-50" data-testid="btn-voucher"><FileText className="w-3 h-3 mr-2" /> Voucher</Button>
              </div>
            </div>
          </div>

          {/* Main Content */}
          <div className="flex-1 overflow-y-auto">
            <Tabs value={activeTab} onValueChange={setActiveTab} className="h-full flex flex-col">
              <TabsList className="border-b rounded-none h-auto p-0 bg-white flex-shrink-0 justify-start gap-0 overflow-x-auto">
                {tabs.map(tab => (
                  <TabsTrigger key={tab.id} value={tab.id}
                    className="rounded-none border-b-2 border-transparent data-[state=active]:border-orange-500 data-[state=active]:text-orange-700 data-[state=active]:bg-transparent data-[state=active]:shadow-none px-4 py-2.5 text-xs font-medium text-gray-500 hover:text-gray-700 transition-colors whitespace-nowrap">
                    <tab.icon className="w-3.5 h-3.5 mr-1.5" />{tab.label}
                  </TabsTrigger>
                ))}
              </TabsList>
              <div className="flex-1 overflow-y-auto p-6">
                <TabsContent value="general" className="mt-0"><GeneralInfoTab booking={booking} guest={guest} room={room} company={company} onGuestUpdate={loadData} /></TabsContent>
                <TabsContent value="guests" className="mt-0"><GuestsTab guests={guests} booking={booking} onRefresh={loadData} /></TabsContent>
                <TabsContent value="online_payment" className="mt-0"><OnlinePaymentTab booking={booking} onRefresh={loadData} /></TabsContent>
                <TabsContent value="vcc" className="mt-0"><VCCTab booking={booking} onRefresh={loadData} /></TabsContent>
                <TabsContent value="folios" className="mt-0"><FoliosTab folios={folios} charges={charges} payments={payments} extra_charges={extra_charges} summary={summary} booking={booking} onRefresh={loadData} onSwitchTab={setActiveTab} /></TabsContent>
                <TabsContent value="daily_rates" className="mt-0"><DailyRatesTab dailyRates={daily_rates} booking={booking} onRefresh={loadData} /></TabsContent>
                <TabsContent value="extras" className="mt-0"><ExtraChargesTab extra_charges={extra_charges} charges={charges} booking={booking} onRefresh={loadData} allBookings={allBookings} /></TabsContent>
                <TabsContent value="room_change" className="mt-0"><RoomChangeTab booking={booking} room={room} roomMoves={room_moves} onRefresh={loadData} /></TabsContent>
                <TabsContent value="cancel" className="mt-0"><CancelTab booking={booking} bookingId={bookingId} onRefresh={loadData} onClose={onClose} /></TabsContent>
                <TabsContent value="voucher" className="mt-0"><VoucherTab booking={booking} bookingId={bookingId} /></TabsContent>
                <TabsContent value="invoice" className="mt-0"><InvoiceTab booking={booking} bookingId={bookingId} /></TabsContent>
                <TabsContent value="deposits" className="mt-0"><DepositsTab deposits={deposits} booking={booking} onRefresh={loadData} /></TabsContent>
                <TabsContent value="communication" className="mt-0"><CommunicationTab booking={booking} onRefresh={loadData} communicationLogs={communication_logs} /></TabsContent>
                <TabsContent value="notes" className="mt-0"><NotesTab notes={notes} booking={booking} onRefresh={loadData} /></TabsContent>
                <TabsContent value="history" className="mt-0"><HistoryTab history={history} roomMoves={room_moves} /></TabsContent>
              </div>
            </Tabs>
          </div>
        </div>
      </div>
    </div>
  );
}
