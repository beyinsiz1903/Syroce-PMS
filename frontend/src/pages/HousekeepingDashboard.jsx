import { useEffect, useState, lazy, Suspense } from 'react';
import { useNavigate } from 'react-router-dom';
import axios from 'axios';

// Ağır alt-componentler lazy yüklenir — sayfa header + KPI kartları
// API yanıtını beklemeden render olur; alt-paneller görünür hale geldikçe
// kendi fetch'lerini başlatır. Eski sürümde 3 alt-component eager mount
// olup ek API çağrılarını ilk paint'ten önce tetikliyordu.
const StaffAssignment = lazy(() => import('../components/StaffAssignment'));
const HousekeepingDetailedReports = lazy(() => import('../components/HousekeepingDetailedReports'));
const HousekeepingQualityPanel = lazy(() => import('../components/HousekeepingQualityPanel'));
import { Card, CardContent, CardHeader, CardTitle } from '../components/ui/card';
import { Button } from '../components/ui/button';
import { PageHeader } from '@/components/ui/page-header';
import { KpiCard } from '@/components/ui/kpi-card';
import { Bed, ArrowLeft, Smartphone, ClipboardList, Wrench, BedDouble, Sparkles, Brush, AlertOctagon } from 'lucide-react';
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
    <>
      <div className="p-6 space-y-6" data-testid="page-housekeeping">
        {/* Header */}
        <PageHeader
          icon={Bed}
          title={t('hkDashboard.title')}
          subtitle={t('hkDashboard.subtitle')}
          actions={
            <Button onClick={() => navigate('/')} variant="outline" size="sm">
              <ArrowLeft className="w-4 h-4 mr-1.5" />
              {t('nav.dashboard')}
            </Button>
          }
        />

        {/* Today Snapshot — KPI Cards */}
        {loading ? (
          <div className="grid grid-cols-2 md:grid-cols-4 gap-4">
            <Skeleton className="h-20" />
            <Skeleton className="h-20" />
            <Skeleton className="h-20" />
            <Skeleton className="h-20" />
          </div>
        ) : (
          <div className="grid grid-cols-2 md:grid-cols-4 gap-4">
            <KpiCard icon={BedDouble} intent="info" label={t('hkDashboard.roomsTotal')} value={totalRooms} />
            <KpiCard icon={Sparkles} intent="success" label={t('hkDashboard.vacantClean')} value={vacantClean} />
            <KpiCard icon={Brush} intent="warning" label={t('hkDashboard.vacantDirty')} value={vacantDirty} />
            <KpiCard icon={AlertOctagon} intent="danger" label={t('hkDashboard.outOfOrderService')} value={oooCount} />
          </div>
        )}

        {/* Detailed Reports */}
        <Card>
          <CardHeader>
            <CardTitle>{t('hkDashboard.detailedReports')}</CardTitle>
          </CardHeader>
          <CardContent>
            <Suspense fallback={<Skeleton className="h-32" />}>
              <HousekeepingDetailedReports />
            </Suspense>
          </CardContent>
        </Card>

        {/* Quality Control — yalnızca oda verisi varsa */}
        {roomStatus?.rooms?.length ? (
          <Suspense fallback={<Skeleton className="h-32" />}>
            <HousekeepingQualityPanel rooms={roomStatus.rooms} />
          </Suspense>
        ) : null}

        {/* Staff Assignment */}
        <Suspense fallback={<Skeleton className="h-32" />}>
          <StaffAssignment />
        </Suspense>

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
                <Wrench className="w-5 h-5 text-amber-600" />
                <span className="text-sm">{t('hkDashboard.taskList')}</span>
              </Button>
              <Button
                variant="outline"
                className="h-20 flex flex-col items-center justify-center gap-1"
                onClick={() => navigate('/mobile/housekeeping')}
                data-testid="hk-quick-mobile"
              >
                <Smartphone className="w-5 h-5 text-indigo-600" />
                <span className="text-sm">{t('hkDashboard.mobileApp')}</span>
              </Button>
            </div>
          </CardContent>
        </Card>
      </div>
    </>
  );
};

export default HousekeepingDashboard;
