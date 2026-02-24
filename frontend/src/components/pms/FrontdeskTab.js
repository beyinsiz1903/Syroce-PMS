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
  LogOut
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

        <TabsContent value="arrivals" className="space-y-4">
          {arrivals.map((booking) => (
            <Card key={booking.id}>
              <CardContent className="pt-6">
                <div className="flex justify-between items-center">
                  <div>
                    <div className="font-bold text-lg">{booking.guest?.name}</div>
                    <div className="text-sm text-gray-600">Room {booking.room?.room_number} - {booking.room?.room_type}</div>
                    <div className="text-sm text-gray-500">Check-in: {new Date(booking.check_in).toLocaleDateString()}</div>
                  </div>
                  <div className="space-x-2">
                    {booking.status === 'confirmed' && (
                      <Button onClick={() => handleCheckIn(booking.id)} data-testid={`checkin-${booking.id}`}>
                        <LogIn className="w-4 h-4 mr-2" />
                        Check In
                      </Button>
                    )}
                    <Button variant="outline" onClick={() => loadFolio(booking.id)}>
                      View Folio
                    </Button>
                  </div>
                </div>
              </CardContent>
            </Card>
          ))}
        </TabsContent>

        <TabsContent value="departures" className="space-y-4">
          {departures.map((booking) => (
            <Card key={booking.id}>
              <CardContent className="pt-6">
                <div className="flex justify-between items-center">
                  <div>
                    <div className="font-bold text-lg">{booking.guest?.name}</div>
                    <div className="text-sm text-gray-600">Room {booking.room?.room_number}</div>
                    <div className="text-sm text-gray-500">Check-out: {new Date(booking.check_out).toLocaleDateString()}</div>
                    <div className="text-sm font-medium mt-1">
                      Balance: <span className={booking.balance > 0 ? 'text-red-600' : 'text-green-600'}>
                        ${booking.balance?.toFixed(2) || '0.00'}
                      </span>
                    </div>
                  </div>
                  <div className="space-x-2">
                    <Button variant="outline" onClick={() => loadFolio(booking.id)}>
                      View Folio
                    </Button>
                    <Button
                      onClick={() => handleCheckOut(booking.id)}
                      disabled={booking.balance > 0}
                      data-testid={`checkout-${booking.id}`}
                    >
                      <LogOut className="w-4 h-4 mr-2" />
                      Check Out
                    </Button>
                  </div>
                </div>
              </CardContent>
            </Card>
          ))}
        </TabsContent>

        <TabsContent value="inhouse" className="space-y-4">
          {inhouse.map((booking) => (
            <Card key={booking.id}>
              <CardContent className="pt-6">
                <div className="flex justify-between items-center">
                  <div>
                    <div className="font-bold text-lg">{booking.guest?.name}</div>
                    <div className="text-sm text-gray-600">Room {booking.room?.room_number} - {booking.room?.room_type}</div>
                    <div className="text-sm text-gray-500">
                      Check-in: {new Date(booking.check_in).toLocaleDateString()} |
                      {' '}Check-out: {new Date(booking.check_out).toLocaleDateString()}
                    </div>
                  </div>
                  <Button variant="outline" onClick={() => loadFolio(booking.id)}>
                    Manage Folio
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
