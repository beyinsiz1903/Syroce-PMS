import React, { useState, useCallback, useRef, useEffect } from 'react';
import axios from 'axios';
import { Dialog, DialogContent, DialogDescription, DialogHeader, DialogTitle } from '@/components/ui/dialog';
import { Button } from '@/components/ui/button';
import { Input } from '@/components/ui/input';
import { Label } from '@/components/ui/label';
import { Badge } from '@/components/ui/badge';
import { Textarea } from '@/components/ui/textarea';
import { Select, SelectContent, SelectItem, SelectTrigger, SelectValue } from '@/components/ui/select';
import { Plus, Trash2, User, Search, UserCheck, UserPlus } from 'lucide-react';
import { useTranslation } from 'react-i18next';
import { findOccupancyRule } from '@/utils/occupancyPricing';
import { cachedTenantCurrency, formatCurrency } from '@/lib/currency';
const BookingDialog = ({
  open,
  onClose,
  guests,
  rooms,
  companies,
  ratePlans,
  packages,
  newBooking,
  setNewBooking,
  multiRoomBooking,
  occupancyPricingRules = {},
  handleCreateBooking,
  handleCompanySelect,
  handleContractedRateSelect,
  handleChildrenChange,
  handleChildAgeChange,
  addRoomToMultiBooking,
  removeRoomFromMultiBooking,
  updateMultiRoomField,
  updateMultiRoomChildrenAges,
  updateMultiRoomChildAge,
  isLite,
  setOpenDialog
}) => {
  const {
    t
  } = useTranslation();
  // Guest search state
  const [guestSearchQuery, setGuestSearchQuery] = useState('');
  const [guestSearchResults, setGuestSearchResults] = useState([]);
  const [guestSearchLoading, setGuestSearchLoading] = useState(false);
  const [selectedGuest, setSelectedGuest] = useState(null);
  const [showGuestDropdown, setShowGuestDropdown] = useState(false);
  const guestSearchTimerRef = useRef(null);
  const guestSearchController = useRef(null);
  const [submitting, setSubmitting] = useState(false);
  const submitLock = useRef(false);
  useEffect(() => () => { clearTimeout(guestSearchTimerRef.current); guestSearchController.current?.abort(); }, []);

  // Reset guest search state when dialog opens/closes
  useEffect(() => {
    if (!open) {
      clearTimeout(guestSearchTimerRef.current);
      guestSearchController.current?.abort();
      setGuestSearchLoading(false);
      setGuestSearchQuery('');
      setGuestSearchResults([]);
      setSelectedGuest(null);
      setShowGuestDropdown(false);
    }
  }, [open]);

  // Guest search with debounce
  const handleGuestSearch = useCallback(query => {
    setGuestSearchQuery(query);
    setSelectedGuest(null);
    setNewBooking(prev => ({
      ...prev,
      guest_id: ''
    }));
    if (guestSearchTimerRef.current) clearTimeout(guestSearchTimerRef.current);
    guestSearchController.current?.abort();
    const controller = new AbortController();
    guestSearchController.current = controller;
    if (query.trim().length < 2) {
      setGuestSearchLoading(false);
      setGuestSearchResults([]);
      setShowGuestDropdown(false);
      return;
    }
    setGuestSearchLoading(true);
    guestSearchTimerRef.current = setTimeout(async () => {
      try {
        const res = await axios.get(`/pms/guests/search?q=${encodeURIComponent(query.trim())}&limit=10`, { signal: controller.signal });
        if (controller.signal.aborted) return;
        setGuestSearchResults(res.data || []);
        setShowGuestDropdown(true);
      } catch {
        if (controller.signal.aborted) return;
        setGuestSearchResults([]);
      } finally {
        if (!controller.signal.aborted) setGuestSearchLoading(false);
      }
    }, 300);
  }, [setNewBooking]);

  // Select an existing guest from search results
  const handleSelectGuest = useCallback(guest => {
    clearTimeout(guestSearchTimerRef.current); guestSearchController.current?.abort(); setGuestSearchLoading(false);
    setSelectedGuest(guest);
    setGuestSearchQuery(guest.name);
    setShowGuestDropdown(false);
    setGuestSearchResults([]);
    setNewBooking(prev => ({
      ...prev,
      guest_id: guest.id
    }));
  }, [setNewBooking]);

  // Clear selected guest
  const handleClearGuest = useCallback(() => {
    clearTimeout(guestSearchTimerRef.current); guestSearchController.current?.abort(); setGuestSearchLoading(false);
    setSelectedGuest(null);
    setGuestSearchQuery('');
    setGuestSearchResults([]);
    setShowGuestDropdown(false);
    setNewBooking(prev => ({
      ...prev,
      guest_id: ''
    }));
  }, [setNewBooking]);
  return <Dialog open={open} onOpenChange={o => !o && !submitLock.current && onClose()}>
  <DialogContent className="max-w-4xl max-h-[94dvh] overflow-y-auto p-4 sm:p-6">
    <DialogHeader>
      <DialogTitle>{t('cm.components_pms_BookingDialog.yeni_rezervasyon_olustur')}</DialogTitle>
      <DialogDescription>{t('cm.components_pms_BookingDialog.rezervasyon_bilgilerini_asagiya_girin')}</DialogDescription>
    </DialogHeader>
    <form onSubmit={async (e) => { e.preventDefault(); if (submitLock.current) return; submitLock.current = true; setSubmitting(true); try { await handleCreateBooking(e, selectedGuest ? null : guestSearchQuery); } finally { submitLock.current = false; setSubmitting(false); } }} className="space-y-6">
      {/* Check-in and Check-out */}
      <div className="grid grid-cols-1 sm:grid-cols-3 gap-4">
        <div>
          <Label>{t('experience.booking.checkIn', "Giriş tarihi *")}</Label>
          <Input aria-label={t("experience.booking.checkIn", "Giriş tarihi *")} type="date" value={newBooking.check_in} onChange={e => setNewBooking(prev => ({
              ...prev,
              check_in: e.target.value
            }))} required />
        </div>
        <div>
          <Label>{t('experience.booking.checkOut', "Çıkış tarihi *")}</Label>
          <Input aria-label={t("experience.booking.checkOut", "Çıkış tarihi *")} min={newBooking.check_in || undefined} type="date" value={newBooking.check_out} onChange={e => setNewBooking(prev => ({
              ...prev,
              check_out: e.target.value
            }))} required />
        </div>
        <div>
          <Label>Para Birimi *</Label>
          <Select value={newBooking.currency || cachedTenantCurrency()} onValueChange={currency => setNewBooking(prev => ({ ...prev, currency }))}>
            <SelectTrigger data-testid="booking-dialog-currency"><SelectValue /></SelectTrigger>
            <SelectContent>
              {['TRY', 'EUR', 'USD', 'GBP'].map(code => <SelectItem key={code} value={code}>{code}</SelectItem>)}
            </SelectContent>
          </Select>
        </div>
      </div>

      {/* Guest search */}
      <div className="grid grid-cols-1 sm:grid-cols-2 gap-4 items-end">
        <div>
          <Label>{t('cm.components_pms_BookingDialog.misafir')}</Label>
          {selectedGuest ? <div className="mt-1 flex items-center gap-2 bg-blue-50 border border-blue-200 rounded-md p-2.5" data-testid="booking-dialog-selected-guest">
              <UserCheck className="w-4 h-4 text-blue-600 flex-shrink-0" />
              <div className="flex-1 min-w-0">
                <p className="text-sm font-medium text-blue-900 truncate">{selectedGuest.name}</p>
                <p className="text-xs text-blue-600 truncate">
                  {selectedGuest.email && !selectedGuest.email.includes('placeholder') ? selectedGuest.email : ''}
                  {selectedGuest.phone ? (selectedGuest.email && !selectedGuest.email.includes('placeholder') ? ' | ' : '') + selectedGuest.phone : ''}
                  {selectedGuest.total_stays > 0 && ` | ${selectedGuest.total_stays} konaklama`}
                </p>
              </div>
              <Button type="button" variant="ghost" size="sm" aria-label={t("experience.clearGuest", "Misafir seçimini kaldır")} className="h-10 w-10 p-0 text-blue-600 hover:text-blue-600 hover:bg-blue-100" onClick={handleClearGuest} data-testid="booking-dialog-clear-guest">
                &times;
              </Button>
            </div> : <div className="relative mt-1">
              <div className="relative">
                <Search className="absolute left-2.5 top-1/2 -translate-y-1/2 w-4 h-4 text-gray-400" />
                <Input value={guestSearchQuery} onChange={e => handleGuestSearch(e.target.value)} onFocus={() => {
                  if (guestSearchResults.length > 0) setShowGuestDropdown(true);
                }} placeholder={t('cm.components_pms_BookingDialog.misafir_ara_isim_e_posta_telefon')} className="pl-9" data-testid="booking-dialog-guest-search" />
                {guestSearchLoading && <span className="absolute right-2.5 top-1/2 -translate-y-1/2 w-4 h-4 border-2 border-blue-400 border-t-transparent rounded-full animate-spin" />}
              </div>

              {/* Search results dropdown */}
              {showGuestDropdown && guestSearchResults.length > 0 && <div className="absolute z-50 w-full mt-1 bg-white border border-gray-200 rounded-md shadow-lg max-h-48 overflow-y-auto" data-testid="booking-dialog-guest-dropdown">
                  {guestSearchResults.map(g => <button key={g.id} type="button" className="w-full text-left px-3 py-2 hover:bg-blue-50 border-b border-gray-50 last:border-b-0 transition-colors" onClick={() => handleSelectGuest(g)} data-testid={`booking-dialog-guest-option-${g.id}`}>
                      <div className="flex items-center gap-2">
                        <UserCheck className="w-3.5 h-3.5 text-blue-500 flex-shrink-0" />
                        <div className="min-w-0">
                          <p className="text-sm font-medium text-gray-900 truncate">
                            {g.name}
                            {g.vip_status && <span className="ml-1 text-amber-500 text-xs">VIP</span>}
                          </p>
                          <p className="text-xs text-gray-500 truncate">
                            {g.email && !g.email.includes('placeholder') ? g.email : ''}
                            {g.phone ? (g.email && !g.email.includes('placeholder') ? ' | ' : '') + g.phone : ''}
                          </p>
                        </div>
                      </div>
                    </button>)}
                </div>}

              {/* No results hint */}
              {guestSearchQuery.trim().length >= 2 && !guestSearchLoading && showGuestDropdown && guestSearchResults.length === 0 && <div className="absolute z-50 w-full mt-1 bg-white border border-gray-200 rounded-md shadow-lg px-3 py-2">
                  <div className="flex items-center gap-2 text-gray-500">
                    <UserPlus className="w-3.5 h-3.5" />
                    <span className="text-sm">{t('cm.components_pms_BookingDialog.sonuc_bulunamadi_yeni_misafir_kaydedin')}</span>
                  </div>
                </div>}
            </div>}
        </div>
        <div className="flex justify-end">
          <Button type="button" variant="outline" size="sm" onClick={() => setOpenDialog('guest')} data-testid="booking-dialog-register-guest">
            {t('cm.components_pms_BookingDialog.yeni_misafir_kaydet')}
          </Button>
        </div>
      </div>

      {/* Multi-room rooms list */}
      <div className="mt-4 border rounded-lg p-4 space-y-4 bg-slate-50">
        <div className="flex items-center justify-between">
          <div>
            <h3 className="font-semibold text-sm">{t('experience.booking.rooms', "Bu rezervasyondaki odalar")}</h3>
            <p className="text-xs text-slate-500">{t('experience.booking.roomsHelp', "Aynı rezervasyona birden fazla oda ekleyebilirsiniz.")}</p>
          </div>
          <Button type="button" variant="outline" size="sm" onClick={addRoomToMultiBooking}>
            <Plus className="w-4 h-4 mr-1" /> {t('experience.booking.addRoom', "Oda ekle")}
          </Button>
        </div>

        <div className="space-y-3">
          {multiRoomBooking.map((room, index) => {
            const physicalRoom = rooms.find(item => item.id === room.room_id);
            const occupancyRule = findOccupancyRule(occupancyPricingRules, physicalRoom);
            return <div key={room.id || index} className="border rounded-md bg-card p-3 space-y-3">
              <div className="flex items-center justify-between">
                <div className="font-medium text-sm">{t('experience.booking.room', 'Oda')} {index + 1}</div>
                {multiRoomBooking.length > 1 && <Button type="button" variant="ghost" size="sm" className="text-red-500 hover:text-red-700 hover:bg-red-50" onClick={() => removeRoomFromMultiBooking(index)}>
                    {t('experience.booking.remove', "Kaldır")}
                  </Button>}
              </div>

              <div className="grid grid-cols-1 sm:grid-cols-3 gap-3">
                <div>
                  <Label className="text-xs">{t("experience.booking.room", "Oda")} *</Label>
                  <Select value={room.room_id} onValueChange={v => updateMultiRoomField(index, 'room_id', v)}>
                    <SelectTrigger><SelectValue placeholder={t('experience.booking.selectRoom', "Oda seçin")} /></SelectTrigger>
                    <SelectContent>
                      {rooms.filter(r => r.status === 'available').map(r => <SelectItem key={r.id} value={r.id}>
                          {t('experience.booking.room', 'Oda')} {r.room_number} - {r.room_type}
                        </SelectItem>)}
                    </SelectContent>
                  </Select>
                </div>
                <div>
                  <Label className="text-xs">{t('experience.booking.adults', "Yetişkin")}</Label>
                  <Input aria-label={t("experience.booking.adults", "Yetişkin")} type="number" min="1" value={room.adults} onChange={e => updateMultiRoomField(index, 'adults', e.target.value)} />
                </div>
                <div>
                  <Label className="text-xs">{t('experience.booking.children', "Çocuk")}</Label>
                  <Input aria-label={t("experience.booking.children", "Çocuk")} type="number" min="0" value={room.children} onChange={e => updateMultiRoomChildrenAges(index, e.target.value)} />
                </div>
              </div>

              {room.children > 0 && <div>
                  <Label className="text-xs">{t('experience.booking.childAges', "Çocukların yaşları")}</Label>
                  <div className="grid grid-cols-4 gap-2 mt-1">
                    {Array.from({
                    length: room.children
                  }).map((_, ageIndex) => <Input key={ageIndex} type="number" min="0" max="17" aria-label={t('experience.childAge', { index: ageIndex + 1, defaultValue: 'Çocuk yaşı' })} placeholder={t('experience.childAge', { index: ageIndex + 1, defaultValue: 'Çocuk yaşı' })} value={room.children_ages?.[ageIndex] ?? ''} onChange={e => updateMultiRoomChildAge(index, ageIndex, e.target.value)} />)}
                  </div>
                </div>}

              <div className="grid grid-cols-1 sm:grid-cols-2 gap-3 pt-2 border-t mt-2">
                <div>
                  <Label className="text-xs">{t('experience.booking.ratePlan', "Fiyat planı")}</Label>
                  <Select value={room.rate_plan || ''} onValueChange={v => {
                    // Set rate plan and suggest base rate from selected plan
                    const selected = ratePlans.find(rp => rp.code === v || rp.id === v);
                    updateMultiRoomField(index, 'rate_plan', v);
                    if (selected?.currency) {
                      setNewBooking(prev => ({ ...prev, currency: String(selected.currency).toUpperCase() }));
                    }
                    if (selected && selected.base_price) {
                      updateMultiRoomField(index, 'base_rate', selected.base_price);
                      if (!room.total_amount || room.total_amount === 0) {
                        updateMultiRoomField(index, 'total_amount', selected.base_price);
                      }
                    }
                  }}>
                    <SelectTrigger><SelectValue placeholder={t('experience.booking.selectRatePlan', "Fiyat planı seçin")} /></SelectTrigger>
                    <SelectContent>
                      {ratePlans.map(rp => <SelectItem key={rp.id} value={rp.code || rp.id}>
                          {rp.name} ({rp.code}) - {rp.currency} {rp.base_price}
                        </SelectItem>)}
                    </SelectContent>
                  </Select>
                </div>
                <div>
                  <Label className="text-xs">{t('experience.booking.package', "Paket")}</Label>
                  <Select value={room.package_code || ''} onValueChange={v => updateMultiRoomField(index, 'package_code', v)}>
                    <SelectTrigger><SelectValue placeholder={t('experience.booking.noPackage', "Paket seçilmedi")} /></SelectTrigger>
                    <SelectContent>
                      {packages.map(pkg => <SelectItem key={pkg.id} value={pkg.code}>
                          {pkg.name} ({pkg.code})
                        </SelectItem>)}
                    </SelectContent>
                  </Select>
                </div>
              </div>

              <div className="grid grid-cols-1 sm:grid-cols-2 gap-3 pt-2">
                <div>
                  <Label className="text-xs">{t('experience.booking.baseRate', "Temel fiyat")}</Label>
                  <Input type="number" step="0.01" value={room.base_rate === 0 ? '' : room.base_rate} onChange={e => updateMultiRoomField(index, 'base_rate', e.target.value)} />
                </div>
                <div>
                  <Label className="text-xs">{room.apply_occupancy_pricing ? 'Hesaplanan toplam' : t('experience.booking.total', 'Toplam tutar *')}</Label>
                  <Input type="number" step="0.01" value={room.total_amount === 0 ? '' : room.total_amount} disabled={room.apply_occupancy_pricing} onChange={e => updateMultiRoomField(index, 'total_amount', e.target.value)} />
                </div>
              </div>
              {room.apply_occupancy_pricing && occupancyRule && <div className="rounded-md border border-blue-200 bg-blue-50 px-3 py-2 text-xs text-blue-800">
                {occupancyRule.base_occupancy} yetişkin fiyata dahil · Ek yetişkin {formatCurrency(occupancyRule.extra_adult_rate, newBooking.currency || room.currency || cachedTenantCurrency())}/gece.
                {occupancyRule.child_age_bands?.length > 0 && ` Çocuk yaş kademeleri: ${occupancyRule.child_age_bands.map(band => `${band.min_age}–${band.max_age} ${band.pricing_mode === 'free' ? 'ücretsiz' : band.pricing_mode === 'adult_rate' ? 'yetişkin sayılır' : band.pricing_mode === 'adult_percentage' ? `%${band.value}` : formatCurrency(band.value, newBooking.currency || room.currency || cachedTenantCurrency())}`).join(', ')}.`}
                {' '}Toplam tutar kaydetme sırasında doğrulanır.
              </div>}
            </div>})}
        </div>
      </div>

      {/* Adults and Children for summary (kept for compatibility but hidden) */}
      <div className="hidden">
        <Input type="number" min="1" value={newBooking.adults} onChange={e => {
            const adults = parseInt(e.target.value) || 1;
            setNewBooking(prev => ({
              ...prev,
              adults,
              guests_count: adults + prev.children
            }));
          }} />
        <Input type="number" min="0" value={newBooking.children} onChange={e => handleChildrenChange(e.target.value)} />
      </div>

      {/* Children Ages - Show only if children > 0 */}
      {newBooking.children > 0 && <div>
          <Label>{t('experience.booking.childAges', "Çocukların yaşları")}</Label>
          <div className="grid grid-cols-4 gap-2 mt-2">
            {Array.from({
              length: newBooking.children
            }).map((_, index) => <Input key={index} type="number" min="0" max="17" aria-label={t('experience.childAge', { index: index + 1, defaultValue: 'Çocuk yaşı' })} placeholder={t('experience.childAge', { index: index + 1, defaultValue: 'Çocuk yaşı' })} value={newBooking.children_ages[index] || ''} onChange={e => handleChildAgeChange(index, e.target.value)} />)}
          </div>
        </div>}

      {/* Company Selection */}
      <div>
        <div className="flex justify-between items-center mb-2">
          <Label>{t('experience.booking.company', "Firma (isteğe bağlı)")}</Label>
          <Button type="button" variant="outline" size="sm" onClick={() => setOpenDialog('company')}>
            <Plus className="w-4 h-4 mr-1" />
            {t('experience.booking.newCompany', "Yeni firma ekle")}
          </Button>
        </div>
        <Select value={newBooking.company_id || "none"} onValueChange={handleCompanySelect}>
          <SelectTrigger><SelectValue placeholder={t('experience.booking.selectCompany', "Firma seçin (isteğe bağlı)")} /></SelectTrigger>
          <SelectContent>
            <SelectItem value="none">{t('experience.booking.none', "Seçilmedi")}</SelectItem>
            {companies.filter(c => c.status === 'active').map(c => <SelectItem key={c.id} value={c.id}>{c.name} - {c.corporate_code}</SelectItem>)}
          </SelectContent>
        </Select>
      </div>

      {/* Contracted Rate */}
      {newBooking.company_id && <div className="grid grid-cols-1 sm:grid-cols-2 gap-4">
          <div>
            <Label>{t('experience.booking.contracted', "Anlaşmalı fiyat")}</Label>
            <Select value={newBooking.contracted_rate} onValueChange={handleContractedRateSelect}>
              <SelectTrigger><SelectValue placeholder={t('experience.booking.selectRate', "Fiyat seçin")} /></SelectTrigger>
              <SelectContent>
                <SelectItem value="corp_std">{t('experience.booking.corpStd', "Standart kurumsal")}</SelectItem>
                <SelectItem value="corp_pref">{t('experience.booking.corpPref', "Özel kurumsal")}</SelectItem>
                <SelectItem value="gov">{t('experience.booking.government', "Kamu fiyatı")}</SelectItem>
                <SelectItem value="ta">{t('experience.booking.travelAgent', "Acente fiyatı")}</SelectItem>
                <SelectItem value="crew">{t('experience.booking.crew', "Uçuş ekibi fiyatı")}</SelectItem>
                <SelectItem value="mice">{t('experience.booking.event', "Etkinlik ve konferans fiyatı")}</SelectItem>
                <SelectItem value="lts">{t('experience.booking.longProject', "Uzun konaklama ve proje fiyatı")}</SelectItem>
                <SelectItem value="tou">{t('experience.booking.tour', "Tur operatörü fiyatı")}</SelectItem>
              </SelectContent>
            </Select>
          </div>
          <div>
            <Label>{t('experience.booking.rateType', "Fiyat türü")}</Label>
            <Select value={newBooking.rate_type} onValueChange={v => setNewBooking({
              ...newBooking,
              rate_type: v
            })}>
              <SelectTrigger><SelectValue placeholder={t('experience.booking.selectType', "Tür seçin")} /></SelectTrigger>
              <SelectContent>
                <SelectItem value="bar">{t('experience.booking.bar', "Standart satış fiyatı (BAR)")}</SelectItem>
                <SelectItem value="corporate">{t('experience.booking.corp', "Kurumsal fiyat")}</SelectItem>
                <SelectItem value="government">{t('experience.booking.government', "Kamu fiyatı")}</SelectItem>
                <SelectItem value="wholesale">{t('experience.booking.wholesale', "Toptan satış fiyatı")}</SelectItem>
                <SelectItem value="package">{t('experience.booking.packageRate', "Paket fiyatı")}</SelectItem>
                <SelectItem value="promotional">{t('experience.booking.promo', "Kampanyalı fiyat")}</SelectItem>
                <SelectItem value="non_refundable">{t('experience.booking.nonRefundable', "İade edilmez")}</SelectItem>
                <SelectItem value="long_stay">{t('experience.booking.longStay', "Uzun konaklama fiyatı")}</SelectItem>
                <SelectItem value="day_use">{t('experience.booking.dayUse', "Günübirlik kullanım fiyatı")}</SelectItem>
              </SelectContent>
            </Select>
          </div>
        </div>}

      {/* Market Segment and Cancellation Policy */}
      {newBooking.company_id && <div className="grid grid-cols-1 sm:grid-cols-2 gap-4">
          <div>
            <Label>{t('experience.booking.segment', "Pazar segmenti")}</Label>
            <Select value={newBooking.market_segment} onValueChange={v => setNewBooking({
              ...newBooking,
              market_segment: v
            })}>
              <SelectTrigger><SelectValue placeholder={t('experience.booking.selectSegment', "Segment seçin")} /></SelectTrigger>
              <SelectContent>
                <SelectItem value="corporate">{t('experience.booking.corporate', "Kurumsal")}</SelectItem>
                <SelectItem value="leisure">{t('experience.booking.leisure', "Tatil")}</SelectItem>
                <SelectItem value="group">{t('experience.booking.group', "Grup")}</SelectItem>
                <SelectItem value="mice">{t('experience.booking.mice', "Toplantı ve etkinlik")}</SelectItem>
                <SelectItem value="government">{t('experience.booking.gov', "Kamu")}</SelectItem>
                <SelectItem value="crew">{t('experience.booking.airline', "Uçuş ekibi")}</SelectItem>
                <SelectItem value="wholesale">{t('experience.booking.wholesaler', "Toptan satış")}</SelectItem>
                <SelectItem value="long_stay">{t('experience.booking.long', "Uzun konaklama")}</SelectItem>
                <SelectItem value="complimentary">{t('experience.booking.comp', "Ücretsiz konaklama")}</SelectItem>
                <SelectItem value="other">{t('experience.booking.other', "Diğer")}</SelectItem>
              </SelectContent>
            </Select>
          </div>
          <div>
            <Label>{t('experience.booking.cancelPolicy', "İptal koşulu")}</Label>
            <Select value={newBooking.cancellation_policy} onValueChange={v => setNewBooking({
              ...newBooking,
              cancellation_policy: v
            })}>
              <SelectTrigger><SelectValue placeholder={t('experience.booking.selectPolicy', "İptal koşulu seçin")} /></SelectTrigger>
              <SelectContent>
                <SelectItem value="same_day">{t('experience.booking.sameDay', "Aynı gün (18.00)")}</SelectItem>
                <SelectItem value="h24">{t('experience.booking.h24', "24 saat")}</SelectItem>
                <SelectItem value="h48">{t('experience.booking.h48', "48 saat")}</SelectItem>
                <SelectItem value="h72">{t('experience.booking.h72', "72 saat")}</SelectItem>
                <SelectItem value="d7">{t('experience.booking.d7', "7 gün")}</SelectItem>
                <SelectItem value="d14">{t('experience.booking.d14', "14 gün")}</SelectItem>
                <SelectItem value="non_refundable">{t('experience.booking.nonRefundable', "İade edilmez")}</SelectItem>
                <SelectItem value="flexible">{t('experience.booking.flex', "Esnek")}</SelectItem>
                <SelectItem value="special_event">{t('experience.booking.special', "Özel etkinlik")}</SelectItem>
              </SelectContent>
            </Select>
          </div>
        </div>}

      {/* Billing Information */}
      {newBooking.company_id && <div className="space-y-4 border-t pt-4">
          <h3 className="font-semibold">{t('experience.booking.billing', "Fatura bilgileri")}</h3>
          <div>
            <Label>{t('experience.booking.address', "Fatura adresi")}</Label>
            <Textarea value={newBooking.billing_address} onChange={e => setNewBooking({
              ...newBooking,
              billing_address: e.target.value
            })} rows={2} />
          </div>
          <div className="grid grid-cols-1 sm:grid-cols-2 gap-4">
            <div>
              <Label>{t('experience.booking.tax', "Vergi numarası")}</Label>
              <Input value={newBooking.billing_tax_number} onChange={e => setNewBooking({
                ...newBooking,
                billing_tax_number: e.target.value
              })} />

      {/* Multi-room section placeholder: future enhancement */}

            </div>
            <div>
              <Label>{t('experience.booking.contact', "İlgili kişi")}</Label>
              <Input value={newBooking.billing_contact_person} onChange={e => setNewBooking({
                ...newBooking,
                billing_contact_person: e.target.value
              })} />
            </div>
          </div>
        </div>}

      {/* Channel selection (rate details managed per-room above) */}
      <div className="grid grid-cols-3 gap-4 border-t pt-4">
        <div className="col-span-2 text-xs text-gray-500 flex items-center">
          {t('experience.booking.rateHelp', "Oda fiyatlarını ve tutarlarını yukarıdaki oda bölümünden düzenleyebilirsiniz.")}
        </div>
        <div>
          <Label>{t('experience.booking.channel', "Rezervasyon kanalı")}</Label>
          <Select value={newBooking.channel} onValueChange={v => setNewBooking({
              ...newBooking,
              channel: v
            })}>
            <SelectTrigger><SelectValue /></SelectTrigger>
            <SelectContent>
              <SelectItem value="direct">{t('experience.booking.direct', "Doğrudan")}</SelectItem>
              <SelectItem value="booking_com">Booking.com</SelectItem>
              <SelectItem value="expedia">Expedia</SelectItem>
              <SelectItem value="airbnb">Airbnb</SelectItem>
              <SelectItem value="agoda">Agoda</SelectItem>
            </SelectContent>
          </Select>
        </div>
      </div>

      {/* Override Reason - Show if rate is different from base */}
      {newBooking.base_rate > 0 && newBooking.base_rate !== newBooking.total_amount && <div className="bg-yellow-50 border border-yellow-200 p-4 rounded">
          <Label className="text-yellow-800">{t('experience.booking.override', "Fiyat değişikliği gerekçesi *")}</Label>
          <Textarea value={newBooking.override_reason} onChange={e => setNewBooking({
            ...newBooking,
            override_reason: e.target.value
          })} placeholder={t('experience.booking.overrideHelp', "Fiyat değişikliğinin nedenini açıklayın.")} className="mt-2" required />
        </div>}

      <div className="sticky bottom-0 -mx-4 border-t bg-background px-4 py-3 sm:-mx-6 sm:px-6"><p className="mb-2 text-sm text-muted-foreground">{t("experience.booking.review", "Kaydetmeden önce tarihleri, oda seçimini ve toplam tutarı kontrol edin.")}</p><Button type="submit" disabled={submitting} aria-busy={submitting} className="w-full">{t('experience.booking.create', "Rezervasyonu oluştur")}</Button></div>
    </form>
  </DialogContent>
</Dialog>;
};
export default BookingDialog;
