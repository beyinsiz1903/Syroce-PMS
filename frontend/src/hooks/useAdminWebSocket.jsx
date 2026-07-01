import { useNativeWebSocket } from './useNativeWebSocket';

export function useAdminWebSocket(tenantId) {
  const path = tenantId
    ? `/api/channel-manager/v2/ws/admin-updates?tenant_id=${tenantId}`
    : null;

  return useNativeWebSocket(path, { enabled: !!tenantId });
}
