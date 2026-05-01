import { useEffect, useState } from 'react';
import { useNavigate } from 'react-router-dom';
import axios from 'axios';
import Layout from '../components/Layout';
import StaffAssignment from '../components/StaffAssignment';
import HousekeepingDetailedReports from '../components/HousekeepingDetailedReports';
import HousekeepingQualityPanel from '../components/HousekeepingQualityPanel';
import { Card, CardContent, CardHeader, CardTitle } from '../components/ui/card';
import { Button } from '../components/ui/button';
import { Bed, ArrowLeft, Smartphone, ClipboardList, Wrench } from 'lucide-react';
import { Skeleton } from '../components/ui/skeleton';
import { useTranslation } from 'react-i18next';

const HousekeepingDashboard = ({ user, tenant, onLogout }) => {
  const { t } = useTranslation();
  const navigate = useNavigate();
  const [roomStatus, setRoomStatus] = useState(null);
  const [loading, setLoading] = useState(true);

  useEffect(() => {
    let cancelled = false;
    const loadHK = async () => {
      try {
        const statusRes = await axios.get('/housekeeping/room-status');
        if (!cancelled) setRoomStatus(statusRes.data || null);
      } catch (err) {
        console.error('Failed to load housekeeping room status', err);
      } finally {
        if (!cancelled) setLoading(false);
      }
    };
    loadHK();
    return () => { cancelled = true; };
  }, []);

  const totalRooms = roomStatus?.total_rooms ?? roomStatus?.summary?.total_rooms ?? '-';
  const vacantClean = roomStatus?.status_counts?.available ?? roomStatus?.summary?.vacant_clean ?? '-';
  const vacantDirty = roomStatus?.status_counts?.dirty ?? roomStatus?.summary?.vacant_dirty ?? '-';
  const oooCount = (roomStatus?.status_counts?.out_of_order ?? roomStatus?.summary?.out_of_order ?? 0)
    + (roomStatus?.status_counts?.maintenance ?? roomStatus?.summary?.out_of_service ?? 0);

  return (
    <Layout user={user} tenant={tenant} onLogout={onLogout} currentModule="housekeeping">
      <div className="p-6 space-y-6" data-testid="page-housekeeping">
        {/* Header */}
        <div className="flex items-center justify-between flex-wrap gap-3">
          <div>
            <h1 className="text-3xl font-bold flex items-center gap-3">
              <Bed className="w-8 h-8 text-blue-600" />
              {t('hkDashboard.title')}
            </h1>
            <p className="text-gray-600 mt-1">{t('hkDashboard.subtitle')}</p>
          </div>
          <Button onClick={() => navigate('/')} variant="outline">
            <ArrowLeft className="w-4 h-4 mr-2" />
            {t('nav.dashboard')}
          </Button>
        </div>

        {/* Today Snapshot — KPI Cards */}
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
                  <div className="text-2xl font-bold text-blue-700">{totalRooms}</div>
                </div>
                <div className="bg-green-50 p-3 rounded">
                  <div className="text-xs text-gray-600">{t('hkDashboard.vacantClean')}</div>
                  <div className="text-2xl font-bold text-green-700">{vacantClean}</div>
                </div>
                <div className="bg-yellow-50 p-3 rounded">
                  <div className="text-xs text-gray-600">{t('hkDashboard.vacantDirty')}</div>
                  <div className="text-2xl font-bold text-yellow-700">{vacantDirty}</div>
                </div>
                <div className="bg-red-50 p-3 rounded">
                  <div className="text-xs text-gray-600">{t('hkDashboard.outOfOrderService')}</div>
                  <div className="text-2xl font-bold text-red-700">{oooCount}</div>
                </div>
              </div>
            )}
          </CardContent>
        </Card>

        {/* Detailed Reports */}
        <Card>
          <CardHeader>
            <CardTitle>{t('hkDashboard.detailedReports')}</CardTitle>
          </CardHeader>
          <CardContent>
            <HousekeepingDetailedReports />
          </CardContent>
        </Card>

        {/* Quality Control — yalnızca oda verisi varsa */}
        {roomStatus?.rooms?.length ? (
          <HousekeepingQualityPanel rooms={roomStatus.rooms} />
        ) : null}

        {/* Staff Assignment */}
        <StaffAssignment />

        {/* Quick Actions — gerçek hedeflere yönlendiriyor */}
        <Card>
          <CardHeader>
            <CardTitle>{t('hkDashboard.quickActions')}</CardTitle>
          </CardHeader>
          <CardContent>
            <div className="grid grid-cols-2 md:grid-cols-3 gap-4">
              <Button
                variant="outline"
                className="h-20 flex flex-col items-center justify-center gap-1"
                onClick={() => navigate('/housekeeping-status')}
                data-testid="hk-quick-room-status"
              >
                <ClipboardList className="w-5 h-5 text-blue-600" />
                <span className="text-sm">{t('hkDashboard.roomStatus')}</span>
              </Button>
              <Button
                variant="outline"
                className="h-20 flex flex-col items-center justify-center gap-1"
                onClick={() => navigate('/maintenance/work-orders')}
                data-testid="hk-quick-maintenance"
              >
                <Wrench className="w-5 h-5 text-orange-600" />
                <span className="text-sm">{t('hkDashboard.taskList')}</span>
              </Button>
              <Button
                variant="outline"
                className="h-20 flex flex-col items-center justify-center gap-1"
                onClick={() => navigate('/mobile/housekeeping')}
                data-testid="hk-quick-mobile"
              >
                <Smartphone className="w-5 h-5 text-purple-600" />
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
