import Layout from '@/components/Layout';
import HousekeepingRoomGrid from '@/components/pms/HousekeepingRoomGrid';

const HousekeepingStatusPage = ({ user, tenant, onLogout }) => {
  return (
    <Layout user={user} tenant={tenant} onLogout={onLogout} currentModule="housekeeping">
      <HousekeepingRoomGrid embedded={false} />
    </Layout>
  );
};

export default HousekeepingStatusPage;
