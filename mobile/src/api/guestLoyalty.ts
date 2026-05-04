import { api } from './client';

export type LoyaltyTransaction = {
  id?: string;
  type?: string;
  points?: number;
  balance_after?: number;
  source?: string;
  reference_id?: string;
  created_at?: string;
};

export type LoyaltyProgram = {
  id: string;
  hotel_id?: string;
  hotel_name?: string;
  tier?: string;
  points: number;
  next_tier?: string | null;
  points_to_next_tier?: number;
  tier_benefits?: string[];
  recent_transactions?: LoyaltyTransaction[];
};

export type UpcomingReward = {
  name: string;
  points_required: number;
  points_remaining: number;
};

export type GuestLoyaltyResponse = {
  total_points: number;
  global_tier: string;
  loyalty_programs: LoyaltyProgram[];
  upcoming_rewards: UpcomingReward[];
};

export async function getGuestLoyalty(): Promise<GuestLoyaltyResponse> {
  try {
    return await api.get<GuestLoyaltyResponse>('/api/guest/loyalty');
  } catch {
    return {
      total_points: 0,
      global_tier: 'bronze',
      loyalty_programs: [],
      upcoming_rewards: [],
    };
  }
}
