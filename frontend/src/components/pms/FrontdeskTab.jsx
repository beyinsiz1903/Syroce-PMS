import React, { memo, useRef, useState, useMemo, useCallback } from 'react';
import axios from 'axios';
import { toast } from 'sonner';
import { useNavigate } from 'react-router-dom';
import { useTranslation } from 'react-i18next';
import { Card, CardContent, CardHeader, CardTitle } from '@/components/ui/card';
import { Badge } from '@/components/ui/badge';
import { Button } from '@/components/ui/button';
import { Input } from '@/components/ui/input';
import { Label } from '@/components/ui/label';
import { Select, SelectContent, SelectItem, SelectTrigger, SelectValue } from '@/components/ui/select';
import { Tabs, TabsContent, TabsList, TabsTrigger } from '@/components/ui/tabs';
import { Dialog, DialogContent, DialogHeader, DialogTitle } from '@/components/ui/dialog';
import { TableLoadingSkeleton } from '@/utils/lazyLoad';
import {
  Calendar, Users, TrendingUp, LogIn, LogOut, Star,
  AlertTriangle, Clock, UserPlus, CheckSquare, Printer, XCircle,
  ChevronDown, ChevronUp, CreditCard, Loader2
} from 'lucide-react';
import { printRegistrationCard } from '@/components/pms/PrintTemplates';

import { confirmDialog } from '@/lib/dialogs';
const FrontdeskTab = ({
  arrivals,
  departures,
  inhouse,
  aiPrediction,
  aiPatterns,
  bookings,
  rooms = [],
  guests = [],
  handleCheckIn,
  handleCheckOut,
  loadFolio,
  loadFrontDeskData,
  loadData,
  loading,
  error,
  tenant,
  setReservationDetailId,
}) => {
  const { t } = useTranslation();
  const navigate = useNavigate();
  const tf = useCallback((k, opts) => t(`pmsComponents.frontdesk.${k}`, opts), [t]);
  const [showGroupCheckin, setShowGroupCheckin] = useState(false);
  const [groupCheckinIds, setGroupCheckinIds] = useState(new Set());
  const [checkoutInProgress, setCheckoutInProgress] = useState(null);
  const [quickPaymentBooking, setQuickPaymentBooking] = useState(null);
  const [quickPaymentAmount, setQuickPaymentAmount] = useState('');
  const [quickPaymentMethod, setQuickPaymentMethod] = useState('card');
  const [quickPaymentCariAccounts, setQuickPaymentCariAccounts] = useState([]);
  const [quickPaymentCariAccountId, setQuickPaymentCariAccountId] = useState('');
  const [quickPaymentCariLoading, setQuickPaymentCariLoading] = useState(false);
  const [quickPaymentInProgress, setQuickPaymentInProgress] = useState(false);
  const quickPaymentSubmittingRef = useRef(false);
  // Which top KPI card is currently expanded to show guest names: null | 'arrivals' | 'departures' | 'inhouse'
  const [expandedKpi, setExpandedKpi] = useState(null);
  const toggleKpi = useCallback((key) => {
    setExpandedKpi(prev => (prev === key ? null : key));
  }, []);

  // Today's financial pulse (computed client-side from already-loaded data)
  const financialPulse = useMemo(() => {
    const sumNum = (arr, key) => arr.reduce((acc, b) => acc + (Number(b?.[key]) || 0), 0);
    const expectedRevenue = sumNum(arrivals, 'total_amount');
    const expectedCollections = sumNum(departures, 'balance');
    const inhouseOutstanding = sumNum(inhouse, 'balance');
    const occRooms = rooms.filter(r => ['occupied', 'reserved'].includes(r.status)).length;
    const totalRooms = rooms.length || 0;
    const occupancyPct = totalRooms > 0 ? Math.round((occRooms / totalRooms) * 100) : 0;
    return { expectedRevenue, expectedCollections, inhouseOutstanding, occupancyPct, occRooms, totalRooms };
  }, [arrivals, departures, inhouse, rooms]);

  // VIP & special-request alerts: scan today's arrivals + in-house
  const guestById = useMemo(() => {
    const m = new Map();
    for (const g of guests) m.set(g.id, g);
    return m;
  }, [guests]);

  const attentionList = useMemo(() => {
    const items = [];
    const seen = new Set();
    const addBooking = (b, source) => {
      if (!b || seen.has(b.id)) return;
      const guest = b.guest_id ? guestById.get(b.guest_id) : null;
      const isVip = !!(guest?.vip_status || b.vip_status);
      const sr = (b.special_requests || '').trim();
      if (!isVip && !sr) return;
      seen.add(b.id);
      items.push({
        id: b.id,
        bookingId: b.id,
        roomNumber: b.room_number || b.room?.room_number || '-',
        guestName: b.guest_name || guest?.name || tf('guest'),
        isVip,
        loyaltyPoints: guest?.loyalty_points || 0,
        specialRequests: sr,
        source, // 'arrival' | 'inhouse'
      });
    };
    (arrivals || []).forEach(b => addBooking(b, 'arrival'));
    (inhouse || []).forEach(b => addBooking(b, 'inhouse'));
    return items.slice(0, 12); // cap to prevent overflow
  }, [arrivals, inhouse, guestById, tf]);

  const formatMoney = useCallback((n) => {
    const v = Number(n) || 0;
    return v.toLocaleString(undefined, { minimumFractionDigits: 0, maximumFractionDigits: 2 });
  }, []);

  const today = useMemo(() => new Date().toISOString().split('T')[0], []);

  const overstays = useMemo(() => {
    return (inhouse || []).filter(b => {
      if (b.status !== 'checked_in') return false;
      const co = (b.check_out || '').slice(0, 10);
      return co && co < today;
    });
  }, [inhouse, today]);

  const noShows = useMemo(() => {
    if (!bookings) return [];
    return bookings.filter(b => {
      if (b.status === 'no_show') return true;
      if (b.status !== 'confirmed' && b.status !== 'guaranteed') return false;
      const ci = (b.check_in || '').slice(0, 10);
      return ci && ci < today;
    });
  }, [bookings, today]);

  const groupArrivals = useMemo(() => {
    return arrivals.filter(b => b.group_booking_id);
  }, [arrivals]);

  const toggleGroupCheckin = (id) => {
    setGroupCheckinIds(prev => {
      const next = new Set(prev);
      if (next.has(id)) next.delete(id); else next.add(id);
      return next;
    });
  };

  const handleBatchCheckin = async () => {
    for (const id of groupCheckinIds) {
      await handleCheckIn(id);
    }
    setGroupCheckinIds(new Set());
    setShowGroupCheckin(false);
  };

  const requestCheckout = useCallback(async (booking) => {
    if (!booking?.id || checkoutInProgress) return;

    const balance = Number(booking.balance) || 0;
    if (balance > 0.01) {
      setReservationDetailId?.(booking.id);
      toast.warning(`${tf('balance')}: ${formatMoney(balance)} ${t('pmsComponents.common.currency')} · ${tf('collectFirst')}`);
      return;
    }

    const guestName = booking.guest_name || booking.guest?.name || tf('guest');
    const confirmed = await confirmDialog({
      message: `${guestName} için çıkış işlemini onaylıyor musunuz?`,
      variant: 'default',
    });
    if (!confirmed) return;

    setCheckoutInProgress(booking.id);
    try {
      await handleCheckOut(booking.id);
    } finally {
      setCheckoutInProgress(null);
    }
  }, [checkoutInProgress, formatMoney, handleCheckOut, setReservationDetailId, t, tf]);

  const openQuickPayment = useCallback((booking) => {
    const balance = Math.max(0, Number(booking?.balance) || 0);
    if (!booking?.id || balance <= 0.01) return;
    setQuickPaymentBooking(booking);
    setQuickPaymentAmount(balance.toFixed(2));
    setQuickPaymentMethod('card');
    setQuickPaymentCariAccountId('');
  }, []);

  const closeQuickPayment = useCallback(() => {
    if (quickPaymentSubmittingRef.current) return;
    setQuickPaymentBooking(null);
    setQuickPaymentAmount('');
    setQuickPaymentMethod('card');
    setQuickPaymentCariAccountId('');
  }, []);

  const handleQuickPaymentMethodChange = useCallback(async (method) => {
    setQuickPaymentMethod(method);
    setQuickPaymentCariAccountId('');
    if (method !== 'city_ledger') return;

    setQuickPaymentCariLoading(true);
    try {
      const response = await axios.get('/pms/cari-accounts');
      const accounts = Array.isArray(response.data?.accounts) ? response.data.accounts : [];
      setQuickPaymentCariAccounts(accounts);
      if (accounts.length === 1) setQuickPaymentCariAccountId(accounts[0].id);
    } catch (error) {
      setQuickPaymentCariAccounts([]);
      toast.error('Cari hesaplar yüklenemedi. Lütfen tekrar deneyin.');
    } finally {
      setQuickPaymentCariLoading(false);
    }
  }, []);

  const submitQuickPayment = useCallback(async () => {
    if (!quickPaymentBooking?.id || quickPaymentSubmittingRef.current) return;
    const amount = Number(quickPaymentAmount);
    const balance = Math.max(0, Number(quickPaymentBooking.balance) || 0);
    if (!Number.isFinite(amount) || amount <= 0) {
      toast.error('Ödeme tutarı sıfırdan büyük olmalı.');
      return;
    }
    if (amount > balance + 0.01) {
      toast.error('Ödeme tutarı kalan bakiyeyi aşamaz.');
      return;
    }
    const isCariTransfer = quickPaymentMethod === 'city_ledger';
    if (isCariTransfer && !quickPaymentCariAccountId) {
      toast.error('Aktarım yapılacak cari hesabı seçin.');
      return;
    }

    quickPaymentSubmittingRef.current = true;
    setQuickPaymentInProgress(true);
    const idempotencyKey = window.crypto?.randomUUID?.()
      || `frontdesk-payment-${quickPaymentBooking.id}-${Date.now()}-${Math.random()}`;
    try {
      if (isCariTransfer) {
        await axios.post(`/pms/reservations/${quickPaymentBooking.id}/transfer-to-cari`, {
          amount,
          cari_account_id: quickPaymentCariAccountId,
          description: 'Ön büro hızlı cari aktarım',
        }, {
          headers: { 'Idempotency-Key': idempotencyKey },
        });
        toast.success(`Bakiye cari hesaba aktarıldı: ${formatMoney(amount)} ${t('pmsComponents.common.currency')}`);
      } else {
        await axios.post(`/frontdesk/folio/${quickPaymentBooking.id}/payment`, {
          amount,
          method: quickPaymentMethod,
          payment_type: amount >= balance - 0.01 ? 'final' : 'interim',
          reference: null,
          notes: 'Ön büro hızlı tahsilat',
        }, {
          headers: { 'Idempotency-Key': idempotencyKey },
        });
        toast.success(`Ödeme folyoya işlendi: ${formatMoney(amount)} ${t('pmsComponents.common.currency')}`);
      }
      setQuickPaymentBooking(null);
      setQuickPaymentAmount('');
      setQuickPaymentMethod('card');
      setQuickPaymentCariAccountId('');
      await Promise.allSettled([
        loadFrontDeskData ? Promise.resolve().then(loadFrontDeskData) : Promise.resolve(),
        loadData ? Promise.resolve().then(loadData) : Promise.resolve(),
      ]);
    } catch (error) {
      const detail = error?.response?.data?.detail;
      const message = typeof detail === 'string'
        ? detail
        : detail?.message || 'Ödeme folyoya işlenemedi. Lütfen tekrar deneyin.';
      toast.error(message);
    } finally {
      quickPaymentSubmittingRef.current = false;
      setQuickPaymentInProgress(false);
    }
  }, [formatMoney, loadData, loadFrontDeskData, quickPaymentAmount, quickPaymentBooking, quickPaymentCariAccountId, quickPaymentMethod, t]);

  if (loading) {
    return (
      <TabsContent value="frontdesk" className="space-y-6">
        <TableLoadingSkeleton />
      </TabsContent>
    );
  }

  if (error) {
    return (
      <TabsContent value="frontdesk" className="space-y-6">
        <div className="text-center py-12">
          <AlertTriangle className="w-10 h-10 text-red-400 mx-auto mb-3" />
          <p className="text-red-600 font-medium mb-2">{tf('dataLoadError')}</p>
          <p className="text-sm text-gray-500 mb-4">{error}</p>
          <Button variant="outline" onClick={loadFrontDeskData}>{tf('retry')}</Button>
        </div>
      </TabsContent>
    );
  }

  return (
    <TabsContent value="frontdesk" className="space-y-6">
      <div className="grid grid-cols-1 md:grid-cols-3 lg:grid-cols-5 gap-4">
        <Card
          role="button"
          tabIndex={0}
          aria-expanded={expandedKpi === 'arrivals'}
          onClick={() => toggleKpi('arrivals')}
          onKeyDown={(e) => { if (e.key === 'Enter' || e.key === ' ') { e.preventDefault(); toggleKpi('arrivals'); } }}
          className={`cursor-pointer transition-all hover:shadow-md hover:border-blue-300 ${expandedKpi === 'arrivals' ? 'ring-2 ring-blue-400 border-blue-300' : ''}`}
          data-testid="kpi-arrivals"
        >
          <CardHeader className="pb-2">
            <CardTitle className="text-sm flex items-center justify-between">
              <span>{t('pms.todayArrivals')}</span>
              {expandedKpi === 'arrivals' ? <ChevronUp className="w-4 h-4 text-gray-400" /> : <ChevronDown className="w-4 h-4 text-gray-400" />}
            </CardTitle>
          </CardHeader>
          <CardContent>
            <div className="text-3xl font-bold">{arrivals.length}</div>
            <p className="text-xs text-gray-500">{t('pms.expectedCheckins')}</p>
          </CardContent>
        </Card>
        <Card
          role="button"
          tabIndex={0}
          aria-expanded={expandedKpi === 'departures'}
          onClick={() => toggleKpi('departures')}
          onKeyDown={(e) => { if (e.key === 'Enter' || e.key === ' ') { e.preventDefault(); toggleKpi('departures'); } }}
          className={`cursor-pointer transition-all hover:shadow-md hover:border-blue-300 ${expandedKpi === 'departures' ? 'ring-2 ring-blue-400 border-blue-300' : ''}`}
          data-testid="kpi-departures"
        >
          <CardHeader className="pb-2">
            <CardTitle className="text-sm flex items-center justify-between">
              <span>{t('pms.todayDepartures')}</span>
              {expandedKpi === 'departures' ? <ChevronUp className="w-4 h-4 text-gray-400" /> : <ChevronDown className="w-4 h-4 text-gray-400" />}
            </CardTitle>
          </CardHeader>
          <CardContent>
            <div className="text-3xl font-bold">{departures.length}</div>
            <p className="text-xs text-gray-500">{t('pms.expectedCheckouts')}</p>
          </CardContent>
        </Card>
        <Card
          role="button"
          tabIndex={0}
          aria-expanded={expandedKpi === 'inhouse'}
          onClick={() => toggleKpi('inhouse')}
          onKeyDown={(e) => { if (e.key === 'Enter' || e.key === ' ') { e.preventDefault(); toggleKpi('inhouse'); } }}
          className={`cursor-pointer transition-all hover:shadow-md hover:border-blue-300 ${expandedKpi === 'inhouse' ? 'ring-2 ring-blue-400 border-blue-300' : ''}`}
          data-testid="kpi-inhouse"
        >
          <CardHeader className="pb-2">
            <CardTitle className="text-sm flex items-center justify-between">
              <span>{t('pms.inHouseGuests')}</span>
              {expandedKpi === 'inhouse' ? <ChevronUp className="w-4 h-4 text-gray-400" /> : <ChevronDown className="w-4 h-4 text-gray-400" />}
            </CardTitle>
          </CardHeader>
          <CardContent>
            <div className="text-3xl font-bold">{inhouse.length}</div>
            <p className="text-xs text-gray-500">{t('pms.currentlyStaying')}</p>
          </CardContent>
        </Card>
        {overstays.length > 0 && (
          <Card className="border-red-200 bg-red-50">
            <CardHeader className="pb-2">
              <CardTitle className="text-sm text-red-700 flex items-center gap-1">
                <AlertTriangle className="w-4 h-4" /> Overstay
              </CardTitle>
            </CardHeader>
            <CardContent>
              <div className="text-3xl font-bold text-red-700">{overstays.length}</div>
              <p className="text-xs text-red-500">{tf('lateCheckout')}</p>
            </CardContent>
          </Card>
        )}
        {noShows.length > 0 && (
          <Card
            role="button"
            tabIndex={0}
            aria-expanded={expandedKpi === 'noshow'}
            onClick={() => toggleKpi('noshow')}
            onKeyDown={(e) => { if (e.key === 'Enter' || e.key === ' ') { e.preventDefault(); toggleKpi('noshow'); } }}
            className={`cursor-pointer transition-all hover:shadow-md hover:border-amber-400 border-amber-200 bg-amber-50 ${expandedKpi === 'noshow' ? 'ring-2 ring-amber-400' : ''}`}
            data-testid="kpi-noshow"
          >
            <CardHeader className="pb-2">
              <CardTitle className="text-sm text-amber-700 flex items-center justify-between">
                <span className="flex items-center gap-1"><Clock className="w-4 h-4" /> No-Show</span>
                {expandedKpi === 'noshow' ? <ChevronUp className="w-4 h-4 text-amber-400" /> : <ChevronDown className="w-4 h-4 text-amber-400" />}
              </CardTitle>
            </CardHeader>
            <CardContent>
              <div className="text-3xl font-bold text-amber-700">{noShows.length}</div>
              <p className="text-xs text-amber-500">{tf('didntCome')}</p>
            </CardContent>
          </Card>
        )}
      </div>

      {/* Expanded guest list — appears below the KPI cards when one of the top 3 is clicked */}
      {expandedKpi && (
        <Card className="border-blue-200 bg-blue-50/30" data-testid={`kpi-expanded-${expandedKpi}`}>
          <CardHeader className="pb-2">
            <CardTitle className="text-sm flex items-center justify-between text-blue-800">
              <span className="flex items-center gap-2">
                {expandedKpi === 'arrivals' && <><LogIn className="w-4 h-4" /> {t('pms.todayArrivals')}</>}
                {expandedKpi === 'departures' && <><LogOut className="w-4 h-4" /> {t('pms.todayDepartures')}</>}
                {expandedKpi === 'inhouse' && <><Users className="w-4 h-4" /> {t('pms.inHouseGuests')}</>}
                {expandedKpi === 'noshow' && <><Clock className="w-4 h-4" /> No-Show</>}
                <Badge variant="outline" className="text-[10px] border-blue-300 text-blue-700">
                  {expandedKpi === 'arrivals' ? arrivals.length : expandedKpi === 'departures' ? departures.length : expandedKpi === 'inhouse' ? inhouse.length : noShows.length}
                </Badge>
              </span>
              <Button variant="ghost" size="sm" className="h-7 text-xs text-gray-500" onClick={() => setExpandedKpi(null)}>
                <XCircle className="w-3.5 h-3.5 mr-1" /> {t('common.close', 'Kapat')}
              </Button>
            </CardTitle>
          </CardHeader>
          <CardContent>
            {(() => {
              const list =
                expandedKpi === 'arrivals' ? arrivals :
                expandedKpi === 'departures' ? departures :
                expandedKpi === 'inhouse' ? inhouse : noShows;
              if (!list || list.length === 0) {
                return (
                  <p className="text-center py-4 text-sm text-gray-400">
                    {expandedKpi === 'arrivals' && tf('noArrivalsToday')}
                    {expandedKpi === 'departures' && tf('noDeparturesToday')}
                    {expandedKpi === 'inhouse' && tf('noInhouseGuests')}
                    {expandedKpi === 'noshow' && tf('didntCome')}
                  </p>
                );
              }
              return (
                <div className="grid grid-cols-1 md:grid-cols-2 lg:grid-cols-3 gap-2 max-h-[280px] overflow-y-auto pr-1">
                  {list.map((b) => {
                    const guestName = b.guest?.name || b.guest_name || tf('guest');
                    const roomNo = b.room?.room_number || b.room_number || '-';
                    const isVip = !!(b.guest?.vip_status || b.vip_status);
                    const balance = Number(b.balance) || 0;
                    return (
                      <button
                        key={b.id}
                        type="button"
                        onClick={() => setReservationDetailId?.(b.id)}
                        className="text-left rounded-md border bg-white border-blue-100 p-2 hover:shadow-md hover:border-blue-400 transition focus:outline-none focus:ring-2 focus:ring-blue-300"
                        title={tf('clickToOpenBooking')}
                        data-testid={`kpi-guest-${b.id}`}
                      >
                        <div className="flex items-center justify-between gap-2 mb-1">
                          <div className="flex items-center gap-1 min-w-0">
                            {isVip && (
                              <Badge className="text-[9px] bg-indigo-500 hover:bg-indigo-500 text-white">VIP</Badge>
                            )}
                            <span className="font-semibold text-xs text-gray-800 truncate">{guestName}</span>
                          </div>
                          <span className="text-[10px] text-gray-500 whitespace-nowrap">
                            {tf('room')} {roomNo}
                          </span>
                        </div>
                        <div className="flex items-center gap-1 flex-wrap">
                          {b.check_in && b.check_out && (
                            <span className="text-[10px] text-gray-500">
                              {new Date(b.check_in).toLocaleDateString('tr-TR')} → {new Date(b.check_out).toLocaleDateString('tr-TR')}
                            </span>
                          )}
                          {balance > 0 && (
                            <Badge variant="outline" className="text-[9px] border-red-300 text-red-700 ml-auto">
                              {tf('balance')}: {balance.toFixed(2)} {t('pmsComponents.common.currency')}
                            </Badge>
                          )}
                        </div>
                      </button>
                    );
                  })}
                </div>
              );
            })()}
          </CardContent>
        </Card>
      )}

      {/* Today's Financial Pulse — quick at-a-glance numbers for the front desk */}
      <Card className="border-blue-100">
        <CardHeader className="pb-2">
          <CardTitle className="text-sm flex items-center gap-2 text-blue-700">
            <TrendingUp className="w-4 h-4" /> {tf('financialPulseTitle')}
          </CardTitle>
        </CardHeader>
        <CardContent>
          <div className="grid grid-cols-2 md:grid-cols-4 gap-3">
            <div className="rounded-md bg-emerald-50 border border-emerald-100 p-3">
              <p className="text-[11px] text-emerald-700 font-medium">{tf('expectedRevenueToday')}</p>
              <p className="text-xl font-bold text-emerald-800 mt-1">
                {formatMoney(financialPulse.expectedRevenue)} <span className="text-[11px] font-normal">{t('pmsComponents.common.currency')}</span>
              </p>
              <p className="text-[10px] text-emerald-600 mt-0.5">{tf('fromArrivals', { count: arrivals.length })}</p>
            </div>
            <div className="rounded-md bg-amber-50 border border-amber-100 p-3">
              <p className="text-[11px] text-amber-700 font-medium">{tf('expectedCollectionsToday')}</p>
              <p className="text-xl font-bold text-amber-800 mt-1">
                {formatMoney(financialPulse.expectedCollections)} <span className="text-[11px] font-normal">{t('pmsComponents.common.currency')}</span>
              </p>
              <p className="text-[10px] text-amber-600 mt-0.5">{tf('fromDepartures', { count: departures.length })}</p>
            </div>
            <div className="rounded-md bg-rose-50 border border-rose-100 p-3">
              <p className="text-[11px] text-rose-700 font-medium">{tf('inhouseOutstanding')}</p>
              <p className="text-xl font-bold text-rose-800 mt-1">
                {formatMoney(financialPulse.inhouseOutstanding)} <span className="text-[11px] font-normal">{t('pmsComponents.common.currency')}</span>
              </p>
              <p className="text-[10px] text-rose-600 mt-0.5">{tf('inhouseGuestsCount', { count: inhouse.length })}</p>
            </div>
            <div className="rounded-md bg-indigo-50 border border-indigo-100 p-3">
              <p className="text-[11px] text-indigo-700 font-medium">{tf('occupancyNow')}</p>
              <p className="text-xl font-bold text-indigo-800 mt-1">
                %{financialPulse.occupancyPct}
              </p>
              <p className="text-[10px] text-indigo-600 mt-0.5">
                {tf('occupiedOfTotal', { occ: financialPulse.occRooms, total: financialPulse.totalRooms })}
              </p>
            </div>
          </div>
        </CardContent>
      </Card>

      {/* VIP & Special Requests attention strip */}
      {attentionList.length > 0 && (
        <Card className="border-amber-200 bg-gradient-to-r from-amber-50 to-yellow-50">
          <CardHeader className="pb-2">
            <CardTitle className="text-sm flex items-center gap-2 text-amber-800">
              <Star className="w-4 h-4 fill-amber-500 text-amber-500" />
              {tf('attentionTitle')}
              <Badge variant="outline" className="ml-1 text-[10px] border-amber-300 text-amber-800">
                {attentionList.length}
              </Badge>
            </CardTitle>
          </CardHeader>
          <CardContent>
            <div className="grid grid-cols-1 md:grid-cols-2 lg:grid-cols-3 gap-2">
              {attentionList.map(item => (
                <button
                  key={item.id}
                  type="button"
                  onClick={() => setReservationDetailId?.(item.bookingId)}
                  className="text-left rounded-md border bg-white border-amber-200 p-2 hover:shadow-md hover:border-amber-400 transition"
                  title={tf('clickToOpenBooking')}
                >
                  <div className="flex items-center justify-between gap-2 mb-1">
                    <div className="flex items-center gap-1 min-w-0">
                      {item.isVip && (
                        <Badge className="text-[9px] bg-amber-500 hover:bg-amber-500 text-white">VIP</Badge>
                      )}
                      <span className="font-semibold text-xs text-gray-800 truncate">{item.guestName}</span>
                    </div>
                    <span className="text-[10px] text-gray-500 whitespace-nowrap">
                      {tf('room')} {item.roomNumber}
                    </span>
                  </div>
                  <div className="flex items-center gap-1 mb-1">
                    <Badge variant="outline" className="text-[9px] border-gray-300">
                      {item.source === 'arrival' ? tf('arrivalToday') : tf('inhouseNow')}
                    </Badge>
                    {item.loyaltyPoints > 0 && (
                      <Badge variant="outline" className="text-[9px] border-indigo-300 text-indigo-700">
                        {tf('loyaltyPoints', { points: item.loyaltyPoints })}
                      </Badge>
                    )}
                  </div>
                  {item.specialRequests && (
                    <p className="text-[11px] text-gray-700 italic line-clamp-2">
                      „{item.specialRequests}"
                    </p>
                  )}
                </button>
              ))}
            </div>
          </CardContent>
        </Card>
      )}

      <div className="flex gap-2">
        <Button variant="outline" size="sm" onClick={() => navigate('/walkin')} data-testid="open-walkin-workflow">
          <UserPlus className="w-4 h-4 mr-1" /> {tf('walkIn')}
        </Button>
        {groupArrivals.length > 0 && (
          <Button variant="outline" size="sm" onClick={() => setShowGroupCheckin(true)}>
            <CheckSquare className="w-4 h-4 mr-1" /> {tf('batchCheckin')} ({groupArrivals.length})
          </Button>
        )}
      </div>

      {overstays.length > 0 && (
        <Card className="border-red-200">
          <CardHeader className="pb-2">
            <CardTitle className="text-sm text-red-700 flex items-center gap-2">
              <AlertTriangle className="w-4 h-4" /> {tf('overstayList')}
            </CardTitle>
          </CardHeader>
          <CardContent>
            <div className="space-y-2">
              {overstays.map(b => (
                <div key={b.id} className="flex items-center justify-between p-2 bg-red-50 rounded border border-red-100 text-xs">
                  <div>
                    <span className="font-medium text-gray-800">{b.guest_name || tf('guest')}</span>
                    <span className="text-gray-500 ml-2">{tf('room')} {b.room_number}</span>
                    <span className="text-red-500 ml-2">{tf('plannedCheckout')}: {b.check_out?.slice(0, 10)}</span>
                  </div>
                  <div className="flex items-center gap-2">
                    {(Number(b.balance) || 0) > 0.01 && (
                      <Button
                        type="button"
                        size="sm"
                        variant="outline"
                        className="h-7 text-xs border-emerald-300 text-emerald-700 hover:bg-emerald-50"
                        onClick={() => openQuickPayment(b)}
                        data-testid={`overstay-payment-${b.id}`}
                      >
                        <CreditCard className="w-3 h-3 mr-1" /> Ödeme Al
                      </Button>
                    )}
                    <Button
                      type="button"
                      size="sm"
                      variant="outline"
                      className="h-7 text-xs border-red-300 text-red-700"
                      onClick={() => requestCheckout(b)}
                      disabled={checkoutInProgress === b.id}
                      data-testid={`overstay-checkout-${b.id}`}
                    >
                      <LogOut className="w-3 h-3 mr-1" />
                      {checkoutInProgress === b.id ? 'İşleniyor…' : tf('checkout')}
                    </Button>
                  </div>
                </div>
              ))}
            </div>
          </CardContent>
        </Card>
      )}

      {noShows.length > 0 && (
        <Card className="border-amber-200">
          <CardHeader className="pb-2">
            <CardTitle className="text-sm text-amber-700 flex items-center gap-2">
              <Clock className="w-4 h-4" /> {tf('noShowList')}
            </CardTitle>
          </CardHeader>
          <CardContent>
            <div className="space-y-2">
              {noShows.map(b => (
                <div key={b.id} className="flex items-center justify-between p-2 bg-amber-50 rounded border border-amber-100 text-xs">
                  <div>
                    <span className="font-medium text-gray-800">{b.guest_name || tf('guest')}</span>
                    <span className="text-gray-500 ml-2">{tf('room')} {b.room_number}</span>
                    <span className="text-amber-500 ml-2">{tf('expectedCheckin')}: {b.check_in?.slice(0, 10)}</span>
                  </div>
                  <Badge className="bg-amber-100 text-amber-700">No-Show</Badge>
                </div>
              ))}
            </div>
          </CardContent>
        </Card>
      )}

      {(aiPrediction || aiPatterns) && (
        <div className="grid grid-cols-1 md:grid-cols-2 gap-4">
          {aiPrediction && (
            <Card className="bg-gradient-to-br from-green-50 to-blue-50 border-green-200">
              <CardHeader>
                <CardTitle className="flex items-center text-green-700">
                  <TrendingUp className="w-5 h-5 mr-2" />
                  {t('ai.occupancyPrediction')}
                </CardTitle>
              </CardHeader>
              <CardContent>
                <div className="space-y-2 text-sm">
                  <div className="flex justify-between">
                    <span className="text-gray-600">{tf('currentOccupancy')}:</span>
                    <span className="font-semibold">{aiPrediction.current_occupancy?.toFixed(1)}%</span>
                  </div>
                  <div className="flex justify-between">
                    <span className="text-gray-600">{tf('upcomingBookings')}:</span>
                    <span className="font-semibold">{aiPrediction.upcoming_bookings}</span>
                  </div>
                  {aiPrediction.prediction && (
                    <div className="mt-3 p-3 bg-white rounded border border-green-100 space-y-1">
                      {typeof aiPrediction.prediction === 'string' ? (
                        <p className="text-xs text-gray-700">{aiPrediction.prediction}</p>
                      ) : (
                        <>
                          {aiPrediction.prediction.tomorrow_prediction != null && (
                            <p className="text-xs text-gray-700">
                              {tf('tomorrow')}: <span className="font-semibold">
                                {typeof aiPrediction.prediction.tomorrow_prediction === 'object'
                                  ? `${aiPrediction.prediction.tomorrow_prediction.predicted_occupancy_percentage ?? aiPrediction.prediction.tomorrow_prediction.occupancy_percentage ?? '?'}%`
                                  : `${aiPrediction.prediction.tomorrow_prediction}%`}
                              </span>
                            </p>
                          )}
                          {aiPrediction.prediction.next_week_prediction != null && (
                            <p className="text-xs text-gray-700">
                              {tf('next7days')}: <span className="font-semibold">
                                {typeof aiPrediction.prediction.next_week_prediction === 'object'
                                  ? `${aiPrediction.prediction.next_week_prediction.predicted_average_occupancy_percentage ?? aiPrediction.prediction.next_week_prediction.occupancy_percentage ?? '?'}%`
                                  : `${aiPrediction.prediction.next_week_prediction}%`}
                              </span>
                            </p>
                          )}
                        </>
                      )}
                    </div>
                  )}
                </div>
                <div className="text-xs text-gray-500 mt-2">{t('ai.poweredBy')}</div>
              </CardContent>
            </Card>
          )}

          {aiPatterns && (
            <Card className="bg-gradient-to-br from-indigo-50 to-pink-50 border-indigo-200">
              <CardHeader>
                <CardTitle className="flex items-center text-indigo-700">
                  <Users className="w-5 h-5 mr-2" />
                  {t('ai.guestPatterns')}
                </CardTitle>
              </CardHeader>
              <CardContent>
                {aiPatterns.insights && Array.isArray(aiPatterns.insights) ? (
                  <div className="space-y-1">
                    {aiPatterns.insights.map((insight, idx) => (
                      <p key={idx} className="text-sm text-gray-700">{insight}</p>
                    ))}
                  </div>
                ) : (
                  <p className="text-sm text-gray-700">{tf('guestAnalysis')}</p>
                )}
                <div className="text-xs text-gray-500 mt-2">{t('ai.poweredBy')}</div>
              </CardContent>
            </Card>
          )}
        </div>
      )}

      <Tabs defaultValue="arrivals">
        <TabsList>
          <TabsTrigger value="arrivals">{t('pms.arrivals')}</TabsTrigger>
          <TabsTrigger value="departures">{t('pms.departures')}</TabsTrigger>
          <TabsTrigger value="inhouse">{t('pms.inHouse')}</TabsTrigger>
        </TabsList>

        <TabsContent value="arrivals" className="space-y-3">
          {arrivals.length === 0 && (
            <div className="text-center py-8 text-slate-400 text-sm">{tf('noArrivalsToday')}</div>
          )}
          {arrivals.map((booking) => {
            const isDirty = booking.room?.status === 'dirty' || booking.room?.status === 'cleaning';
            const isVip = booking.guest?.vip_status;
            return (
              <Card key={booking.id} className={`transition-all hover:shadow-md ${isDirty ? 'border-l-4 border-l-amber-400' : ''} ${isVip ? 'ring-1 ring-indigo-200' : ''}`}
                data-testid={`arrival-card-${booking.id}`}>
                <CardContent className="pt-5 pb-4">
                  <div className="flex justify-between items-start gap-4">
                    <div className="min-w-0 flex-1">
                      <div className="flex items-center gap-2 mb-1">
                        <span className="font-bold text-base text-slate-800">{booking.guest?.name}</span>
                        {isVip && <Badge className="bg-indigo-100 text-indigo-700 text-[10px]"><Star className="w-3 h-3 mr-0.5" />VIP</Badge>}
                      </div>
                      <div className="text-sm text-slate-500">{tf('room')} {booking.room?.room_number} — {booking.room?.room_type}</div>
                      <div className="text-xs text-slate-400 mt-0.5">{new Date(booking.check_in).toLocaleDateString()} - {new Date(booking.check_out).toLocaleDateString()}</div>
                      <div className="flex flex-wrap gap-1.5 mt-2">
                        {isDirty && (
                          <span className="inline-flex items-center gap-1 text-[11px] bg-amber-50 border border-amber-200 text-amber-700 rounded-md px-2 py-0.5">
                            <Calendar className="w-3 h-3" /> {tf('roomDirty')}
                          </span>
                        )}
                        {booking.balance > 0 && (
                          <span className="inline-flex items-center gap-1 text-[11px] bg-red-50 border border-red-200 text-red-700 rounded-md px-2 py-0.5">
                            {tf('balance')}: {booking.balance?.toFixed(2)} {t('pmsComponents.common.currency')}
                          </span>
                        )}
                      </div>
                    </div>
                    <div className="flex flex-col gap-1.5 flex-shrink-0">
                      {booking.status === 'confirmed' && (
                        <Button size="sm" className={`h-9 ${isDirty ? 'bg-amber-500 hover:bg-amber-600' : 'bg-[#C09D63] hover:bg-[#B08D55]'} text-white`}
                          onClick={async () => {
                            if (isDirty) {
                              if (!await confirmDialog({ message: tf('dirtyWarning'), variant: 'danger' })) return;
                            }
                            await handleCheckIn(booking.id, isDirty);
                          }} data-testid={`checkin-${booking.id}`}>
                          <LogIn className="w-4 h-4 mr-1.5" /> {isDirty ? tf('checkinDirty') : tf('checkin')}
                        </Button>
                      )}
                      <Button variant="outline" size="sm" className="h-8 text-xs" onClick={() => loadFolio(booking.id)}>{tf('folio')}</Button>
                      <Button variant="ghost" size="sm" className="h-7 text-xs text-gray-500"
                        onClick={() => printRegistrationCard(booking, booking.guest, booking.room, tenant)}>
                        <Printer className="w-3 h-3 mr-1" /> {tf('regCard')}
                      </Button>
                    </div>
                  </div>
                </CardContent>
              </Card>
            );
          })}
        </TabsContent>

        <TabsContent value="departures" className="space-y-3">
          {departures.length === 0 && (
            <div className="text-center py-8 text-slate-400 text-sm">{tf('noDeparturesToday')}</div>
          )}
          {departures.map((booking) => {
            const hasBalance = booking.balance > 0;
            return (
              <Card key={booking.id} className={`transition-all hover:shadow-md ${hasBalance ? 'border-l-4 border-l-red-400' : 'border-l-4 border-l-emerald-400'}`}
                data-testid={`departure-card-${booking.id}`}>
                <CardContent className="pt-5 pb-4">
                  <div className="flex justify-between items-start gap-4">
                    <div className="min-w-0 flex-1">
                      <div className="font-bold text-base text-slate-800">{booking.guest?.name}</div>
                      <div className="text-sm text-slate-500">{tf('room')} {booking.room?.room_number}</div>
                      <div className="text-xs text-slate-400 mt-0.5">{tf('checkout')}: {new Date(booking.check_out).toLocaleDateString()}</div>
                      {hasBalance && (
                        <div className="mt-2 inline-flex items-center gap-1 text-[11px] bg-red-50 border border-red-200 text-red-700 rounded-md px-2 py-0.5">
                          <span className="font-semibold">{tf('balance')}: {booking.balance?.toFixed(2)} {t('pmsComponents.common.currency')}</span>
                          — {tf('collectFirst')}
                        </div>
                      )}
                    </div>
                    <div className="flex flex-col gap-1.5 flex-shrink-0">
                      <Button variant="outline" size="sm" className="h-8 text-xs" onClick={() => loadFolio(booking.id)}>{tf('folio')}</Button>
                      {hasBalance && (
                        <Button type="button" size="sm" variant="outline"
                          className="h-8 text-xs border-emerald-300 text-emerald-700 hover:bg-emerald-50"
                          onClick={() => openQuickPayment(booking)}
                          data-testid={`departure-payment-${booking.id}`}>
                          <CreditCard className="w-4 h-4 mr-1.5" /> Ödeme Al
                        </Button>
                      )}
                      <Button type="button" size="sm"
                        className={`h-9 ${hasBalance ? 'bg-slate-300 text-slate-500 cursor-not-allowed' : 'bg-blue-600 hover:bg-blue-700 text-white'}`}
                        onClick={() => requestCheckout(booking)} disabled={hasBalance || checkoutInProgress === booking.id}
                        data-testid={`checkout-${booking.id}`}>
                        <LogOut className="w-4 h-4 mr-1.5" />
                        {checkoutInProgress === booking.id ? 'İşleniyor…' : tf('checkout')}
                      </Button>
                    </div>
                  </div>
                </CardContent>
              </Card>
            );
          })}
        </TabsContent>

        <TabsContent value="inhouse" className="space-y-3">
          {inhouse.length === 0 && (
            <div className="text-center py-8 text-slate-400 text-sm">{tf('noInhouseGuests')}</div>
          )}
          {inhouse.map((booking) => (
            <Card key={booking.id} className="transition-all hover:shadow-md" data-testid={`inhouse-card-${booking.id}`}>
              <CardContent className="pt-5 pb-4">
                <div className="flex justify-between items-start gap-4">
                  <div className="min-w-0 flex-1">
                    <div className="font-bold text-base text-slate-800">{booking.guest?.name}</div>
                    <div className="text-sm text-slate-500">{tf('room')} {booking.room?.room_number} — {booking.room?.room_type}</div>
                    <div className="text-xs text-slate-400 mt-0.5">
                      {new Date(booking.check_in).toLocaleDateString('tr-TR')} - {new Date(booking.check_out).toLocaleDateString('tr-TR')}
                    </div>
                  </div>
                  <Button variant="outline" size="sm" className="h-8 text-xs" onClick={() => loadFolio(booking.id)}>
                    {tf('manageFolio')}
                  </Button>
                </div>
              </CardContent>
            </Card>
          ))}
        </TabsContent>
      </Tabs>

      <Dialog open={!!quickPaymentBooking} onOpenChange={(open) => !open && closeQuickPayment()}>
        <DialogContent className="max-w-md">
          <DialogHeader>
            <DialogTitle>Hızlı Ödeme Al</DialogTitle>
          </DialogHeader>
          {quickPaymentBooking && (
            <div className="space-y-4">
              <div className="rounded-lg border border-slate-200 bg-slate-50 p-3">
                <div className="font-semibold text-slate-900">
                  {quickPaymentBooking.guest_name || quickPaymentBooking.guest?.name || tf('guest')}
                </div>
                <div className="mt-1 flex items-center justify-between text-sm text-slate-600">
                  <span>{tf('room')} {quickPaymentBooking.room_number || quickPaymentBooking.room?.room_number || '-'}</span>
                  <span className="font-semibold text-red-700">
                    {tf('balance')}: {formatMoney(quickPaymentBooking.balance)} {t('pmsComponents.common.currency')}
                  </span>
                </div>
              </div>
              <div className="space-y-2">
                <Label htmlFor="frontdesk-quick-payment-amount">Tutar</Label>
                <Input
                  id="frontdesk-quick-payment-amount"
                  data-testid="frontdesk-quick-payment-amount"
                  type="number"
                  min="0.01"
                  step="0.01"
                  max={Number(quickPaymentBooking.balance) || undefined}
                  value={quickPaymentAmount}
                  onChange={(event) => setQuickPaymentAmount(event.target.value)}
                  disabled={quickPaymentInProgress}
                />
              </div>
              <div className="space-y-2">
                <Label>Tahsilat / Aktarım Yöntemi</Label>
                <Select value={quickPaymentMethod} onValueChange={handleQuickPaymentMethodChange} disabled={quickPaymentInProgress}>
                  <SelectTrigger data-testid="frontdesk-quick-payment-method">
                    <SelectValue />
                  </SelectTrigger>
                  <SelectContent>
                    <SelectItem value="card">Kredi / Banka Kartı</SelectItem>
                    <SelectItem value="cash">Nakit</SelectItem>
                    <SelectItem value="bank_transfer">Havale / EFT</SelectItem>
                    <SelectItem value="city_ledger">Cari Hesaba Aktar</SelectItem>
                  </SelectContent>
                </Select>
              </div>
              {quickPaymentMethod === 'city_ledger' && (
                <div className="space-y-2">
                  <Label>Cari Hesap</Label>
                  <Select
                    value={quickPaymentCariAccountId}
                    onValueChange={setQuickPaymentCariAccountId}
                    disabled={quickPaymentInProgress || quickPaymentCariLoading}
                  >
                    <SelectTrigger data-testid="frontdesk-quick-payment-cari-account">
                      <SelectValue placeholder={quickPaymentCariLoading ? 'Cari hesaplar yükleniyor…' : 'Cari hesap seçin'} />
                    </SelectTrigger>
                    <SelectContent>
                      {quickPaymentCariAccounts.map((account) => (
                        <SelectItem key={account.id} value={account.id}>
                          {account.name || account.title || account.account_name || account.id}
                        </SelectItem>
                      ))}
                    </SelectContent>
                  </Select>
                  {!quickPaymentCariLoading && quickPaymentCariAccounts.length === 0 && (
                    <p className="text-xs text-amber-700">Aktarım için önce Cari Hesaplar ekranında aktif bir cari oluşturun.</p>
                  )}
                </div>
              )}
              <p className="text-xs text-slate-500">
                {quickPaymentMethod === 'city_ledger'
                  ? 'Tutar misafirin folyosunu kapatır ve seçilen cari hesabın borcuna tek işlem olarak yansır.'
                  : 'Ödeme doğrudan misafirin açık folyosuna işlenir. Bakiye kapandığında çıkış butonu otomatik olarak kullanılabilir hâle gelir.'}
              </p>
              <div className="flex justify-end gap-2 border-t pt-4">
                <Button type="button" variant="outline" onClick={closeQuickPayment} disabled={quickPaymentInProgress}>
                  Vazgeç
                </Button>
                <Button
                  type="button"
                  onClick={submitQuickPayment}
                  disabled={quickPaymentInProgress || !Number.isFinite(Number(quickPaymentAmount)) || Number(quickPaymentAmount) <= 0 || (quickPaymentMethod === 'city_ledger' && !quickPaymentCariAccountId)}
                  data-testid="frontdesk-quick-payment-submit"
                  className="bg-emerald-600 text-white hover:bg-emerald-700"
                >
                  {quickPaymentInProgress ? <Loader2 className="mr-2 h-4 w-4 animate-spin" /> : <CreditCard className="mr-2 h-4 w-4" />}
                  {quickPaymentInProgress ? 'İşleniyor…' : quickPaymentMethod === 'city_ledger' ? 'Cari Hesaba Aktar' : 'Ödemeyi Folyoya İşle'}
                </Button>
              </div>
            </div>
          )}
        </DialogContent>
      </Dialog>

      <Dialog open={showGroupCheckin} onOpenChange={setShowGroupCheckin}>
        <DialogContent className="max-w-lg">
          <DialogHeader>
            <DialogTitle className="flex items-center gap-2"><CheckSquare className="w-5 h-5" /> {tf('batchTitle')}</DialogTitle>
          </DialogHeader>
          <div className="space-y-3 py-2">
            <p className="text-sm text-gray-500">{tf('batchDesc')}</p>
            <div className="max-h-[300px] overflow-y-auto space-y-1">
              {groupArrivals.map(b => (
                <label key={b.id} className="flex items-center gap-3 p-2 rounded border hover:bg-gray-50 cursor-pointer text-xs">
                  <input type="checkbox" checked={groupCheckinIds.has(b.id)} onChange={() => toggleGroupCheckin(b.id)} />
                  <span className="font-medium">{b.guest?.name || b.guest_name}</span>
                  <span className="text-gray-400">{tf('room')} {b.room?.room_number || b.room_number}</span>
                  <Badge variant="outline" className="ml-auto text-[9px]">{b.status}</Badge>
                </label>
              ))}
            </div>
            <Button className="w-full" disabled={groupCheckinIds.size === 0} onClick={handleBatchCheckin}>
              <CheckSquare className="w-4 h-4 mr-2" /> {t('pmsComponents.frontdesk.checkinCount', { count: groupCheckinIds.size })}
            </Button>
          </div>
        </DialogContent>
      </Dialog>
    </TabsContent>
  );
};

export default memo(FrontdeskTab);
