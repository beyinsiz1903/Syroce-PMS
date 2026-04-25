import React, { memo, useState, useMemo, useCallback } from 'react';
import axios from 'axios';
import { toast } from 'sonner';
import { useTranslation } from 'react-i18next';
import { Card, CardContent, CardHeader, CardTitle } from '@/components/ui/card';
import { Badge } from '@/components/ui/badge';
import { Button } from '@/components/ui/button';
import { Tabs, TabsContent, TabsList, TabsTrigger } from '@/components/ui/tabs';
import { Input } from '@/components/ui/input';
import { Label } from '@/components/ui/label';
import { Dialog, DialogContent, DialogHeader, DialogTitle } from '@/components/ui/dialog';
import { TableLoadingSkeleton } from '@/utils/lazyLoad';
import {
  Calendar, Users, TrendingUp, LogIn, LogOut, Star,
  AlertTriangle, Clock, UserPlus, CheckSquare, Printer, CheckCircle2, XCircle
} from 'lucide-react';
import { printRegistrationCard } from '@/components/pms/PrintTemplates';

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
  const tf = useCallback((k, opts) => t(`pmsComponents.frontdesk.${k}`, opts), [t]);
  const [showWalkIn, setShowWalkIn] = useState(false);
  const [showGroupCheckin, setShowGroupCheckin] = useState(false);
  const [walkInForm, setWalkInForm] = useState({ guest_name: '', phone: '', email: '', id_number: '', room_number: '', nights: 1, rate: 0 });
  const [walkInSubmitting, setWalkInSubmitting] = useState(false);
  const [groupCheckinIds, setGroupCheckinIds] = useState(new Set());

  // Live preview: lookup room by typed room_number
  const matchedRoom = useMemo(() => {
    const rn = (walkInForm.room_number || '').trim();
    if (!rn) return null;
    return rooms.find(r => String(r.room_number) === rn) || null;
  }, [walkInForm.room_number, rooms]);

  const isRoomBookable = matchedRoom && ['available', 'inspected'].includes(matchedRoom.status);

  // Quick-pick: first 6 currently bookable rooms
  const availableRoomQuickPicks = useMemo(() => {
    return rooms
      .filter(r => ['available', 'inspected'].includes(r.status))
      .slice(0, 6);
  }, [rooms]);

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

  const formatMoney = (n) => {
    const v = Number(n) || 0;
    return v.toLocaleString(undefined, { minimumFractionDigits: 0, maximumFractionDigits: 2 });
  };

  const resetWalkInForm = () => {
    setWalkInForm({ guest_name: '', phone: '', email: '', id_number: '', room_number: '', nights: 1, rate: 0 });
  };

  const handleWalkInSubmit = async () => {
    if (!walkInForm.guest_name?.trim()) { toast.error(tf('walkInGuestRequired')); return; }
    if (!walkInForm.room_number?.trim()) { toast.error(tf('walkInRoomRequired')); return; }
    if (!walkInForm.rate || walkInForm.rate <= 0) { toast.error(tf('walkInRateRequired')); return; }
    if (!matchedRoom) { toast.error(tf('walkInRoomNotFound', { roomNo: walkInForm.room_number })); return; }
    if (!isRoomBookable) {
      toast.error(tf('walkInRoomNotAvailable', { roomNo: matchedRoom.room_number, status: matchedRoom.status }));
      return;
    }

    setWalkInSubmitting(true);
    try {
      const payload = {
        guest_name: walkInForm.guest_name.trim(),
        guest_phone: walkInForm.phone?.trim() || '',
        guest_email: walkInForm.email?.trim() || null,
        guest_id_number: walkInForm.id_number?.trim() || null,
        room_id: matchedRoom.id,
        nights: Math.max(1, parseInt(walkInForm.nights) || 1),
        adults: 1,
        children: 0,
        rate_per_night: parseFloat(walkInForm.rate) || 0,
      };
      const res = await axios.post('/frontdesk/walk-in-booking', payload);
      const data = res.data || {};
      toast.success(tf('walkInSuccess', {
        roomNo: data.room_number || matchedRoom.room_number,
        guest: walkInForm.guest_name.trim(),
      }));
      resetWalkInForm();
      setShowWalkIn(false);
      // Refresh both front desk data and the rooms/bookings list so the new check-in is visible everywhere
      try { await Promise.all([loadFrontDeskData?.(), loadData?.()]); } catch (_) { /* non-fatal */ }
    } catch (err) {
      const msg = err?.response?.data?.detail || err?.message || tf('walkInBookingFailed');
      toast.error(typeof msg === 'string' ? msg : tf('walkInBookingFailed'));
    } finally {
      setWalkInSubmitting(false);
    }
  };

  const today = useMemo(() => new Date().toISOString().split('T')[0], []);

  const overstays = useMemo(() => {
    if (!bookings) return [];
    return bookings.filter(b => {
      if (b.status !== 'checked_in') return false;
      const co = (b.check_out || '').slice(0, 10);
      return co && co < today;
    });
  }, [bookings, today]);

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
        <Card>
          <CardHeader className="pb-2">
            <CardTitle className="text-sm">{t('pms.todayArrivals')}</CardTitle>
          </CardHeader>
          <CardContent>
            <div className="text-3xl font-bold">{arrivals.length}</div>
            <p className="text-xs text-gray-500">{t('pms.expectedCheckins')}</p>
          </CardContent>
        </Card>
        <Card>
          <CardHeader className="pb-2">
            <CardTitle className="text-sm">{t('pms.todayDepartures')}</CardTitle>
          </CardHeader>
          <CardContent>
            <div className="text-3xl font-bold">{departures.length}</div>
            <p className="text-xs text-gray-500">{t('pms.expectedCheckouts')}</p>
          </CardContent>
        </Card>
        <Card>
          <CardHeader className="pb-2">
            <CardTitle className="text-sm">{t('pms.inHouseGuests')}</CardTitle>
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
          <Card className="border-amber-200 bg-amber-50">
            <CardHeader className="pb-2">
              <CardTitle className="text-sm text-amber-700 flex items-center gap-1">
                <Clock className="w-4 h-4" /> No-Show
              </CardTitle>
            </CardHeader>
            <CardContent>
              <div className="text-3xl font-bold text-amber-700">{noShows.length}</div>
              <p className="text-xs text-amber-500">{tf('didntCome')}</p>
            </CardContent>
          </Card>
        )}
      </div>

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
                      <Badge variant="outline" className="text-[9px] border-purple-300 text-purple-700">
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
        <Button variant="outline" size="sm" onClick={() => setShowWalkIn(true)}>
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
                  <Button size="sm" variant="outline" className="h-6 text-xs border-red-300 text-red-700" onClick={() => handleCheckOut(b.id)}>
                    <LogOut className="w-3 h-3 mr-1" /> {tf('checkout')}
                  </Button>
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
            <Card className="bg-gradient-to-br from-purple-50 to-pink-50 border-purple-200">
              <CardHeader>
                <CardTitle className="flex items-center text-purple-700">
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
              <Card key={booking.id} className={`transition-all hover:shadow-md ${isDirty ? 'border-l-4 border-l-amber-400' : ''} ${isVip ? 'ring-1 ring-purple-200' : ''}`}
                data-testid={`arrival-card-${booking.id}`}>
                <CardContent className="pt-5 pb-4">
                  <div className="flex justify-between items-start gap-4">
                    <div className="min-w-0 flex-1">
                      <div className="flex items-center gap-2 mb-1">
                        <span className="font-bold text-base text-slate-800">{booking.guest?.name}</span>
                        {isVip && <Badge className="bg-purple-100 text-purple-700 text-[10px]"><Star className="w-3 h-3 mr-0.5" />VIP</Badge>}
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
                          onClick={() => {
                            if (isDirty) {
                              if (!window.confirm(tf('dirtyWarning'))) return;
                            }
                            handleCheckIn(booking.id);
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
                      <Button size="sm"
                        className={`h-9 ${hasBalance ? 'bg-slate-300 text-slate-500 cursor-not-allowed' : 'bg-blue-600 hover:bg-blue-700 text-white'}`}
                        onClick={() => handleCheckOut(booking.id)} disabled={hasBalance}
                        data-testid={`checkout-${booking.id}`}>
                        <LogOut className="w-4 h-4 mr-1.5" /> {tf('checkout')}
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

      <Dialog open={showWalkIn} onOpenChange={(open) => {
        if (!open && walkInSubmitting) return; // prevent closing mid-submit
        setShowWalkIn(open);
        if (!open) resetWalkInForm();
      }}>
        <DialogContent>
          <DialogHeader>
            <DialogTitle className="flex items-center gap-2"><UserPlus className="w-5 h-5" /> {tf('walkInTitle')}</DialogTitle>
          </DialogHeader>
          <div className="space-y-3 py-2">
            <p className="text-xs text-gray-500 -mt-1">{tf('walkInIntro')}</p>
            <div className="grid grid-cols-1 md:grid-cols-3 gap-3">
              <div><Label>{tf('guestName')}</Label><Input value={walkInForm.guest_name} onChange={e => setWalkInForm(p => ({ ...p, guest_name: e.target.value }))} /></div>
              <div><Label>{t('pmsComponents.guests.phone')}</Label><Input value={walkInForm.phone} onChange={e => setWalkInForm(p => ({ ...p, phone: e.target.value }))} /></div>
              <div><Label>{tf('emailOptional')}</Label><Input type="email" value={walkInForm.email} onChange={e => setWalkInForm(p => ({ ...p, email: e.target.value }))} placeholder="ornek@mail.com" /></div>
            </div>
            <div className="grid grid-cols-2 gap-3">
              <div><Label>{tf('idPassport')}</Label><Input value={walkInForm.id_number} onChange={e => setWalkInForm(p => ({ ...p, id_number: e.target.value }))} /></div>
              <div>
                <Label>{tf('roomNo')}</Label>
                <Input value={walkInForm.room_number} onChange={e => setWalkInForm(p => ({ ...p, room_number: e.target.value }))} placeholder={tf('roomNoPlaceholder')} />
                {walkInForm.room_number?.trim() && (
                  matchedRoom ? (
                    isRoomBookable ? (
                      <p className="text-[11px] text-emerald-700 mt-1 flex items-center gap-1">
                        <CheckCircle2 className="w-3 h-3" />
                        {tf('roomBookable', { type: matchedRoom.room_type || '-', floor: matchedRoom.floor ?? '-' })}
                      </p>
                    ) : (
                      <p className="text-[11px] text-red-700 mt-1 flex items-center gap-1">
                        <XCircle className="w-3 h-3" />
                        {tf('roomBlocked', { status: matchedRoom.status })}
                      </p>
                    )
                  ) : (
                    <p className="text-[11px] text-amber-700 mt-1 flex items-center gap-1">
                      <AlertTriangle className="w-3 h-3" /> {tf('roomNotFoundHint')}
                    </p>
                  )
                )}
              </div>
            </div>
            <div className="grid grid-cols-2 gap-3">
              <div><Label>{tf('nights')}</Label><Input type="number" min="1" value={walkInForm.nights} onChange={e => setWalkInForm(p => ({ ...p, nights: parseInt(e.target.value) || 1 }))} /></div>
              <div><Label>{tf('nightlyRate')}</Label><Input type="number" value={walkInForm.rate} onChange={e => setWalkInForm(p => ({ ...p, rate: parseFloat(e.target.value) || 0 }))} /></div>
            </div>

            {availableRoomQuickPicks.length > 0 && (
              <div className="rounded-md border border-emerald-100 bg-emerald-50/60 p-2">
                <p className="text-[11px] text-emerald-800 mb-1 font-medium">{tf('quickPickAvailable')}</p>
                <div className="flex flex-wrap gap-1">
                  {availableRoomQuickPicks.map(r => (
                    <button
                      key={r.id}
                      type="button"
                      onClick={() => setWalkInForm(p => ({
                        ...p,
                        room_number: String(r.room_number),
                        rate: p.rate || r.base_price || r.price || 0,
                      }))}
                      className="px-2 py-0.5 rounded border border-emerald-300 bg-white text-[11px] text-emerald-800 hover:bg-emerald-100"
                    >
                      {r.room_number} · {r.room_type || '-'}
                    </button>
                  ))}
                </div>
              </div>
            )}

            <div className="rounded-md border bg-gray-50 p-2 text-[11px] text-gray-600">
              {tf('walkInWhatHappens')}
            </div>

            <Button
              className="w-full bg-emerald-600 hover:bg-emerald-700"
              onClick={handleWalkInSubmit}
              disabled={
                walkInSubmitting ||
                !walkInForm.guest_name?.trim() ||
                !walkInForm.room_number?.trim() ||
                !walkInForm.rate || walkInForm.rate <= 0 ||
                !isRoomBookable
              }
            >
              <LogIn className="w-4 h-4 mr-2" />
              {walkInSubmitting ? tf('walkInProcessing') : tf('quickCheckin')}
            </Button>
          </div>
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
