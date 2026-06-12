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

// GET /api/spa/availability — therapist x time-slot grid for a given day.
// Each slot carries per-therapist availability plus an `any_available` summary
// so the UI can offer free slots for quick selection and disable full ones.
export type SpaAvailabilityTherapistSlot = {
  therapist_id: string;
  therapist_name?: string;
  color?: string;
  available: boolean;
};

export type SpaAvailabilitySlot = {
  starts_at: string;
  ends_at: string;
  therapists: SpaAvailabilityTherapistSlot[];
  any_available: boolean;
};

export type SpaAvailability = {
  date: string;
  duration_minutes?: number;
  therapists: { id: string; name?: string; color?: string }[];
  slots: SpaAvailabilitySlot[];
  stats?: Record<string, number>;
};

// `date` is YYYY-MM-DD. `service_id` lets the backend block-check the slot for
// the service's real duration instead of the default slot size.
export async function getSpaAvailability(params: {
  date: string;
  service_id?: string;
  slot_minutes?: number;
}): Promise<SpaAvailability> {
  const res = await api.get<SpaAvailability>('/api/spa/availability', params);
  return (
    res ?? { date: params.date, therapists: [], slots: [] }
  );
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

// ── Activity Scheduler ──────────────────────────────────────────────────────
// Mirror of backend/domains/pms/activity_scheduler_router.py (prefix
// /api/activities). These cover general (non-spa) activities such as golf,
// tennis or yoga: a catalogue of activities, the resources (instructor / venue
// / equipment) they consume, and the date-based bookings that schedule them.
// Reads require any authenticated user; the create posts to a backend that
// re-enforces authorization, so a non-privileged user just sees the error.

export type Activity = {
  id: string;
  name: string;
  type?: string;
  duration_min?: number;
  price?: number;
  capacity?: number;
  description?: string | null;
  active?: boolean;
};

export type ActivityResource = {
  id: string;
  name: string;
  kind?: 'instructor' | 'venue' | 'equipment' | string;
  activity_types?: string[];
  capacity?: number;
  active?: boolean;
};

export type ActivityBooking = {
  id: string;
  activity_id: string;
  resource_id: string;
  guest_id: string;
  starts_at: string;
  ends_at?: string;
  duration_min?: number;
  note?: string | null;
  status?: string;
};

// GET /api/activities
export async function listActivities(type?: string): Promise<Activity[]> {
  const res = await api.get<Activity[]>('/api/activities', type ? { type } : undefined);
  return res ?? [];
}

// GET /api/activities/resources
export async function listActivityResources(kind?: string): Promise<ActivityResource[]> {
  const res = await api.get<ActivityResource[]>(
    '/api/activities/resources',
    kind ? { kind } : undefined,
  );
  return res ?? [];
}

// GET /api/activities/bookings?date=YYYY-MM-DD
export async function listActivityBookings(params?: {
  date?: string;
  resource_id?: string;
}): Promise<ActivityBooking[]> {
  const res = await api.get<ActivityBooking[]>('/api/activities/bookings', params);
  return res ?? [];
}

// Payload for POST /api/activities/bookings. The backend derives ends_at and
// the effective duration from the chosen activity, so the client sends the
// activity, resource, guest, the start instant and an optional note.
export type CreateActivityBookingInput = {
  activity_id: string;
  resource_id: string;
  guest_id: string;
  // ISO-8601 datetime (local wall time → ISO). Backend treats naive as UTC.
  starts_at: string;
  note?: string | null;
};

// POST /api/activities/bookings — allowed to throw so the form can surface a
// 409 (resource busy in that slot) or 404 (activity not found) inline.
export async function createActivityBooking(
  input: CreateActivityBookingInput,
): Promise<ActivityBooking> {
  return api.post<ActivityBooking>('/api/activities/bookings', input);
}

// Appointment lifecycle status. Backend `_SPA_TRANSITIONS` is the source of
// truth for which transitions are legal; the client mirrors it only to decide
// which actions to surface.
export type SpaAppointmentStatus =
  | 'scheduled'
  | 'in_progress'
  | 'completed'
  | 'no_show'
  | 'cancelled';

// POST /api/spa/appointments/{id}/status — staff-only on the backend
// (require_spa_ops + manage_sales); the `completed` transition additionally
// requires require_finance. Allowed to throw so the caller can surface a 403
// (insufficient role) or 409 (illegal transition) inline.
export async function updateSpaAppointmentStatus(
  appointmentId: string,
  status: SpaAppointmentStatus,
): Promise<{ ok: boolean; status: string }> {
  return api.post<{ ok: boolean; status: string }>(
    `/api/spa/appointments/${appointmentId}/status`,
    { status },
  );
}
