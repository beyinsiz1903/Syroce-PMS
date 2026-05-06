
import HousekeepingRoomGrid from '@/components/pms/HousekeepingRoomGrid';

const HousekeepingStatusPage = ({ user, tenant, onLogout }) => {
  return (
    <>
      <HousekeepingRoomGrid embedded={false} />
    </>
  );
};

export default HousekeepingStatusPage;
