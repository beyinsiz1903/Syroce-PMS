import { api } from './client';

// Spa & Wellness API client — read-focused mirror of backend/domains/spa/router.py.
// Reads are open to any authenticated user server-side; writes (not used here)
// stay gated by `require_spa_ops` on the backend. Queries are allowed to throw
// so react-query can surface loading / error / empty states honestly.

export type SpaService = {
  id: string;
  name: string;
  category?: string;
  duration_minutes?: number;
  price?: number;
  currency?: string;
  description?: string | null;
  active?: boolean;
};

export type SpaTherapist = {
  id: string;
  name: string;
  specialties?: string[];
  phone?: string | null;
  email?: string | null;
  work_start?: string;
  work_end?: string;
  color?: string;
  active?: boolean;
};

export type SpaAppointment = {
  id: string;
  service_id?: string;
  service_name?: string;
  service_category?: string;
  therapist_id?: string | null;
  room_id?: string | null;
  starts_at?: string;
  ends_at?: string;
  duration_minutes?: number;
  price?: number;
  currency?: string;
  guest_name?: string;
  guest_phone?: string | null;
  status?: string;
};

// GET /api/spa/services
export async function listSpaServices(): Promise<SpaService[]> {
  const res = await api.get<{ services?: SpaService[] }>('/api/spa/services');
  return res?.services ?? [];
}

// GET /api/spa/therapists
export async function listSpaTherapists(): Promise<SpaTherapist[]> {
  const res = await api.get<{ therapists?: SpaTherapist[] }>('/api/spa/therapists');
  return res?.therapists ?? [];
}

// GET /api/spa/appointments?date_from=&date_to=
export async function listSpaAppointments(params?: {
  date_from?: string;
  date_to?: string;
}): Promise<SpaAppointment[]> {
  const res = await api.get<{ appointments?: SpaAppointment[] }>(
    '/api/spa/appointments',
    params,
  );
  return res?.appointments ?? [];
}

// Payload for POST /api/spa/appointments. The backend derives ends_at, price,
// currency and service_name from the chosen service, so the client only sends
// the service, the start instant, the guest and the optional therapist / notes.
export type CreateSpaAppointmentInput = {
  service_id: string;
  // ISO-8601 datetime (local wall time → ISO). Backend treats naive as UTC.
  starts_at: string;
  guest_name: string;
  therapist_id?: string | null;
  guest_phone?: string | null;
  notes?: string | null;
};

// POST /api/spa/appointments — staff-only on the backend (require_spa_ops +
// manage_sales). Allowed to throw so the form can surface 403 / 409 conflicts.
export async function createSpaAppointment(
  input: CreateSpaAppointmentInput,
): Promise<SpaAppointment> {
  return api.post<SpaAppointment>('/api/spa/appointments', input);
}
