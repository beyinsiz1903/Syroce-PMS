import { api, apiRequest } from './client';

// Housekeeping task-action + issue-report client. Split out of the shared
// rooms.ts so the (housekeeping) screens own their write surface (Task #456 —
// mobil kat hizmetleri). Mirrors backend/domains/pms/housekeeping_router.py:
//   POST /housekeeping/mobile/start-task/{id}
//   POST /housekeeping/mobile/complete-task/{id}
//   POST /housekeeping/mobile/report-issue
// Every endpoint is RBAC-guarded (require_module("housekeeping")) and
// tenant-scoped server-side via the authenticated user.

// Start working on a task. The backend matches the task to the caller
// (assigned_to == current_user.name) and flips the task → in_progress and the
// room → cleaning; a task not owned by the caller returns 404.
export async function startTask(taskId: string): Promise<unknown> {
  return apiRequest(`/api/housekeeping/mobile/start-task/${encodeURIComponent(taskId)}`, {
    method: 'POST',
  });
}

// Complete a task. `notes` is an optional scalar query param (the backend
// declares it as `notes: str = None`); we never send the heavier `photos`
// body list from the one-tap action — completion just closes the task and
// flips the room to clean/inspected server-side.
export async function completeTask(taskId: string, notes?: string): Promise<unknown> {
  return apiRequest(`/api/housekeeping/mobile/complete-task/${encodeURIComponent(taskId)}`, {
    method: 'POST',
    query: notes ? { notes } : undefined,
  });
}

export type ReportIssueInput = {
  room_id: string;
  issue_type: string;
  description: string;
  priority?: string;
  // Data-URI strings (camera photo as image/jpeg + optional signature as an
  // image/svg+xml acknowledgment). The backend stores them on the issue as a
  // list[str]; a maintenance issue_type also spawns an engineering task.
  photos?: string[];
};

export async function reportIssue(input: ReportIssueInput): Promise<unknown> {
  return api.post('/api/housekeeping/mobile/report-issue', {
    priority: 'normal',
    photos: [],
    ...input,
  });
}
