import React, { memo, useState, useMemo } from 'react';
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
  AlertTriangle, Clock, UserPlus, CheckSquare, Printer
} from 'lucide-react';
import { printRegistrationCard } from '@/components/pms/PrintTemplates';

const FrontdeskTab = ({
  arrivals,
  departures,
  inhouse,
  aiPrediction,
  aiPatterns,
  bookings,
  handleCheckIn,
  handleCheckOut,
  loadFolio,
  loadFrontDeskData,
  loading,
  error,
}) => {
  const { t } = useTranslation();
  const tf = (k) => t(`pmsComponents.frontdesk.${k}`);
  const [showWalkIn, setShowWalkIn] = useState(false);
  const [showGroupCheckin, setShowGroupCheckin] = useState(false);
  const [walkInForm, setWalkInForm] = useState({ guest_name: '', phone: '', id_number: '', room_number: '', nights: 1, rate: 0 });
  const [groupCheckinIds, setGroupCheckinIds] = useState(new Set());

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
        <Card className="cursor-pointer hover:shadow-lg transition" onClick={loadFrontDeskData}>
          <CardHeader className="pb-2">
            <CardTitle className="text-sm">{t('pms.todayArrivals')}</CardTitle>
          </CardHeader>
          <CardContent>
            <div className="text-3xl font-bold">{arrivals.length}</div>
            <p className="text-xs text-gray-500">{t('pms.expectedCheckins')}</p>
          </CardContent>
        </Card>
        <Card className="cursor-pointer hover:shadow-lg transition" onClick={loadFrontDeskData}>
          <CardHeader className="pb-2">
            <CardTitle className="text-sm">{t('pms.todayDepartures')}</CardTitle>
          </CardHeader>
          <CardContent>
            <div className="text-3xl font-bold">{departures.length}</div>
            <p className="text-xs text-gray-500">{t('pms.expectedCheckouts')}</p>
          </CardContent>
        </Card>
        <Card className="cursor-pointer hover:shadow-lg transition" onClick={loadFrontDeskData}>
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
                        onClick={() => printRegistrationCard(booking, booking.guest, booking.room)}>
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

      <Dialog open={showWalkIn} onOpenChange={setShowWalkIn}>
        <DialogContent>
          <DialogHeader>
            <DialogTitle className="flex items-center gap-2"><UserPlus className="w-5 h-5" /> {tf('walkInTitle')}</DialogTitle>
          </DialogHeader>
          <div className="space-y-3 py-2">
            <div className="grid grid-cols-2 gap-3">
              <div><Label>{tf('guestName')}</Label><Input value={walkInForm.guest_name} onChange={e => setWalkInForm(p => ({ ...p, guest_name: e.target.value }))} /></div>
              <div><Label>{t('pmsComponents.guests.phone')}</Label><Input value={walkInForm.phone} onChange={e => setWalkInForm(p => ({ ...p, phone: e.target.value }))} /></div>
            </div>
            <div className="grid grid-cols-2 gap-3">
              <div><Label>{tf('idPassport')}</Label><Input value={walkInForm.id_number} onChange={e => setWalkInForm(p => ({ ...p, id_number: e.target.value }))} /></div>
              <div><Label>{tf('roomNo')}</Label><Input value={walkInForm.room_number} onChange={e => setWalkInForm(p => ({ ...p, room_number: e.target.value }))} /></div>
            </div>
            <div className="grid grid-cols-2 gap-3">
              <div><Label>{tf('nights')}</Label><Input type="number" min="1" value={walkInForm.nights} onChange={e => setWalkInForm(p => ({ ...p, nights: parseInt(e.target.value) || 1 }))} /></div>
              <div><Label>{tf('nightlyRate')}</Label><Input type="number" value={walkInForm.rate} onChange={e => setWalkInForm(p => ({ ...p, rate: parseFloat(e.target.value) || 0 }))} /></div>
            </div>
            <Button className="w-full bg-emerald-600 hover:bg-emerald-700" onClick={() => {
              if (!walkInForm.guest_name?.trim()) { return; }
              if (!walkInForm.room_number?.trim()) { return; }
              if (!walkInForm.rate || walkInForm.rate <= 0) { return; }
              setShowWalkIn(false);
            }} disabled={!walkInForm.guest_name?.trim() || !walkInForm.room_number?.trim() || !walkInForm.rate || walkInForm.rate <= 0}>
              <LogIn className="w-4 h-4 mr-2" /> {tf('quickCheckin')}
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
