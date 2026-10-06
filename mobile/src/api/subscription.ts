import { api } from './client';

export type CurrentSubscription = {
  status?: string;
  tier?: string;
  modules?: Record<string, boolean>;
};

// The same tenant entitlement snapshot used by the web PMS. Mobile uses it
// only to hide add-on entry points that would otherwise lead to a dead
// "planiniza dahil degil" page; the backend remains the authority.
export async function getCurrentSubscription(): Promise<CurrentSubscription> {
  return api.get<CurrentSubscription>('/api/subscription/current');
}
