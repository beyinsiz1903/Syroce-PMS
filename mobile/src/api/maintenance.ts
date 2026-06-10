import { api, apiRequest } from './client';

// Maintenance API client — mirror of backend/domains/pms/maintenance_router.py.
// Work-order list (GET) only requires authentication; work-order CREATE and the
// mobile technician-task submit are gated by require_module("housekeeping") on
// the backend. The mobile `maintenanceAccess` entitlement mirrors that role set
// so we only show the create form / submit action to users who could act —
// the backend still enforces every write.

export type WorkOrder = {
  id: string;
  room_id?: string | null;
  room_number?: string | null;
  issue_type?: string;
  priority?: string;
  status?: string;
  source?: string;
  description?: string | null;
  reported_by_role?: string | null;
  created_at?: string;
};

export type MaintenanceTask = {
  id: string;
  room_id?: string | null;
  room_number?: string | null;
  issue_type?: string;
  priority?: string;
  status?: string;
  description?: string | null;
  technician_notes?: string | null;
  time_spent_minutes?: number;
  created_at?: string;
  updated_at?: string;
};

// GET /api/maintenance/work-orders?status=&room_id=&priority= → { items, count }
export async function listWorkOrders(params?: {
  status?: string;
  room_id?: string;
  priority?: string;
}): Promise<WorkOrder[]> {
  const res = await api.get<{ items?: WorkOrder[] }>(
    '/api/maintenance/work-orders',
    params,
  );
  return res?.items ?? [];
}

// POST /api/maintenance/work-orders (MaintenanceWorkOrder body; issue_type required)
export async function createWorkOrder(body: {
  issue_type: string;
  priority?: string;
  description?: string | null;
  room_id?: string | null;
  room_number?: string | null;
  source?: string;
}): Promise<WorkOrder> {
  return api.post<WorkOrder>('/api/maintenance/work-orders', body);
}

// GET /api/maintenance/tasks → list
export async function listMaintenanceTasks(): Promise<MaintenanceTask[]> {
  const res = await api.get<MaintenanceTask[]>('/api/maintenance/tasks');
  return res ?? [];
}

// POST /api/maintenance/mobile/technician-task — scalar query params, no body.
export async function submitTechnicianTask(params: {
  task_id: string;
  status: 'started' | 'completed' | 'needs_parts';
  notes?: string;
  time_spent_minutes?: number;
}): Promise<{ success: boolean; task_id: string; message: string }> {
  return apiRequest('/api/maintenance/mobile/technician-task', {
    method: 'POST',
    query: {
      task_id: params.task_id,
      status: params.status,
      notes: params.notes,
      time_spent_minutes: params.time_spent_minutes,
    },
  });
}
