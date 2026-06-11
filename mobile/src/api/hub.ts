import { api } from './client';

// Mirrors backend/domains/pms/mobile_router/hub.py
// Person-centric aggregation for the common mobile shell (Task #327, Faz 0).
// These endpoints merge EXISTING data (notifications, alerts, tasks,
// approvals) — they introduce no new data or notification types.

export type FeedSource = 'notification' | 'alert';

export type FeedItem = {
  source: FeedSource;
  id: string;
  type: string;
  title: string;
  message: string;
  priority: string;
  read: boolean;
  action_url?: string | null;
  created_at: string;
};

export type FeedResponse = {
  items: FeedItem[];
  count: number;
  offset: number;
  limit: number;
  has_more: boolean;
  unread_count: number;
};

// GET /api/mobile/hub/feed
export async function getFeed(params?: {
  limit?: number;
  offset?: number;
  unread_only?: boolean;
}): Promise<FeedResponse> {
  return api.get<FeedResponse>('/api/mobile/hub/feed', {
    limit: params?.limit,
    offset: params?.offset,
    unread_only: params?.unread_only,
  });
}

// POST /api/mobile/hub/feed/mark-read
export async function markFeedRead(source: FeedSource, id: string): Promise<{ success: boolean }> {
  return api.post<{ success: boolean }>('/api/mobile/hub/feed/mark-read', { source, id });
}

export type MyTaskKind = 'housekeeping' | 'maintenance';

export type MyTask = {
  id: string;
  kind: MyTaskKind;
  title: string;
  room_number?: string | null;
  priority: string;
  status: string;
  notes?: string | null;
  created_at: string;
};

export type MyTasksResponse = {
  tasks: MyTask[];
  count: number;
  by_kind: { housekeeping: number; maintenance: number };
};

// GET /api/mobile/hub/my-tasks
export async function getMyTasks(): Promise<MyTasksResponse> {
  return api.get<MyTasksResponse>('/api/mobile/hub/my-tasks');
}

export type TodayDigest = {
  date: string;
  open_tasks: number;
  urgent_tasks: number;
  unread_feed: number;
  pending_approvals: number;
  tasks_preview: MyTask[];
};

// GET /api/mobile/hub/today
export async function getToday(): Promise<TodayDigest> {
  return api.get<TodayDigest>('/api/mobile/hub/today');
}

export type ApprovalItem = {
  id: string;
  kind: string;
  title: string;
  requested_by?: string | null;
  amount?: number | null;
  priority: string;
  created_at: string;
};

export type ApprovalCategory = {
  key: 'finance' | 'hr';
  label: string;
  items: ApprovalItem[];
  count: number;
};

export type ApprovalsResponse = {
  categories: ApprovalCategory[];
  total: number;
};

// GET /api/mobile/hub/approvals
export async function getApprovals(): Promise<ApprovalsResponse> {
  return api.get<ApprovalsResponse>('/api/mobile/hub/approvals');
}
