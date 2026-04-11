import React, { useEffect, useState } from 'react';
import { useNavigate } from 'react-router-dom';
import axios from 'axios';
import Layout from '../components/Layout';
import StaffAssignment from '../components/StaffAssignment';
import HousekeepingDetailedReports from '../components/HousekeepingDetailedReports';
import HousekeepingQualityPanel from '../components/HousekeepingQualityPanel';
import { Card, CardContent, CardHeader, CardTitle } from '../components/ui/card';
import { Button } from '../components/ui/button';
import { Bed, Users, ArrowLeft, Sparkles } from 'lucide-react';
import { Skeleton } from '../components/ui/skeleton';
import { useTranslation } from 'react-i18next';

const HousekeepingDashboard = ({ user, tenant, onLogout }) => {
  const { t } = useTranslation();
  const [hkDashboard, setHkDashboard] = useState(null);
  const [roomStatus, setRoomStatus] = useState(null);
  const [loading, setLoading] = useState(true);

  useEffect(() => {
    const loadHK = async () => {
      try {
        const [dashRes, statusRes] = await Promise.all([
          axios.get('/department/housekeeping/dashboard'),
          axios.get('/housekeeping/room-status')
        ]);
        setHkDashboard(dashRes.data || null);
        setRoomStatus(statusRes.data || null);
      } catch (err) {
        console.error('Failed to load housekeeping dashboard', err);
      } finally {
        setLoading(false);
      }
    };
    loadHK();
  }, []);

  const navigate = useNavigate();

  return (
    <Layout user={user} tenant={tenant} onLogout={onLogout} currentModule="housekeeping">
      <div className="p-6 space-y-6">
        {/* Header */}
        <div className="flex items-center justify-between">
          <div>
            <h1 className="text-3xl font-bold flex items-center gap-3">
              <Bed className="w-8 h-8 text-blue-600" />
              {t('hkDashboard.title')}
            </h1>
            <p className="text-gray-600 mt-1">
              {t('hkDashboard.subtitle')}
            </p>
          </div>
          <div className="flex items-center gap-3">
            <Button variant="outline" onClick={() => navigate('/features')}>
              <Sparkles className="w-4 h-4 mr-2" />
              {t('hkDashboard.moreFeatures')}
            </Button>
            <Button onClick={() => navigate('/')}>
              <ArrowLeft className="w-4 h-4 mr-2" />
              {t('nav.dashboard')}
            </Button>
          </div>
        </div>

        {/* Info Banner */}
        <Card className="bg-gradient-to-r from-blue-50 to-indigo-50 border-blue-200">
        {/* Detailed Reports Inline */}
        <Card>
          <CardHeader>
            <CardTitle>{t('hkDashboard.detailedReports')}</CardTitle>
          </CardHeader>
          <CardContent>
            <HousekeepingDetailedReports />
          </CardContent>
        </Card>


          <CardContent className="p-4">
            <div className="flex items-start space-x-3">
              <div className="bg-blue-100 p-2 rounded-full">
                <Users className="w-5 h-5 text-blue-600" />
              </div>
              <div>
                <h4 className="font-semibold text-gray-900 mb-1">🧹 {t('hkDashboard.hkManagement')}</h4>
                <p className="text-sm text-gray-600">
                  {t('hkDashboard.hkManagementDesc')}
                </p>
              </div>
            </div>
          </CardContent>
        </Card>

        {/* HK Summary Widgets */}
        <Card>
          <CardHeader>
            <CardTitle>{t('hkDashboard.todaySnapshot')}</CardTitle>
          </CardHeader>
          <CardContent>
            {loading ? (
              <div className="grid grid-cols-2 md:grid-cols-4 gap-4">
                <Skeleton className="h-20" />
                <Skeleton className="h-20" />
                <Skeleton className="h-20" />
                <Skeleton className="h-20" />
              </div>
            ) : (
              <div className="grid grid-cols-2 md:grid-cols-4 gap-4 text-sm">
                <div className="bg-blue-50 p-3 rounded">
                  <div className="text-xs text-gray-600">{t('hkDashboard.roomsTotal')}</div>
                  <div className="text-2xl font-bold text-blue-700">{roomStatus?.summary?.total_rooms ?? '-'}</div>
                </div>
                <div className="bg-green-50 p-3 rounded">
                  <div className="text-xs text-gray-600">{t('hkDashboard.vacantClean')}</div>
                  <div className="text-2xl font-bold text-green-700">{roomStatus?.summary?.vacant_clean ?? '-'}</div>
                </div>
                <div className="bg-yellow-50 p-3 rounded">
                  <div className="text-xs text-gray-600">{t('hkDashboard.vacantDirty')}</div>
                  <div className="text-2xl font-bold text-yellow-700">{roomStatus?.summary?.vacant_dirty ?? '-'}</div>
                </div>
                <div className="bg-red-50 p-3 rounded">
                  <div className="text-xs text-gray-600">{t('hkDashboard.outOfOrderService')}</div>
                  <div className="text-2xl font-bold text-red-700">{(roomStatus?.summary?.out_of_order || 0) + (roomStatus?.summary?.out_of_service || 0)}</div>
                </div>
              </div>
            )}
          </CardContent>
        </Card>

        {/* Quality Control */}
        {roomStatus?.rooms?.length ? (
          <HousekeepingQualityPanel rooms={roomStatus.rooms} />
        ) : null}

        {/* Staff Assignment Component */}
        <StaffAssignment />

        {/* Quick Actions */}
        <Card>
          <CardHeader>
            <CardTitle>{t('hkDashboard.quickActions')}</CardTitle>
          </CardHeader>
          <CardContent>
            <div className="grid grid-cols-2 md:grid-cols-4 gap-4">
              <Button
                variant="outline"
                className="h-20 flex flex-col items-center justify-center"
                onClick={() => navigate('/')}
              >
                <span className="text-2xl mb-2">🛏️</span>
                <span className="text-sm">{t('hkDashboard.roomStatus')}</span>
              </Button>
              <Button
                variant="outline"
                className="h-20 flex flex-col items-center justify-center"
                onClick={() => navigate('/')}
              >
                <span className="text-2xl mb-2">📋</span>
                <span className="text-sm">{t('hkDashboard.taskList')}</span>
              </Button>
              <Button
                variant="outline"
                className="h-20 flex flex-col items-center justify-center"
                onClick={() => navigate('/')}
              >
                <span className="text-2xl mb-2">📊</span>
                <span className="text-sm">{t('hkDashboard.reports')}</span>
              </Button>
              <Button
                variant="outline"
                className="h-20 flex flex-col items-center justify-center"
                onClick={() => navigate('/mobile')}
              >
                <span className="text-2xl mb-2">📱</span>
                <span className="text-sm">{t('hkDashboard.mobileApp')}</span>
              </Button>
            </div>
          </CardContent>
        </Card>
      </div>
    </Layout>
  );
};

export default HousekeepingDashboard;
