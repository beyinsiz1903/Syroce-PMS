import React, { memo } from 'react';
import { Card, CardContent, CardHeader, CardTitle } from '@/components/ui/card';
import { Badge } from '@/components/ui/badge';
import { Button } from '@/components/ui/button';
import { Tabs, TabsContent, TabsList, TabsTrigger } from '@/components/ui/tabs';
import { TableLoadingSkeleton } from '@/utils/lazyLoad';
import { 
  Calendar,
  Users,
  TrendingUp,
  LogIn,
  LogOut,
  Star
} from 'lucide-react';

/**
 * Front Desk main tab content
 * Extracted from PMSModule to reduce re-render cost.
 */
const FrontdeskTab = ({
  t,
  arrivals,
  departures,
  inhouse,
  aiPrediction,
  aiPatterns,
  handleCheckIn,
  handleCheckOut,
  loadFolio,
  loadFrontDeskData,
}) => {
  return (
    <TabsContent value="frontdesk" className="space-y-6">
      <div className="grid grid-cols-1 md:grid-cols-3 gap-4">
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
      </div>

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
                    <span className="text-gray-600">Current Occupancy:</span>
                    <span className="font-semibold">{aiPrediction.current_occupancy?.toFixed(1)}%</span>
                  </div>
                  <div className="flex justify-between">
                    <span className="text-gray-600">Upcoming Bookings:</span>
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
                              Tomorrow: <span className="font-semibold">
                                {typeof aiPrediction.prediction.tomorrow_prediction === 'object'
                                  ? `${aiPrediction.prediction.tomorrow_prediction.predicted_occupancy_percentage ?? aiPrediction.prediction.tomorrow_prediction.occupancy_percentage ?? '?'}%`
                                  : `${aiPrediction.prediction.tomorrow_prediction}%`}
                              </span>
                              {typeof aiPrediction.prediction.tomorrow_prediction === 'object' && aiPrediction.prediction.tomorrow_prediction.confidence_level && (
                                <span className="text-gray-400 ml-1">({aiPrediction.prediction.tomorrow_prediction.confidence_level})</span>
                              )}
                            </p>
                          )}
                          {aiPrediction.prediction.next_week_prediction != null && (
                            <p className="text-xs text-gray-700">
                              Next 7 days: <span className="font-semibold">
                                {typeof aiPrediction.prediction.next_week_prediction === 'object'
                                  ? `${aiPrediction.prediction.next_week_prediction.predicted_average_occupancy_percentage ?? aiPrediction.prediction.next_week_prediction.occupancy_percentage ?? '?'}%`
                                  : `${aiPrediction.prediction.next_week_prediction}%`}
                              </span>
                              {typeof aiPrediction.prediction.next_week_prediction === 'object' && aiPrediction.prediction.next_week_prediction.confidence_level && (
                                <span className="text-gray-400 ml-1">({aiPrediction.prediction.next_week_prediction.confidence_level})</span>
                              )}
                            </p>
                          )}
                          {typeof aiPrediction.prediction.patterns === 'string' && (
                            <p className="text-xs text-gray-600 mt-1">{aiPrediction.prediction.patterns}</p>
                          )}
                          {Array.isArray(aiPrediction.prediction.patterns) && aiPrediction.prediction.patterns.length > 0 && (
                            <ul className="list-disc list-inside text-xs text-gray-700">
                              {aiPrediction.prediction.patterns.map((item, idx) => (
                                <li key={idx}>{typeof item === 'string' ? item : JSON.stringify(item)}</li>
                              ))}
                            </ul>
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
                  <p className="text-sm text-gray-700">Guest pattern analysis available</p>
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
            <div className="text-center py-8 text-slate-400 text-sm">Bugun beklenen gelis yok</div>
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
                        <span className="font-bold text-base text-slate-800" style={{ fontFamily: 'Manrope' }}>{booking.guest?.name}</span>
                        {isVip && <Badge className="bg-purple-100 text-purple-700 text-[10px]"><Star className="w-3 h-3 mr-0.5" />VIP</Badge>}
                      </div>
                      <div className="text-sm text-slate-500">Oda {booking.room?.room_number} — {booking.room?.room_type}</div>
                      <div className="text-xs text-slate-400 mt-0.5">{new Date(booking.check_in).toLocaleDateString('tr-TR')} - {new Date(booking.check_out).toLocaleDateString('tr-TR')}</div>
                      {/* Operational alerts inline */}
                      <div className="flex flex-wrap gap-1.5 mt-2">
                        {isDirty && (
                          <span className="inline-flex items-center gap-1 text-[11px] bg-amber-50 border border-amber-200 text-amber-700 rounded-md px-2 py-0.5">
                            <Calendar className="w-3 h-3" /> Oda kirli — ~{booking.room?.status === 'cleaning' ? '8' : '15'} dk
                          </span>
                        )}
                        {booking.balance > 0 && (
                          <span className="inline-flex items-center gap-1 text-[11px] bg-red-50 border border-red-200 text-red-700 rounded-md px-2 py-0.5">
                            Bakiye: {booking.balance?.toFixed(2)} TL
                          </span>
                        )}
                      </div>
                    </div>
                    <div className="flex flex-col gap-1.5 flex-shrink-0">
                      {booking.status === 'confirmed' && (
                        <Button size="sm" className="bg-[#C09D63] hover:bg-[#B08D55] text-white h-9" onClick={() => handleCheckIn(booking.id)} data-testid={`checkin-${booking.id}`}>
                          <LogIn className="w-4 h-4 mr-1.5" />
                          Giris Yap
                        </Button>
                      )}
                      <Button variant="outline" size="sm" className="h-8 text-xs" onClick={() => loadFolio(booking.id)} data-testid={`folio-${booking.id}`}>
                        Folyo
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
            <div className="text-center py-8 text-slate-400 text-sm">Bugun beklenen cikis yok</div>
          )}
          {departures.map((booking) => {
            const hasBalance = booking.balance > 0;
            return (
              <Card key={booking.id} className={`transition-all hover:shadow-md ${hasBalance ? 'border-l-4 border-l-red-400' : 'border-l-4 border-l-emerald-400'}`}
                data-testid={`departure-card-${booking.id}`}>
                <CardContent className="pt-5 pb-4">
                  <div className="flex justify-between items-start gap-4">
                    <div className="min-w-0 flex-1">
                      <div className="font-bold text-base text-slate-800" style={{ fontFamily: 'Manrope' }}>{booking.guest?.name}</div>
                      <div className="text-sm text-slate-500">Oda {booking.room?.room_number}</div>
                      <div className="text-xs text-slate-400 mt-0.5">Cikis: {new Date(booking.check_out).toLocaleDateString('tr-TR')}</div>
                      {hasBalance && (
                        <div className="mt-2 inline-flex items-center gap-1 text-[11px] bg-red-50 border border-red-200 text-red-700 rounded-md px-2 py-0.5" data-testid={`dep-balance-${booking.id}`}>
                          <span className="font-semibold">Bakiye: {booking.balance?.toFixed(2)} TL</span>
                          — Cikis icin once tahsil edin
                        </div>
                      )}
                    </div>
                    <div className="flex flex-col gap-1.5 flex-shrink-0">
                      <Button variant="outline" size="sm" className="h-8 text-xs" onClick={() => loadFolio(booking.id)}>
                        Folyo
                      </Button>
                      <Button
                        size="sm"
                        className={`h-9 ${hasBalance ? 'bg-slate-300 text-slate-500 cursor-not-allowed' : 'bg-blue-600 hover:bg-blue-700 text-white'}`}
                        onClick={() => handleCheckOut(booking.id)}
                        disabled={hasBalance}
                        data-testid={`checkout-${booking.id}`}
                      >
                        <LogOut className="w-4 h-4 mr-1.5" />
                        Cikis
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
            <div className="text-center py-8 text-slate-400 text-sm">Su an iceride misafir yok</div>
          )}
          {inhouse.map((booking) => (
            <Card key={booking.id} className="transition-all hover:shadow-md" data-testid={`inhouse-card-${booking.id}`}>
              <CardContent className="pt-5 pb-4">
                <div className="flex justify-between items-start gap-4">
                  <div className="min-w-0 flex-1">
                    <div className="font-bold text-base text-slate-800" style={{ fontFamily: 'Manrope' }}>{booking.guest?.name}</div>
                    <div className="text-sm text-slate-500">Oda {booking.room?.room_number} — {booking.room?.room_type}</div>
                    <div className="text-xs text-slate-400 mt-0.5">
                      {new Date(booking.check_in).toLocaleDateString('tr-TR')} → {new Date(booking.check_out).toLocaleDateString('tr-TR')}
                    </div>
                  </div>
                  <Button variant="outline" size="sm" className="h-8 text-xs" onClick={() => loadFolio(booking.id)}>
                    Folyo Yonet
                  </Button>
                </div>
              </CardContent>
            </Card>
          ))}
        </TabsContent>
      </Tabs>
    </TabsContent>
  );
};

export default memo(FrontdeskTab);
