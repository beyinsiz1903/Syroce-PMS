import React, { useState, useEffect } from 'react';
import { Card, CardHeader, CardTitle, CardContent } from './ui/card';
import { Button } from './ui/button';
import { Badge } from './ui/badge';
import { Tabs, TabsContent, TabsList, TabsTrigger } from './ui/tabs';
import { Moon, DoorClosed, AlertTriangle, Award, Clock, Star } from 'lucide-react';
import { useTranslation } from 'react-i18next';

const HousekeepingDetailedReports = () => {
  const { t } = useTranslation();
  const [roomStatus, setRoomStatus] = useState(null);
  const [staffPerformance, setStaffPerformance] = useState([]);
  const [loading, setLoading] = useState(true);

  useEffect(() => {
    fetchRoomStatusReport();
    fetchStaffPerformance();
  }, []);

  const fetchRoomStatusReport = async () => {
    try {
      const token = localStorage.getItem('token');
      const response = await fetch(
        `/api/housekeeping/room-status-report`,
        { headers: { 'Authorization': `Bearer ${token}` } }
      );
      const data = await response.json();
      setRoomStatus(data);
    } catch (error) {
      console.error('Error:', error);
    } finally {
      setLoading(false);
    }
  };

  const fetchStaffPerformance = async () => {
    try {
      const token = localStorage.getItem('token');
      const response = await fetch(
        `/api/housekeeping/staff-performance-detailed`,
        { headers: { 'Authorization': `Bearer ${token}` } }
      );
      const data = await response.json();
      setStaffPerformance(data.staff_performance || []);
    } catch (error) {
      console.error('Error:', error);
    }
  };

  return (
    <div className="p-6 space-y-6">
      <div>
        <h1 className="text-3xl font-bold">{t('hkReports.title')}</h1>
        <p className="text-gray-600">{t('hkReports.subtitle')}</p>
      </div>

      <Tabs defaultValue="status" className="w-full">
        <TabsList className="grid w-full grid-cols-2">
          <TabsTrigger value="status">
            <DoorClosed className="w-4 h-4 mr-2" />
            {t('hkReports.roomStatus')}
          </TabsTrigger>
          <TabsTrigger value="performance">
            <Award className="w-4 h-4 mr-2" />
            {t('hkReports.staffPerformance')}
          </TabsTrigger>
        </TabsList>

        {/* Room Status Tab */}
        <TabsContent value="status">
          {loading ? (
            <div className="text-center py-8">{t('common.loading')}</div>
          ) : (
            <div className="space-y-6">
              {/* Summary */}
              <Card>
                <CardHeader>
                  <CardTitle>{t('hkReports.roomStatusSummary')}</CardTitle>
                </CardHeader>
                <CardContent>
                  <div className="grid grid-cols-2 md:grid-cols-6 gap-4">
                    <div className="bg-blue-50 p-4 rounded-lg">
                      <div className="text-sm text-gray-600">{t('hkReports.totalRooms')}</div>
                      <div className="text-2xl font-bold text-blue-600">{roomStatus?.summary?.total_rooms}</div>
                    </div>
                    <div className="bg-green-50 p-4 rounded-lg">
                      <div className="text-sm text-gray-600">{t('hkReports.occupied')}</div>
                      <div className="text-2xl font-bold text-green-600">{roomStatus?.summary?.occupied}</div>
                    </div>
                    <div className="bg-indigo-50 p-4 rounded-lg">
                      <div className="text-sm text-gray-600">{t('hkReports.vacantClean')}</div>
                      <div className="text-2xl font-bold text-indigo-600">{roomStatus?.summary?.vacant_clean}</div>
                    </div>
                    <div className="bg-yellow-50 p-4 rounded-lg">
                      <div className="text-sm text-gray-600">{t('hkReports.vacantDirty')}</div>
                      <div className="text-2xl font-bold text-yellow-600">{roomStatus?.summary?.vacant_dirty}</div>
                    </div>
                    <div className="bg-red-50 p-4 rounded-lg">
                      <div className="text-sm text-gray-600">{t('hkReports.outOfOrder')}</div>
                      <div className="text-2xl font-bold text-red-600">{roomStatus?.summary?.out_of_order}</div>
                    </div>
                    <div className="bg-gray-50 p-4 rounded-lg">
                      <div className="text-sm text-gray-600">{t('hkReports.outOfService')}</div>
                      <div className="text-2xl font-bold text-gray-600">{roomStatus?.summary?.out_of_service}</div>
                    </div>
                  </div>
                </CardContent>
              </Card>

              {/* DND Rooms */}
              <Card>
                <CardHeader>
                  <CardTitle className="flex items-center gap-2">
                    <Moon className="w-5 h-5" />
                    Do Not Disturb (DND) {t('hkReports.rooms')}
                  </CardTitle>
                </CardHeader>
                <CardContent>
                  {roomStatus?.dnd_rooms?.length === 0 ? (
                    <div className="text-center text-gray-500 py-4">{t('hkReports.noDndRooms')}</div>
                  ) : (
                    <table className="w-full">
                      <thead>
                        <tr className="border-b">
                          <th className="text-left p-3">{t('hkReports.room')}</th>
                          <th className="text-left p-3">{t('hkReports.guest')}</th>
                          <th className="text-left p-3">{t('hkReports.dndSince')}</th>
                          <th className="text-left p-3">{t('hkReports.duration')}</th>
                        </tr>
                      </thead>
                      <tbody>
                        {roomStatus?.dnd_rooms?.map((room, idx) => (
                          <tr key={idx} className="border-b hover:bg-gray-50">
                            <td className="p-3 font-bold">{room.room}</td>
                            <td className="p-3">{room.guest}</td>
                            <td className="p-3">{room.dnd_since}</td>
                            <td className="p-3">
                              <Badge variant="outline">{room.duration_hours} {t('hkReports.hours')}</Badge>
                            </td>
                          </tr>
                        ))}
                      </tbody>
                    </table>
                  )}
                </CardContent>
              </Card>

              {/* Sleep Out */}
              <Card>
                <CardHeader>
                  <CardTitle>Sleep Out (SO)</CardTitle>
                </CardHeader>
                <CardContent>
                  {roomStatus?.sleep_out?.length === 0 ? (
                    <div className="text-center text-gray-500 py-4">{t('hkReports.noSleepOutRooms')}</div>
                  ) : (
                    <table className="w-full">
                      <thead>
                        <tr className="border-b">
                          <th className="text-left p-3">{t('hkReports.room')}</th>
                          <th className="text-left p-3">{t('hkReports.guest')}</th>
                          <th className="text-left p-3">{t('hkReports.lastActivity')}</th>
                          <th className="text-left p-3">{t('hkReports.status')}</th>
                        </tr>
                      </thead>
                      <tbody>
                        {roomStatus?.sleep_out?.map((room, idx) => (
                          <tr key={idx} className="border-b hover:bg-gray-50">
                            <td className="p-3 font-bold">{room.room}</td>
                            <td className="p-3">{room.guest}</td>
                            <td className="p-3">{room.last_activity}</td>
                            <td className="p-3">
                              <Badge className="bg-yellow-500">{room.status}</Badge>
                            </td>
                          </tr>
                        ))}
                      </tbody>
                    </table>
                  )}
                </CardContent>
              </Card>

              {/* Out of Order */}
              <Card>
                <CardHeader>
                  <CardTitle className="flex items-center gap-2">
                    <AlertTriangle className="w-5 h-5 text-red-600" />
                    Out of Order (OOO)
                  </CardTitle>
                </CardHeader>
                <CardContent>
                  {roomStatus?.out_of_order?.length === 0 ? (
                    <div className="text-center text-gray-500 py-4">{t('hkReports.noOooRooms')}</div>
                  ) : (
                    <table className="w-full">
                      <thead>
                        <tr className="border-b">
                          <th className="text-left p-3">{t('hkReports.room')}</th>
                          <th className="text-left p-3">{t('hkReports.reason')}</th>
                          <th className="text-left p-3">{t('hkReports.since')}</th>
                          <th className="text-left p-3">{t('hkReports.expectedFix')}</th>
                        </tr>
                      </thead>
                      <tbody>
                        {roomStatus?.out_of_order?.map((room, idx) => (
                          <tr key={idx} className="border-b hover:bg-gray-50">
                            <td className="p-3 font-bold">{room.room}</td>
                            <td className="p-3">{room.reason}</td>
                            <td className="p-3">{room.since}</td>
                            <td className="p-3">{room.expected_fix}</td>
                          </tr>
                        ))}
                      </tbody>
                    </table>
                  )}
                </CardContent>
              </Card>
            </div>
          )}
        </TabsContent>

        {/* Staff Performance Tab */}
        <TabsContent value="performance">
          <div className="space-y-4">
            {staffPerformance.map((staff, idx) => (
              <Card key={idx} className="border-l-4 border-l-blue-500">
                <CardContent className="p-6">
                  <div className="space-y-4">
                    <div className="flex items-center justify-between">
                      <h3 className="text-xl font-bold flex items-center gap-2">
                        <Award className="w-6 h-6 text-blue-600" />
                        {staff.staff_name}
                      </h3>
                      <Badge className="bg-green-500">
                        {staff.monthly_stats?.efficiency_rating || 'N/A'}
                      </Badge>
                    </div>

                    {/* Daily Stats */}
                    {staff.daily_stats && (
                    <div>
                      <h4 className="font-semibold mb-2">{t('hkReports.todayPerformance')}</h4>
                      <div className="grid grid-cols-2 md:grid-cols-5 gap-3">
                        <div className="bg-blue-50 p-3 rounded">
                          <div className="text-xs text-gray-600">{t('hkReports.roomsCleaned')}</div>
                          <div className="text-2xl font-bold text-blue-600">{staff.daily_stats?.rooms_cleaned || 0}</div>
                        </div>
                        <div className="bg-indigo-50 p-3 rounded">
                          <div className="text-xs text-gray-600">{t('hkReports.avgTime')}</div>
                          <div className="text-2xl font-bold text-indigo-600">{staff.daily_stats?.avg_time_per_room || 0}m</div>
                        </div>
                        <div className="bg-green-50 p-3 rounded">
                          <div className="text-xs text-gray-600">{t('hkReports.passed')}</div>
                          <div className="text-2xl font-bold text-green-600">{staff.daily_stats?.inspections_passed || 0}</div>
                        </div>
                        <div className="bg-red-50 p-3 rounded">
                          <div className="text-xs text-gray-600">{t('hkReports.failed')}</div>
                          <div className="text-2xl font-bold text-red-600">{staff.daily_stats?.inspections_failed || 0}</div>
                        </div>
                        <div className="bg-yellow-50 p-3 rounded">
                          <div className="text-xs text-gray-600">{t('hkReports.qualityScore')}</div>
                          <div className="text-2xl font-bold text-yellow-600">{staff.daily_stats?.quality_score || 0}%</div>
                        </div>
                      </div>
                    </div>
                    )}

                    {/* Monthly Stats */}
                    {staff.monthly_stats && (
                    <div>
                      <h4 className="font-semibold mb-2">{t('hkReports.monthlyPerformance')}</h4>
                      <div className="grid grid-cols-2 md:grid-cols-3 gap-3">
                        <div>
                          <div className="text-sm text-gray-600">{t('hkReports.totalRooms')}</div>
                          <div className="font-semibold">{staff.monthly_stats?.total_rooms || 0}</div>
                        </div>
                        <div>
                          <div className="text-sm text-gray-600">{t('hkReports.avgDailyRooms')}</div>
                          <div className="font-semibold">{staff.monthly_stats?.avg_daily_rooms || 0}</div>
                        </div>
                        <div>
                          <div className="text-sm text-gray-600">{t('hkReports.attendance')}</div>
                          <div className="font-semibold">{staff.monthly_stats?.attendance_rate || 0}%</div>
                        </div>
                      </div>
                    </div>
                    )}

                    {/* Certifications */}
                    <div>
                      <h4 className="font-semibold mb-2">{t('hkReports.certifications')}</h4>
                      <div className="flex gap-2 flex-wrap">
                        {staff.certifications?.map((cert, i) => (
                          <Badge key={i} variant="outline" className="bg-blue-50">
                            {cert}
                          </Badge>
                        ))}
                      </div>
                    </div>

                    {/* Recent Feedback */}
                    {staff.recent_feedback && staff.recent_feedback.length > 0 && (
                      <div>
                        <h4 className="font-semibold mb-2">{t('hkReports.recentFeedback')}</h4>
                        <div className="space-y-2">
                          {staff.recent_feedback.map((feedback, i) => (
                            <div key={i} className="bg-gray-50 p-3 rounded">
                              <div className="flex items-center justify-between">
                                <div className="flex items-center gap-2">
                                  <div className="flex">
                                    {[...Array(5)].map((_, j) => (
                                      <Star key={j} className={`w-3.5 h-3.5 ${j < feedback.rating ? 'text-yellow-400 fill-yellow-400' : 'text-gray-300'}`} />
                                    ))}
                                  </div>
                                  <span className="text-sm text-gray-600">{feedback.date}</span>
                                </div>
                              </div>
                              <p className="text-sm mt-1">{feedback.comment}</p>
                            </div>
                          ))}
                        </div>
                      </div>
                    )}
                  </div>
                </CardContent>
              </Card>
            ))}
          </div>
        </TabsContent>
      </Tabs>
    </div>
  );
};

export default HousekeepingDetailedReports;
