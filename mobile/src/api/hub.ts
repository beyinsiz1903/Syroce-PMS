import { api, apiRequest } from './client';

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

// The per-item kind selects which existing backend approve/reject endpoint
// the action routes to (see actOnApproval). It is NOT the category key.
export type ApprovalKind =
  | 'approval'
  | 'approval_request'
  | 'leave'
  | 'shift_swap'
  | 'pr_status';

export type ApprovalItem = {
  id: string;
  kind: ApprovalKind | string;
  title: string;
  requested_by?: string | null;
  amount?: number | null;
  priority: string;
  status?: string | null;
  target_consent_status?: string | null;
  created_at: string;
};

export type ApprovalCategory = {
  key: 'finance' | 'hr' | 'procurement';
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

export type ApprovalAction = 'approve' | 'reject';

// Approve or reject a single approval item by delegating to the EXISTING,
// already RBAC-guarded backend endpoints — no new endpoints, no RBAC change.
// Routing depends on the item kind because each source collection exposes a
// different endpoint/method/body shape:
//   - approval          -> PUT  /api/approvals/{id}/approve|reject  (PMS)
//   - approval_request  -> POST /api/approvals/{id}/approve|reject  (analytics)
//   - leave             -> POST /api/hr/leave-request/{id}/decision (2-stage)
//   - shift_swap        -> POST /api/hr/shift-swap-request/{id}/decision
//   - pr_status         -> POST /api/procurement/purchase-requests/{id}/status
export async function actOnApproval(
  item: ApprovalItem,
  action: ApprovalAction,
  reason?: string,
): Promise<unknown> {
  const id = item.id;
  const note = reason ?? '';
  switch (item.kind) {
    case 'approval':
      if (action === 'approve') {
        return api.put(`/api/approvals/${id}/approve`, { notes: note });
      }
      return api.put(`/api/approvals/${id}/reject`, {
        rejection_reason: note,
        notes: note,
      });
    case 'approval_request':
      if (action === 'approve') {
        return api.post(`/api/approvals/${id}/approve`, { note });
      }
      return api.post(`/api/approvals/${id}/reject`, { reason: note });
    case 'leave': {
      // Honour the backend's 2-stage chain: a pending request can only advance
      // to dept_approved; a dept_approved one to the final approved state.
      const decision =
        action === 'reject'
          ? 'reject'
          : item.status === 'dept_approved'
            ? 'approve'
            : 'dept_approve';
      return api.post(`/api/hr/leave-request/${id}/decision`, {
        decision,
        note: note || null,
      });
    }
    case 'shift_swap':
      return api.post(`/api/hr/shift-swap-request/${id}/decision`, {
        action,
        note: note || null,
      });
    case 'pr_status':
      // The PR-status endpoint maps a submitted request to approved|rejected.
      // A rejection reason is mandatory (backend requires reason >= 5 chars for
      // reject/cancel); approvals send no reason. Backend still enforces
      // require_op("manage_sales") + require_procurement on the decision.
      return api.post(`/api/procurement/purchase-requests/${id}/status`, {
        status: action === 'approve' ? 'approved' : 'rejected',
        ...(action === 'reject' ? { reason: note } : {}),
      });
    default:
      throw new Error(`Bilinmeyen onay türü: ${item.kind}`);
  }
}

// ── Staff-to-staff messaging (Task #333) ────────────────────────────────────
// Reuses the EXISTING internal-messaging backend (`/api/messaging/internal/*`)
// — no new collection or notification type is introduced. Every endpoint is
// tenant-scoped server-side via the authenticated user.

export type Conversation = {
  user_id: string;
  user_name: string;
  user_role?: string;
  last_message: string;
  last_message_at?: string | null;
  last_from_me: boolean;
  last_priority: string;
  last_deleted: boolean;
  unread_count: number;
  time_ago: string;
};

export type ConversationsResponse = {
  conversations: Conversation[];
  total_count: number;
};

// GET /api/messaging/internal/conversations
export async function getConversations(): Promise<ConversationsResponse> {
  return api.get<ConversationsResponse>('/api/messaging/internal/conversations');
}

export type ThreadMessage = {
  id: string;
  from_user_id: string;
  from_user_name?: string;
  to_user_id?: string | null;
  to_user_name?: string | null;
  message: string;
  priority: string;
  created_at?: string;
  time_ago: string;
  is_from_me: boolean;
  read: boolean;
  deleted: boolean;
  edited: boolean;
};

export type ThreadResponse = {
  user_id: string;
  message_count: number;
  messages: ThreadMessage[];
};

// GET /api/messaging/internal/conversation/{user_id}
export async function getConversationThread(userId: string): Promise<ThreadResponse> {
  return api.get<ThreadResponse>(
    `/api/messaging/internal/conversation/${encodeURIComponent(userId)}`,
  );
}

// PUT /api/messaging/internal/conversation/{user_id}/mark-read
export async function markConversationRead(
  userId: string,
): Promise<{ success: boolean; updated_count?: number }> {
  return api.put<{ success: boolean; updated_count?: number }>(
    `/api/messaging/internal/conversation/${encodeURIComponent(userId)}/mark-read`,
    {},
  );
}

// POST /api/messaging/internal/send — the backend declares these as QUERY
// params (no request-body model), so they must be sent on the query string.
export async function sendInternalMessage(
  toUserId: string,
  message: string,
): Promise<unknown> {
  return apiRequest('/api/messaging/internal/send', {
    method: 'POST',
    query: { message, to_user_id: toUserId, priority: 'normal', message_type: 'text' },
  });
}

// ── Unified cross-entity search (Task #333) ─────────────────────────────────

export type GuestHit = { id: string; name: string; vip_status: boolean };
export type ReservationHit = {
  id: string;
  booking_number: string;
  guest_name: string;
  room_number?: string | null;
  status: string;
  check_in?: string | null;
  check_out?: string | null;
};
export type RoomHit = { id: string; room_number: string; room_type: string; status: string };

export type SearchResponse = {
  query: string;
  guests: GuestHit[];
  reservations: ReservationHit[];
  rooms: RoomHit[];
  total: number;
};

// GET /api/mobile/hub/search
export async function unifiedSearch(q: string): Promise<SearchResponse> {
  return api.get<SearchResponse>('/api/mobile/hub/search', { q });
}
