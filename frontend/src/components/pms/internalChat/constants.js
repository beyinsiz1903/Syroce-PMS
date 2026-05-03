// InternalChatTab constants — extracted in R4 split.

export const DEPARTMENTS = [
  { value: 'Reception', label: 'Ön Büro' },
  { value: 'Housekeeping', label: 'Kat Hizmetleri' },
  { value: 'Maintenance', label: 'Teknik Servis' },
  { value: 'Finance', label: 'Muhasebe' },
  { value: 'Management', label: 'Yönetim' },
  { value: 'General', label: 'Genel' },
];

export const ROLE_LABELS = {
  super_admin: 'Süper Yönetici',
  admin: 'Yönetici',
  supervisor: 'Süpervizör',
  front_desk: 'Ön Büro',
  housekeeping: 'Kat Hizmetleri',
  maintenance: 'Teknik',
  finance: 'Muhasebe',
  sales: 'Satış',
};

export const STAFF_ROLES = new Set([
  'super_admin', 'admin', 'supervisor',
  'front_desk', 'housekeeping', 'maintenance', 'finance', 'sales',
]);

// Department filter options for the conversations list. Each entry maps a
// human-readable label to the set of backend `role` values it should match.
// `value: 'all'` is the no-op default that keeps every conversation visible.
export const CONVERSATION_DEPARTMENT_FILTERS = [
  { value: 'all', label: 'Tümü', roles: null },
  { value: 'front_desk', label: 'Ön Büro', roles: ['front_desk'] },
  { value: 'housekeeping', label: 'HK', roles: ['housekeeping'] },
  { value: 'maintenance', label: 'Teknik', roles: ['maintenance'] },
  { value: 'finance', label: 'Muhasebe', roles: ['finance'] },
  { value: 'management', label: 'Yönetim', roles: ['super_admin', 'admin', 'supervisor'] },
];

// Real-time delivery happens via Socket.IO; this poll is now just a safety
// net for missed events / cross-tab sync, so we can run it much less often.
export const POLL_INTERVAL_MS = 60000;

// Mirror of the backend RECALL_WINDOW_SECONDS — keeps the recall menu hidden
// once the message is past the window so we don't pretend the action is still
// available. The backend remains the source of truth and will reject late
// recalls with HTTP 400.
export const RECALL_WINDOW_MS = 5 * 60 * 1000;

// How long after the last `typing` event we keep the indicator visible.
// Slightly longer than the emit cadence so brief pauses don't flicker.
export const TYPING_INDICATOR_TTL_MS = 4000;
// Throttle how often we emit `internal_typing` while the user is typing.
export const TYPING_EMIT_THROTTLE_MS = 1500;

// Same 5-minute window applies to in-place edits — kept identical to the
// recall window so the menu logic is straightforward (one age check covers
// both actions). Backend enforces the same limit and rejects stale edits
// with HTTP 400.
export const EDIT_WINDOW_MS = 5 * 60 * 1000;
