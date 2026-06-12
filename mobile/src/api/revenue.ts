import { api } from './client';

// Revenue Management API client — read-focused mirror of
// backend/domains/revenue/rms_router/pricing_strategy.py (mounted under /api).
// pricing-strategy / price-adjustments / pricing-insights only require auth
// server-side; mutations (auto-pricing, apply, update strategy) stay gated by
// require_op("manage_rates") and view_revenue on the backend and are NOT
// exposed here. The (departments) revenue entitlement decides whether we show
// the screen.

export type PricingStrategy = {
  current_rate?: number;
  recommended_rate?: number;
  auto_pricing_enabled?: boolean;
  market_position?: string;
  comp_avg_rate?: number;
  pending_recommendations?: number;
};

export type PriceAdjustment = {
  id?: string;
  date?: string;
  reason?: string;
  old_rate?: number;
  new_rate?: number;
  room_type?: string;
  applied_at?: string;
};

export type PricingInsight = {
  room_type?: string;
  current_rate?: number;
  suggested_rate?: number;
  price_change?: number;
  price_change_pct?: number;
  occupancy?: number;
  confidence?: number;
  confidence_level?: string;
  strategy?: string;
  reasoning?: string;
};

export type PricingInsights = {
  date?: string;
  message?: string;
  insights: PricingInsight[];
  summary?: {
    total_recommendations?: number;
    avg_confidence?: number;
    total_rate_adjustment?: number;
    high_confidence_count?: number;
  };
};

// GET /api/rms/pricing-strategy → computed metrics object
export async function getPricingStrategy(): Promise<PricingStrategy> {
  return api.get<PricingStrategy>('/api/rms/pricing-strategy');
}

// GET /api/rms/price-adjustments?limit= → { adjustments, count }
export async function listPriceAdjustments(limit = 20): Promise<PriceAdjustment[]> {
  const res = await api.get<{ adjustments?: PriceAdjustment[] }>(
    '/api/rms/price-adjustments',
    { limit },
  );
  return res?.adjustments ?? [];
}

// GET /api/rms/pricing-insights?date= → { date, insights, summary }
export async function getPricingInsights(date?: string): Promise<PricingInsights> {
  const res = await api.get<PricingInsights>('/api/rms/pricing-insights', { date });
  return { ...res, insights: res?.insights ?? [] };
}

// Revenue engine dashboard — ADR / RevPAR / occupancy cockpit metrics.
// backend/routers/revenue_management.py GET /api/revenue-engine/dashboard only
// requires auth (computes real 30-day metrics from folio_charges + bookings).
export type RevenueOpportunity = {
  date?: string;
  type?: string;
  message?: string;
  potential_revenue?: number;
};

export type RevenueDashboard = {
  total_rooms?: number;
  today_occupancy_pct?: number;
  today_booked?: number;
  period_30d?: {
    total_revenue?: number;
    room_revenue?: number;
    room_nights_sold?: number;
    adr?: number;
    revpar?: number;
  };
  opportunities: RevenueOpportunity[];
};

// GET /api/revenue-engine/dashboard → comprehensive ADR/RevPAR/occupancy snapshot
export async function getRevenueDashboard(): Promise<RevenueDashboard> {
  const res = await api.get<RevenueDashboard>('/api/revenue-engine/dashboard');
  return { ...res, opportunities: res?.opportunities ?? [] };
}

// Forward-looking occupancy forecast. High occupancy days carry the highest
// displacement risk (accepting discounted/group business crowds out higher
// rated demand), so `demand_level` doubles as the displacement-risk signal.
export type ForecastDay = {
  date?: string;
  total_rooms?: number;
  booked?: number;
  blocked?: number;
  available?: number;
  occupancy_pct?: number;
  demand_level?: string;
};

export type OccupancyForecast = {
  total_rooms?: number;
  forecast: ForecastDay[];
};

// GET /api/revenue-engine/occupancy-forecast?days= → { total_rooms, forecast }
export async function getOccupancyForecast(days = 7): Promise<OccupancyForecast> {
  const res = await api.get<OccupancyForecast>(
    '/api/revenue-engine/occupancy-forecast',
    { days },
  );
  return { ...res, forecast: res?.forecast ?? [] };
}
