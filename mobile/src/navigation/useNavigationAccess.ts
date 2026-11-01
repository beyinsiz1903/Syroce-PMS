import { useQuery } from '@tanstack/react-query';
import { getCurrentSubscription } from '../api/subscription';
import { useAuthStore } from '../state/authStore';
import { hubModuleState } from '../utils/departmentScreens';
import { mobileTargetAllowed, paidDepartmentForSegments } from './routeAccess';

/** Menus and cold links share the same confirmed subscription vocabulary. */
export function useNavigationAccess() {
  const user = useAuthStore((s) => s.user);
  const subscription = useQuery({
    queryKey: ['current-subscription', user?.tenant_id || user?.hotel_id],
    queryFn: getCurrentSubscription, enabled: !!user && user.role !== 'guest' && user.role !== 'guest_app',
    staleTime: 5 * 60 * 1000, retry: false,
  });
  return (target: unknown) => {
    if (!mobileTargetAllowed(user, target) || typeof target !== 'string') return false;
    const tile = paidDepartmentForSegments(target.split('/').filter(Boolean));
    return !tile || (!subscription.isError && hubModuleState(tile, subscription.data) === 'enabled');
  };
}
