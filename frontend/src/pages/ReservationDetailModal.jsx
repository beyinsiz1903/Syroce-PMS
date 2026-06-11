import { useState, useEffect, useCallback } from 'react';
import axios from 'axios';
import { toast } from 'sonner';
import { Tabs, TabsContent, TabsList, TabsTrigger } from '@/components/ui/tabs';
import { Button } from '@/components/ui/button';
import { Badge } from '@/components/ui/badge';
import { DropdownMenu, DropdownMenuContent, DropdownMenuItem, DropdownMenuTrigger } from '@/components/ui/dropdown-menu';
import {
  X, Calendar, DollarSign, FileText, Users, Receipt,
  History, MessageSquare, Star, AlertTriangle,
  LogIn, LogOut, Repeat2, Shield, Mail, Loader2, CreditCard,
  ChevronDown, DoorOpen, Globe, Clock,
} from 'lucide-react';

import { API, fmtTL, fmtDateTime, statusLabel, translateValue, bookingRef, Avatar } from './reservation-detail/helpers';
import { GeneralInfoTab, GuestsTab } from './reservation-detail/InfoTabs';
import { FoliosTab } from './reservation-detail/FoliosTab';
import { DailyRatesTab, ExtraChargesTab } from './reservation-detail/PricingTabs';
import { RoomChangeTab, CancelTab } from './reservation-detail/OperationTabs';
import { CommunicationTab, NotesTab, HistoryTab } from './reservation-detail/GuestServiceTabs';
import { DepositsTab, VoucherTab, InvoiceTab } from './reservation-detail/DocumentTabs';
import { OnlinePaymentTab } from './reservation-detail/OnlinePaymentTab';
import { VCCTab } from './reservation-detail/VCCTab';
import GuestAlertModal from '@/components/GuestAlertModal';
import IdPhotoViewerButton from '@/components/IdPhotoViewerButton';

import { confirmDialog } from '@/lib/dialogs';
import { useTranslation } from 'react-i18next';

// Statü için pill rengi (sıkı palet: amber/emerald/rose/slate)
const STATUS_PILL = {
  confirmed: 'bg-emerald-500/15 text-emerald-100 border border-emerald-400/30',
  guaranteed: 'bg-emerald-500/15 text-emerald-100 border border-emerald-400/30',
  checked_in: 'bg-amber-500/20 text-amber-100 border border-amber-400/30',
  in_house: 'bg-amber-500/20 text-amber-100 border border-amber-400/30',
  checked_out: 'bg-slate-400/20 text-slate-100 border border-slate-300/30',
  cancelled: 'bg-rose-500/20 text-rose-100 border border-rose-400/30',
  no_show: 'bg-rose-500/20 text-rose-100 border border-rose-400/30',
  pending: 'bg-slate-400/20 text-slate-100 border border-slate-300/30',
};

export default function ReservationDetailModal({ bookingId, onClose, allBookings }) {
  const { t } = useTranslation();
  const [data, setData] = useState(null);
  const [loading, setLoading] = useState(true);
  const [activeTab, setActiveTab] = useState('general');
  const [checkinAlertOpen, setCheckinAlertOpen] = useState(false);

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

  const action = async (url, body = {}, msg = 'İşlem tamamlandı') => {
    try { await axios.post(`${API}${url}`, body); toast.success(msg); loadData(); }
    catch (e) { toast.error('Hata: ' + (e.response?.data?.detail || e.message)); }
  };

  if (loading) return (
    <div className="fixed inset-0 z-[60] flex items-center justify-center bg-black/50">
      <div className="bg-white rounded-2xl p-8 flex flex-col items-center gap-3">
        <Loader2 className="w-8 h-8 animate-spin text-amber-600" />
        <span className="text-sm text-slate-500">{t('cm.pages_ReservationDetailModal.yukleniyor')}</span>
      </div>
    </div>
  );

  if (!data) return null;

  const { booking, guest, room, company, folios, charges, payments, extra_charges, notes, history, room_moves, daily_rates, guests, summary, communication_logs, deposits } = data;

  const balance = summary?.balance || 0;
  const hasOpenBalance = balance > 0;

  // Birincil sekmeler — günlük kullanımda en sık ihtiyaç duyulanlar
  const primaryTabs = [
    { id: 'general', label: 'Genel Bilgiler', icon: FileText },
    { id: 'guests', label: `Misafirler${guests?.length ? ` (${guests.length})` : ''}`, icon: Users },
    { id: 'folios', label: 'Folyolar', icon: DollarSign },
    { id: 'online_payment', label: 'Online Ödeme', icon: CreditCard },
    { id: 'extras', label: 'Ek Ücretler', icon: Receipt },
    { id: 'invoice', label: 'Fatura', icon: Receipt },
    { id: 'history', label: 'Geçmiş', icon: History },
  ];
  // İkincil sekmeler — "Daha Fazla" menüsünde gizli
  const moreTabs = [
    { id: 'vcc', label: 'Sanal Kart', icon: Shield },
    { id: 'daily_rates', label: 'Günlük Fiyatlar', icon: Calendar },
    { id: 'room_change', label: 'Oda Değiştir', icon: Repeat2 },
    { id: 'cancel', label: 'İptal Et', icon: AlertTriangle },
    { id: 'voucher', label: 'Voucher', icon: FileText },
    { id: 'deposits', label: `Depozito${deposits?.length ? ` (${deposits.length})` : ''}`, icon: Shield },
    { id: 'communication', label: `İletişim${communication_logs?.length ? ` (${communication_logs.length})` : ''}`, icon: Mail },
    { id: 'notes', label: `Notlar${notes?.length ? ` (${notes.length})` : ''}`, icon: MessageSquare },
  ];
  const activeMore = moreTabs.find(t => t.id === activeTab);

  const refLabel = bookingRef(booking);
  const channelLabel = translateValue(booking?.source_channel || booking?.channel) || 'Doğrudan';
  const guestName = guest?.name || booking?.guest_name || 'Misafir';

  return (
    <div className="fixed inset-0 z-[60]" data-testid="reservation-detail-modal">
      <div className="absolute inset-0 bg-black/50 backdrop-blur-sm" />
      <div className="absolute inset-2 md:inset-4 lg:inset-6 bg-white rounded-2xl shadow-2xl flex flex-col overflow-hidden">
        {/* Header — sade, marka rengiyle */}
        <div className="flex items-center justify-between px-6 py-3 border-b bg-gradient-to-r from-slate-900 to-slate-800">
          <div className="flex items-center gap-3 min-w-0">
            <div className="flex items-baseline gap-2 min-w-0">
              <h2 className="text-white font-semibold text-base whitespace-nowrap">{t('cm.pages_ReservationDetailModal.rezervasyon')}</h2>
              <span className="text-amber-300 font-mono text-sm tracking-wide truncate">{refLabel}</span>
            </div>
            <Badge className={`text-[11px] h-5 px-2 ${STATUS_PILL[booking?.status] || STATUS_PILL.pending}`}>
              {statusLabel(booking?.status)}
            </Badge>
            {booking?.group_booking_id && (
              <Badge className="bg-amber-400/20 text-amber-100 border border-amber-400/30 text-[11px] h-5 px-2">Grup</Badge>
            )}
            {hasOpenBalance && (
              <Badge className="bg-rose-500/20 text-rose-100 border border-rose-400/30 text-[11px] h-5 px-2 hidden md:inline-flex">
                <AlertTriangle className="w-3 h-3 mr-1" /> {t('cm.pages_ReservationDetailModal.bakiye')} {fmtTL(balance)} TL
              </Badge>
            )}
          </div>
          <button
            onClick={onClose}
            className="text-white/70 hover:text-white hover:bg-white/10 rounded-full p-2 transition-colors"
            data-testid="close-reservation-detail"
            aria-label={t('cm.pages_ReservationDetailModal.kapat')}
          ><X className="w-5 h-5" /></button>
        </div>

        <div className="flex flex-1 overflow-hidden">
          {/* Sol panel — sticky footer'lı */}
          <aside className="w-72 border-r bg-slate-50 flex-shrink-0 flex flex-col">
            <div className="flex-1 overflow-y-auto px-4 pt-4 pb-2 space-y-4">
              {/* Misafir başlığı */}
              <div className="flex flex-col items-center text-center gap-2">
                <Avatar name={guestName} size="xl" />
                <div className="min-w-0 w-full">
                  <div className="font-semibold text-slate-800 text-sm truncate" title={guestName}>{guestName}</div>
                  {guest?.vip_status && (
                    <Badge className="mt-1 bg-amber-100 text-amber-700 border-amber-200 text-[10px] h-4 px-1.5">
                      <Star className="w-2.5 h-2.5 mr-0.5" /> VIP
                    </Badge>
                  )}
                </div>
              </div>

              {/* Anahtar bilgiler — kompakt, şık */}
              <div className="bg-white border border-slate-200 rounded-xl p-3 space-y-2.5 shadow-sm">
                <div className="flex items-center gap-2 text-xs">
                  <DoorOpen className="w-3.5 h-3.5 text-slate-400 shrink-0" />
                  <span className="text-slate-500">{t('cm.pages_ReservationDetailModal.oda')}</span>
                  <span className="ml-auto font-semibold text-slate-800">{booking?.room_number || room?.room_number || '—'}</span>
                </div>
                <div className="flex items-center gap-2 text-xs">
                  <Globe className="w-3.5 h-3.5 text-slate-400 shrink-0" />
                  <span className="text-slate-500">Kanal</span>
                  <span className="ml-auto font-medium text-slate-700 truncate">{channelLabel}</span>
                </div>

                {/* Giriş → Çıkış tek satır görsel blok */}
                {(() => {
                  const ci = booking?.check_in ? new Date(booking.check_in) : null;
                  const co = booking?.check_out ? new Date(booking.check_out) : null;
                  const nights = ci && co ? Math.max(1, Math.ceil((co - ci) / 86400000)) : 0;
                  const fmt = (d) => d ? d.toLocaleDateString('tr-TR', { day: '2-digit', month: 'short' }) : '—';
                  const dow = (d) => d ? d.toLocaleDateString('tr-TR', { weekday: 'short' }) : '';
                  return (
                    <div className="pt-2 border-t border-slate-100">
                      <div className="flex items-center justify-between gap-2">
                        <div className="text-center flex-1">
                          <div className="text-[9px] text-slate-400 uppercase tracking-wider">{t('cm.pages_ReservationDetailModal.giris')}</div>
                          <div className="text-[13px] font-semibold text-slate-800 leading-tight">{fmt(ci)}</div>
                          <div className="text-[10px] text-slate-400 capitalize">{dow(ci)}</div>
                        </div>
                        <div className="flex flex-col items-center text-amber-600">
                          <div className="text-[9px] font-medium leading-none">{nights} gece</div>
                          <div className="text-base leading-none mt-0.5">→</div>
                        </div>
                        <div className="text-center flex-1">
                          <div className="text-[9px] text-slate-400 uppercase tracking-wider">{t('cm.pages_ReservationDetailModal.cikis')}</div>
                          <div className="text-[13px] font-semibold text-slate-800 leading-tight">{fmt(co)}</div>
                          <div className="text-[10px] text-slate-400 capitalize">{dow(co)}</div>
                        </div>
                      </div>
                    </div>
                  );
                })()}

                {booking?.created_at && (
                  <div className="flex items-center gap-1.5 pt-2 border-t border-slate-100 text-[10px] text-slate-400">
                    <Clock className="w-3 h-3 shrink-0" />
                    <span>{t('cm.pages_ReservationDetailModal.olusturuldu')}</span>
                    <span className="ml-auto" title={fmtDateTime(booking.created_at)}>
                      {new Date(booking.created_at).toLocaleDateString('tr-TR', { day: '2-digit', month: 'short' })}
                    </span>
                  </div>
                )}
              </div>

              {/* Operasyonel Durum — yalnızca anlamlı olanlar */}
              <div className="space-y-1.5" data-testid="reservation-ops-panel">
                <p className="text-[10px] font-semibold text-slate-400 uppercase tracking-wider">{t('cm.pages_ReservationDetailModal.operasyonel_durum')}</p>
                {hasOpenBalance ? (
                  <div className="flex items-center gap-1.5 bg-rose-50 border border-rose-200 rounded-md px-2 py-1.5" data-testid="ops-payment-alert">
                    <AlertTriangle className="w-3 h-3 text-rose-500 flex-shrink-0" />
                    <span className="text-[11px] text-rose-700 font-medium">{t('cm.pages_ReservationDetailModal.odeme_bekleniyor')} {fmtTL(balance)} TL</span>
                  </div>
                ) : (
                  <div className="flex items-center gap-1.5 bg-emerald-50 border border-emerald-200 rounded-md px-2 py-1.5" data-testid="ops-payment-ok">
                    <Shield className="w-3 h-3 text-emerald-500 flex-shrink-0" />
                    <span className="text-[11px] text-emerald-700">{t('cm.pages_ReservationDetailModal.odeme_tamam')}</span>
                  </div>
                )}
                {room && (room.status === 'dirty' || room.status === 'cleaning') && (
                  <div className="flex items-center gap-1.5 bg-amber-50 border border-amber-200 rounded-md px-2 py-1.5" data-testid="ops-room-dirty">
                    <AlertTriangle className="w-3 h-3 text-amber-500 flex-shrink-0" />
                    <span className="text-[11px] text-amber-700 font-medium">{t('cm.pages_ReservationDetailModal.oda_e4b47')} {room.status === 'cleaning' ? 'temizleniyor' : 'kirli'}</span>
                  </div>
                )}
                {room && room.status === 'available' && (
                  <div className="flex items-center gap-1.5 bg-emerald-50 border border-emerald-200 rounded-md px-2 py-1.5" data-testid="ops-room-ready">
                    <Shield className="w-3 h-3 text-emerald-500 flex-shrink-0" />
                    <span className="text-[11px] text-emerald-700">{t('cm.pages_ReservationDetailModal.oda_hazir')}</span>
                  </div>
                )}
                {guest?.total_stays > 1 && (
                  <div className="flex items-center gap-1.5 bg-amber-50 border border-amber-200 rounded-md px-2 py-1.5" data-testid="ops-repeat">
                    <Repeat2 className="w-3 h-3 text-amber-600 flex-shrink-0" />
                    <span className="text-[11px] text-amber-700">{guest.total_stays}. konaklama</span>
                  </div>
                )}
                {guest?.preferences && Object.keys(guest.preferences).length > 0 && (
                  <div className="bg-white border border-slate-200 rounded-md px-2 py-1.5" data-testid="ops-preferences">
                    <p className="text-[10px] text-slate-500 mb-0.5">Tercihler</p>
                    <div className="flex flex-wrap gap-1">
                      {Object.entries(guest.preferences).slice(0, 3).map(([k, v]) => (
                        <span key={k} className="text-[10px] bg-slate-50 border border-slate-200 rounded px-1.5 py-0.5 text-slate-600">
                          {k}: {typeof v === 'boolean' ? (v ? 'Evet' : 'Hayır') : String(v)}
                        </span>
                      ))}
                    </div>
                  </div>
                )}
              </div>

              {/* Finansal özet — bakiye vurgulu */}
              <div className={`rounded-xl p-3 space-y-1.5 shadow-sm ${
                hasOpenBalance ? 'bg-rose-50 border-2 border-rose-300' : 'bg-white border border-slate-200'
              }`} data-testid="financial-summary-card">
                <div className="flex justify-between text-xs">
                  <span className="text-slate-500">{t('cm.pages_ReservationDetailModal.toplam')}</span>
                  <span className="font-semibold text-slate-800">{fmtTL(summary?.total_amount)} TL</span>
                </div>
                <div className="flex justify-between text-xs">
                  <span className="text-slate-500">{t('cm.pages_ReservationDetailModal.odenen')}</span>
                  <span className="font-semibold text-emerald-600">{fmtTL(summary?.total_payments)} TL</span>
                </div>
                {(summary?.total_deposits || 0) > 0 && (
                  <div className="flex justify-between text-xs">
                    <span className="text-slate-500">Depozito</span>
                    <span className="font-semibold text-sky-600">{fmtTL(summary?.total_deposits)} TL</span>
                  </div>
                )}
                <div className={`pt-2 border-t flex justify-between items-baseline ${hasOpenBalance ? 'border-rose-200' : 'border-slate-200'}`}>
                  <span className={`text-[11px] font-semibold uppercase tracking-wider ${hasOpenBalance ? 'text-rose-700' : 'text-slate-500'}`}>{t('cm.pages_ReservationDetailModal.bakiye_33769')}</span>
                  <span className={`text-base font-bold ${hasOpenBalance ? 'text-rose-700' : 'text-emerald-600'}`}>{fmtTL(balance)} TL</span>
                </div>
              </div>

              {/* İkincil eylemler */}
              <div className="space-y-1.5">
                <IdPhotoViewerButton
                  bookingId={bookingId}
                  guestName={guestName}
                  onlineCheckinCompleted={booking?.online_checkin_completed}
                  idPhotoUploaded={booking?.online_checkin_id_photo_uploaded}
                  className="w-full h-8 text-xs justify-start bg-white text-slate-700 border-slate-300 hover:bg-slate-50"
                />
                <Button size="sm" variant="outline" onClick={() => action(`/api/pms/reservations/${bookingId}/early-checkin`, { extra_charge: 0 }, 'Erken giriş yapıldı')} className="w-full h-8 text-xs justify-start bg-white border-slate-300 hover:bg-slate-50">
                  <LogIn className="w-3 h-3 mr-2" /> {t('cm.pages_ReservationDetailModal.erken_giris')}
                </Button>
                <Button size="sm" variant="outline" onClick={() => action(`/api/pms/reservations/${bookingId}/late-checkout`, { extra_charge: 0 }, 'Geç çıkış kaydedildi')} className="w-full h-8 text-xs justify-start bg-white border-slate-300 hover:bg-slate-50">
                  <LogOut className="w-3 h-3 mr-2" /> {t('cm.pages_ReservationDetailModal.gec_cikis')}
                </Button>
                <Button size="sm" variant="outline" onClick={async () => {
                  const vip = data?.guest?.vip_status || false;
                  try {
                    await axios.put(`/pms/reservations/${bookingId}/vip-status?vip=${!vip}`);
                    toast.success(vip ? 'VIP kaldırıldı' : 'VIP yapıldı');
                    loadData();
                  } catch (_e) { toast.error('Hata'); }
                }} className="w-full h-8 text-xs justify-start bg-white border-slate-300 hover:bg-slate-50">
                  <Star className="w-3 h-3 mr-2" /> {data?.guest?.vip_status ? 'VIP Kaldır' : 'VIP Yap'}
                </Button>
                <Button size="sm" variant="outline" onClick={async () => { if (await confirmDialog({ message: 'No-show olarak işaretlensin mi?', variant: 'danger' })) action(`/api/pms/reservations/${bookingId}/mark-noshow`, {}, 'No-show işaretlendi'); }} className="w-full h-8 text-xs justify-start text-rose-600 border-rose-200 hover:bg-rose-50">
                  <AlertTriangle className="w-3 h-3 mr-2" /> No-Show
                </Button>
                <Button size="sm" variant="outline" onClick={() => setActiveTab('cancel')} className="w-full h-8 text-xs justify-start text-rose-600 border-rose-200 hover:bg-rose-50" data-testid="btn-cancel-reservation">
                  <X className="w-3 h-3 mr-2" /> {t('cm.pages_ReservationDetailModal.iptal_et')}
                </Button>
                <Button size="sm" variant="outline" onClick={() => setActiveTab('voucher')} className="w-full h-8 text-xs justify-start bg-white border-slate-300 hover:bg-slate-50" data-testid="btn-voucher">
                  <FileText className="w-3 h-3 mr-2" /> Voucher
                </Button>
              </div>
            </div>

            {/* Sticky footer — birincil eylem (Giriş/Çıkış) hep görünür */}
            {(booking?.status === 'confirmed' || booking?.status === 'guaranteed') && (
              <div className="border-t bg-white px-4 py-3 shadow-[0_-4px_12px_rgba(0,0,0,0.04)]">
                <Button
                  size="sm"
                  onClick={() => setCheckinAlertOpen(true)}
                  className="w-full h-10 bg-emerald-600 hover:bg-emerald-700 text-white font-medium shadow-sm"
                  data-testid="btn-checkin"
                >
                  <LogIn className="w-4 h-4 mr-2" /> {t('cm.pages_ReservationDetailModal.giris_yap')}
                </Button>
              </div>
            )}
            {booking?.status === 'checked_in' && (
              <div className="border-t bg-white px-4 py-3 shadow-[0_-4px_12px_rgba(0,0,0,0.04)]">
                <Button
                  size="sm"
                  onClick={async () => {
                    if (!await confirmDialog({ message: 'Çıkış yapılsın mı?', variant: 'danger' })) return;
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
                  }}
                  className="w-full h-10 bg-amber-600 hover:bg-amber-700 text-white font-medium shadow-sm"
                  data-testid="btn-checkout"
                >
                  <LogOut className="w-4 h-4 mr-2" /> {t('cm.pages_ReservationDetailModal.cikis_yap')}
                </Button>
              </div>
            )}
          </aside>

          {/* Ana içerik */}
          <div className="flex-1 overflow-y-auto bg-white">
            <Tabs value={activeTab} onValueChange={setActiveTab} className="h-full flex flex-col">
              <TabsList className="border-b rounded-none h-auto p-0 bg-white flex-shrink-0 justify-start gap-0 overflow-x-auto sticky top-0 z-10">
                {primaryTabs.map(tab => (
                  <TabsTrigger
                    key={tab.id}
                    value={tab.id}
                    className="rounded-none border-b-2 border-transparent data-[state=active]:border-amber-600 data-[state=active]:text-amber-700 data-[state=active]:bg-amber-50/40 data-[state=active]:shadow-none px-4 py-2.5 text-xs font-medium text-slate-500 hover:text-slate-800 hover:bg-slate-50 transition-colors whitespace-nowrap"
                  >
                    <tab.icon className="w-3.5 h-3.5 mr-1.5" />{tab.label}
                  </TabsTrigger>
                ))}
                {/* Daha Fazla menüsü */}
                <DropdownMenu>
                  <DropdownMenuTrigger asChild>
                    <button
                      type="button"
                      className={`rounded-none border-b-2 px-4 py-2.5 text-xs font-medium hover:text-slate-800 hover:bg-slate-50 transition-colors whitespace-nowrap inline-flex items-center ${
                        activeMore ? 'border-amber-600 text-amber-700 bg-amber-50/40' : 'border-transparent text-slate-500'
                      }`}
                    >
                      {activeMore ? (<><activeMore.icon className="w-3.5 h-3.5 mr-1.5" />{activeMore.label}</>) : (<>Daha Fazla</>)}
                      <ChevronDown className="w-3.5 h-3.5 ml-1.5 opacity-70" />
                    </button>
                  </DropdownMenuTrigger>
                  <DropdownMenuContent align="end" className="w-56 z-[70]">
                    {moreTabs.map(tab => (
                      <DropdownMenuItem
                        key={tab.id}
                        onClick={() => setActiveTab(tab.id)}
                        className={`text-xs cursor-pointer ${activeTab === tab.id ? 'bg-amber-50 text-amber-700' : ''}`}
                      >
                        <tab.icon className="w-3.5 h-3.5 mr-2" />{tab.label}
                      </DropdownMenuItem>
                    ))}
                  </DropdownMenuContent>
                </DropdownMenu>
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

      <GuestAlertModal
        guestId={guest?.id || booking?.guest_id}
        open={checkinAlertOpen}
        onClose={() => setCheckinAlertOpen(false)}
        confirmLabel="Girişi Onayla"
        onConfirm={async () => {
          setCheckinAlertOpen(false);
          try {
            await axios.post(`/frontdesk/checkin/${bookingId}?create_folio=true&force_clean=true`);
            toast.success('Giriş yapıldı'); loadData();
          } catch (e) { toast.error('Hata: ' + (e.response?.data?.detail || e.message)); }
        }}
      />
    </div>
  );
}
